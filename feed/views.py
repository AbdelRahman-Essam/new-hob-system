import csv
import io
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core import serializers
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from .forms import CustomerForm, CustomerImportForm, RegionForm, SettingsForm, TransactionForm, UserForm
from .models import AppSettings, Customer, FeedTransaction, Profile, Region, get_role, visible_customers
from .permissions import can_admin, can_edit, can_edit_own

DUE_GRACE = 40  # "no recent delivery" = overdue by more than 40 days, or never delivered
FILTERS = [("all", "الكل"), ("soon", "مستحق قريبًا"), ("due", "مستحق اليوم"), ("late", "متأخر"), ("none", "لا توجد نقلة حديثة")]


def _form(request, form_class, title, next_url, instance=None, initial=None, on_save=None):
    form = form_class(request.POST or None, instance=instance, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if on_save:
            on_save(obj)
        obj.save()
        messages.success(request, "تم الحفظ")
        return redirect(next_url)
    return render(request, "feed/form.html", {"form": form, "title": title, "cancel": next_url})


@login_required
def dashboard(request):
    if get_role(request.user) == Profile.ROLE_CLIENT:
        c = visible_customers(request.user).select_related("region").first()
        if not c:
            return render(request, "feed/dashboard.html", {"no_client_link": True})
        return render(request, "feed/customer_detail.html", {"c": c, "history": list(c.transactions.all()), "t": c.last_tx})
    cfg = AppSettings.get()
    groups = {"soon": [], "due": [], "late": []}
    alerts = []
    my_customers = visible_customers(request.user).select_related("region").with_last_tx()
    for c in my_customers:
        t = c.last_tx
        if not t:
            continue
        if t.status in groups:
            groups[t.status].append({"c": c, "t": t})
        d, who = t.days_left, c.farm_name or c.name
        if cfg.notifications_enabled:
            if d < 0 and cfg.late_daily:
                alerts.append({"title": "تنبيه: سحب علف متأخر", "body": f"العميل: {who}\nمرّ {-d} يومًا بعد موعد الـ40 يومًا."})
            elif d == 0:
                alerts.append({"title": "موعد سحب علف مستحق اليوم", "body": f"العميل: {who}"})
            elif d in cfg.days_list:
                alerts.append({"title": "موعد سحب علف قريب", "body": f"العميل: {who}\nمتبقي {d} يوم على مرور 40 يومًا من آخر نقلة."})
    for g in groups.values():
        g.sort(key=lambda x: x["t"].days_left)
    ids = [c.pk for c in my_customers]
    agg = FeedTransaction.objects.filter(customer_id__in=ids).aggregate(q=Sum("quantity"), v=Sum("total_price"))
    return render(request, "feed/dashboard.html", {
        "groups": groups, "alerts": alerts, "n_customers": len(ids), "n_regions": Region.objects.count(),
        "total_qty": agg["q"] or 0, "total_value": agg["v"] or 0})


@login_required
def regions(request):
    my_customers = visible_customers(request.user)
    rows = []
    for r in Region.objects.all():
        cs = my_customers.filter(region=r).with_last_tx()
        if not cs and get_role(request.user) in (Profile.ROLE_REP, Profile.ROLE_CLIENT):
            continue  # hide regions with none of *my* customers for scoped roles
        qty = FeedTransaction.objects.filter(customer__in=cs).aggregate(q=Sum("quantity"))["q"] or 0
        need = sum(1 for c in cs if c.last_tx and c.last_tx.status != "ok")
        rows.append({"r": r, "n": len(cs), "qty": qty, "need": need})
    return render(request, "feed/regions.html", {"rows": rows})


@login_required
@can_edit
def region_form(request, pk=None):
    obj = get_object_or_404(Region, pk=pk) if pk else None
    return _form(request, RegionForm, "تعديل الشريحة" if obj else "شريحة جديدة", reverse("regions"), instance=obj)


@login_required
def customers(request):
    q, f, r = request.GET.get("q", "").strip(), request.GET.get("f", "all"), request.GET.get("r", "")
    qs = visible_customers(request.user).select_related("region")
    if r.isdigit():
        qs = qs.filter(region_id=r)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(farm_name__icontains=q) | Q(phone__icontains=q) | Q(region__name__icontains=q))
    rows = []
    for c in qs.with_last_tx():
        t = c.last_tx
        if f == "none" and t and t.days_left >= -DUE_GRACE:
            continue
        if f in ("soon", "due", "late") and not (t and t.status == f):
            continue
        rows.append({"c": c, "t": t})
    rows.sort(key=lambda x: (x["t"] is None, x["t"].days_left if x["t"] else 0))
    region = Region.objects.filter(pk=r).first() if r.isdigit() else None
    return render(request, "feed/customers.html", {"rows": rows, "q": q, "f": f, "filters": FILTERS, "region": region})


@login_required
@can_edit_own
def customer_form(request, pk=None):
    obj = get_object_or_404(visible_customers(request.user), pk=pk) if pk else None
    if not obj and not Region.objects.exists():
        messages.error(request, "أضف شريحة أولًا")
        return redirect("region_new")
    initial = {"region": request.GET.get("r")} if request.GET.get("r") else None
    nxt = reverse("customer_detail", args=[pk]) if pk else reverse("customers")
    role = get_role(request.user)

    def attach(o):
        if role == Profile.ROLE_REP and not o.rep_id:
            o.rep = request.user  # a rep's new customers are automatically their own
    return _form(request, lambda *a, **kw: CustomerForm(*a, allow_assign=(role in (Profile.ROLE_EDIT, Profile.ROLE_ADMIN)),
                                                          next_url=request.get_full_path(), **kw),
                 "تعديل العميل" if obj else "عميل جديد", nxt, instance=obj, initial=initial, on_save=attach)


@login_required
@can_edit_own
def customer_import(request):
    """Bulk-add members/customers from a CSV file (columns: name, phone, farm_name, address,
    notes, region — region column optional if a default region is chosen below). A rep's
    imported customers are automatically assigned to them, same as customer_form."""
    form = CustomerImportForm(request.POST or None, request.FILES or None)
    created = errors = []
    my_role = get_role(request.user)
    if request.method == "POST" and form.is_valid():
        created, errors = [], []
        default_region = form.cleaned_data["default_region"]
        raw = form.cleaned_data["file"].read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(raw))
        with transaction.atomic():
            for i, row in enumerate(reader, start=2):  # row 1 is the header
                row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                name = row.get("name") or row.get("الاسم")
                if not name:
                    errors.append(f"سطر {i}: بلا اسم — تم تجاهله")
                    continue
                region_name = row.get("region") or row.get("الشريحة")
                region = Region.objects.filter(name__iexact=region_name).first() if region_name else default_region
                if not region:
                    errors.append(f"سطر {i} ({name}): لا توجد شريحة محددة أو مطابقة — تم تجاهله")
                    continue
                Customer.objects.create(
                    region=region, name=name,
                    phone=row.get("phone") or row.get("الهاتف") or "",
                    farm_name=row.get("farm_name") or row.get("المزرعة") or "",
                    address=row.get("address") or row.get("العنوان") or "",
                    notes=row.get("notes") or row.get("ملاحظات") or "",
                    rep=request.user if my_role == Profile.ROLE_REP else None,
                )
                created.append(name)
        if created:
            messages.success(request, f"تمت إضافة {len(created)} عميل بنجاح")
        if errors:
            messages.error(request, " | ".join(errors))
        if created and not errors:
            return redirect("customers")
    return render(request, "feed/customer_import.html", {"form": form, "created": created, "errors": errors})


@login_required
def customer_detail(request, pk):
    c = get_object_or_404(visible_customers(request.user).select_related("region"), pk=pk)
    return render(request, "feed/customer_detail.html", {"c": c, "history": list(c.transactions.all()), "t": c.last_tx})


@login_required
@can_edit_own
def tx_form(request, cpk=None, pk=None):
    obj = get_object_or_404(FeedTransaction.objects.filter(customer__in=visible_customers(request.user)), pk=pk) if pk else None
    customer = obj.customer if obj else get_object_or_404(visible_customers(request.user), pk=cpk)

    def attach(o):
        o.customer = customer
    return _form(request, TransactionForm, ("تعديل النقلة" if obj else "إضافة نقلة") + " — " + customer.name,
                 reverse("customer_detail", args=[customer.pk]), instance=obj, on_save=attach)


@login_required
def delete(request, kind, pk):
    model = {"region": Region, "customer": Customer, "tx": FeedTransaction}.get(kind)
    if not model:
        return redirect("dashboard")
    role = get_role(request.user)
    if kind == "region":
        if role not in ("edit", "admin"):
            raise PermissionDenied("صلاحيتك الحالية لا تسمح بهذا الإجراء")
        obj = get_object_or_404(Region, pk=pk)
    else:
        if role not in ("edit", "rep", "admin"):
            raise PermissionDenied("صلاحيتك الحالية لا تسمح بهذا الإجراء")
        scope = visible_customers(request.user)
        obj = get_object_or_404(model.objects.filter(**({"pk__in": scope} if kind == "customer" else {"customer__in": scope})), pk=pk)
    back = reverse({"region": "regions", "customer": "customers"}[kind]) if kind != "tx" else reverse("customer_detail", args=[obj.customer_id])
    if request.method == "POST":
        obj.delete()
        messages.success(request, "تم الحذف")
        return redirect(back)
    warn = {"region": "سيتم حذف كل عملاء الشريحة وسجل سحوباتهم أيضًا.", "customer": "سيتم حذف كل سجل سحوبات العميل أيضًا."}.get(kind, "")
    return render(request, "feed/confirm.html", {"obj": obj, "warn": warn, "cancel": back})


@login_required
def report(request):
    g = request.GET
    my_customers = visible_customers(request.user)
    qs = FeedTransaction.objects.filter(customer__in=my_customers).select_related("customer__region").order_by("-date")
    if g.get("r", "").isdigit():
        qs = qs.filter(customer__region_id=g["r"])
    if g.get("c", "").isdigit():
        qs = qs.filter(customer_id=g["c"])
    a, b = parse_date(g.get("a", "") or ""), parse_date(g.get("b", "") or "")
    if a:
        qs = qs.filter(date__gte=a)
    if b:
        qs = qs.filter(date__lte=b)
    rows = list(qs)
    if g.get("csv"):
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="feed_report.csv"'
        resp.write("\ufeff")
        w = csv.writer(resp)
        w.writerow(["الشريحة", "العميل", "المزرعة", "الهاتف", "تاريخ السحب", "النوع", "الكمية", "الوحدة", "السعر", "الإجمالي", "موعد 40 يوم"])
        for t in rows:
            c = t.customer
            w.writerow([c.region.name, c.name, c.farm_name, c.phone, t.date, t.feed_type, t.quantity, t.unit, t.unit_price, t.total_price, t.due_date])
        return resp
    by = {}
    for t in rows:
        x = by.setdefault(t.customer.region.name, [0, 0, 0])
        x[0] += 1; x[1] += t.quantity; x[2] += t.total_price
    due = late = 0
    for c in my_customers.with_last_tx():
        t = c.last_tx
        due += bool(t and t.status == "due"); late += bool(t and t.status == "late")
    return render(request, "feed/report.html", {
        "rows": rows, "by_region": by.items(), "n": len(rows), "qty": sum(t.quantity for t in rows),
        "value": sum(t.total_price for t in rows), "due": due, "late": late, "g": g,
        "regions": Region.objects.all(), "customers": my_customers.filter(region_id=g["r"]) if g.get("r", "").isdigit() else my_customers,
        "today": timezone.localdate()})


@login_required
@can_admin
def settings_view(request):
    form = SettingsForm(request.POST or None, instance=AppSettings.get())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ الإعدادات")
        return redirect("settings")
    return render(request, "feed/settings.html", {"form": form})


@login_required
@can_admin
def backup(request):
    data = serializers.serialize("json", [*Region.objects.all(), *Customer.objects.all(), *FeedTransaction.objects.all(), *AppSettings.objects.all()])
    resp = HttpResponse(data, content_type="application/json; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="newhope_backup_{timezone.localdate()}.json"'
    return resp


@login_required
@can_admin
def restore(request):
    f = request.FILES.get("file")
    if request.method == "POST" and f:
        try:
            objs = list(serializers.deserialize("json", f.read().decode("utf-8-sig")))
            with transaction.atomic():
                for m in (FeedTransaction, Customer, Region, AppSettings):
                    m.objects.all().delete()
                for o in objs:
                    o.save()
            messages.success(request, "تمت استعادة النسخة الاحتياطية")
        except Exception:
            messages.error(request, "ملف النسخة الاحتياطية غير صالح، لم يتغير شيء")
    return redirect("settings")


@login_required
@can_admin
def users_view(request):
    return render(request, "feed/users.html", {"rows": User.objects.select_related("profile").all().order_by("username")})


def _safe_next(request, raw):
    """Only ever redirect to a path of this same site (never an attacker-supplied external URL)."""
    if raw and url_has_allowed_host_and_scheme(raw, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return raw
    return None


@login_required
@can_admin
def user_form(request, pk=None):
    obj = get_object_or_404(User, pk=pk) if pk else None
    # Coming here from "no rep/client accounts yet" links on the customer form: preselect the
    # role that was missing, and remember where to send the admin back to once this is saved.
    next_url = _safe_next(request, request.POST.get("next") or request.GET.get("next"))
    initial = None
    if not obj and request.GET.get("role") in dict(Profile.ROLES):
        initial = {"role": request.GET["role"]}
    form = UserForm(request.POST or None, instance=obj, initial=initial)
    cancel = next_url or reverse("users")
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        pw = form.cleaned_data.get("password")
        if pw:
            user.set_password(pw)
        elif not obj:
            messages.error(request, "اكتب كلمة مرور للمستخدم الجديد")
            return render(request, "feed/form.html", {"form": form, "title": "مستخدم جديد", "cancel": cancel, "next_url": next_url})
        role = form.cleaned_data["role"]
        user.is_staff = (role == Profile.ROLE_ADMIN)  # also grants/revokes access to Django's own /admin/
        user.save()
        Profile.objects.update_or_create(user=user, defaults={"role": role})
        messages.success(request, "تم الحفظ")
        return redirect(next_url or "users")
    return render(request, "feed/form.html", {"form": form, "title": "تعديل مستخدم" if obj else "مستخدم جديد",
                                               "cancel": cancel, "next_url": next_url})


@login_required
@can_admin
def user_delete(request, pk):
    obj = get_object_or_404(User, pk=pk)
    if obj == request.user:
        messages.error(request, "لا يمكنك حذف حسابك الحالي")
        return redirect("users")
    if request.method == "POST":
        obj.delete()
        messages.success(request, "تم الحذف")
        return redirect("users")
    return render(request, "feed/confirm.html", {"obj": obj.username, "warn": "سيفقد هذا المستخدم إمكانية الدخول.", "cancel": reverse("users")})
