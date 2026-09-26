import re
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings as django_settings
from django.core.cache import cache
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import OuterRef, Subquery
from django.utils import timezone

DUE_DAYS = 40


class Region(models.Model):
    name = models.CharField("اسم الشريحة", max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CustomerQuerySet(models.QuerySet):
    def with_last_tx(self):
        """Attach each customer's latest transaction in 2 queries total instead of one query per customer
        (fixes an N+1 slowdown that got worse as the customer list grows)."""
        last_id = FeedTransaction.objects.filter(customer=OuterRef("pk")).order_by("-date", "-id").values("id")[:1]
        customers = list(self.annotate(_last_tx_id=Subquery(last_id)))
        tx_ids = [c._last_tx_id for c in customers if c._last_tx_id]
        tx_by_id = FeedTransaction.objects.in_bulk(tx_ids)
        for c in customers:
            c._last_tx_cache = tx_by_id.get(c._last_tx_id)
        return customers


class Customer(models.Model):
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="customers", verbose_name="الشريحة")
    name = models.CharField("الاسم", max_length=150)
    phone = models.CharField("رقم الهاتف", max_length=30, blank=True)
    farm_name = models.CharField("اسم المزرعة / الشركة", max_length=150, blank=True)
    address = models.CharField("العنوان", max_length=250, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomerQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["region", "name"])]

    def __str__(self):
        return self.name

    @property
    def last_tx(self):
        # Uses the bulk-loaded value from with_last_tx() when available (list pages);
        # falls back to a single query when a customer is fetched on its own (detail page).
        if hasattr(self, "_last_tx_cache"):
            return self._last_tx_cache
        return self.transactions.order_by("-date", "-id").first()

    @property
    def whatsapp_url(self):
        n = re.sub(r"\D", "", self.phone)
        if n.startswith("0"):
            n = "2" + n
        return f"https://wa.me/{n}" if n else ""


class FeedTransaction(models.Model):
    UNITS = [("طن", "طن"), ("كجم", "كجم"), ("شيكارة", "شيكارة")]
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="transactions")
    date = models.DateField("تاريخ السحب", default=timezone.localdate)
    time = models.TimeField("وقت السحب (اختياري)", null=True, blank=True)
    feed_type = models.CharField("نوع العلف", max_length=120, blank=True)
    quantity = models.DecimalField("الكمية", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    unit = models.CharField("الوحدة", max_length=10, choices=UNITS, default="طن")
    unit_price = models.DecimalField("سعر الوحدة", max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0"))])
    total_price = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    vehicle_number = models.CharField("رقم السيارة (اختياري)", max_length=40, blank=True)
    invoice_number = models.CharField("رقم إذن/فاتورة (اختياري)", max_length=60, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    due_date = models.DateField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["customer", "-date"]),
            models.Index(fields=["due_date"]),
        ]

    def save(self, *args, **kwargs):
        self.total_price = (Decimal(self.quantity) * Decimal(self.unit_price)).quantize(Decimal("0.01"), ROUND_HALF_UP)
        self.due_date = self.date + timedelta(days=DUE_DAYS)  # true calendar arithmetic
        super().save(*args, **kwargs)

    @property
    def days_left(self):
        return (self.due_date - timezone.localdate()).days

    @property
    def status(self):
        d = self.days_left
        if d < 0:
            return "late"
        if d == 0:
            return "due"
        return "soon" if d <= AppSettings.get().threshold else "ok"

    @property
    def status_label(self):
        return {"ok": "بعيد", "soon": "اقترب الموعد", "due": "مستحق اليوم", "late": "متأخر"}[self.status]

    @property
    def remaining_text(self):
        d = self.days_left
        return f"متبقي {d} يوم" if d > 0 else "مستحق اليوم" if d == 0 else f"متأخر {-d} يوم"


APP_SETTINGS_CACHE_KEY = "feed_app_settings_singleton"


class AppSettings(models.Model):
    notify_days = models.CharField("أيام التنبيه قبل الاستحقاق (مفصولة بفاصلة)", max_length=40, default="7,3,1")
    notifications_enabled = models.BooleanField("تفعيل التنبيهات", default=True)
    late_daily = models.BooleanField("تنبيه يومي للمتأخرين", default=True)
    dark_mode = models.BooleanField("الوضع الليلي", default=False)

    @classmethod
    def get(cls):
        # Cached: this singleton row is read on every transaction's .status (often dozens of
        # times per page), so re-querying it each time is wasted work as the data grows.
        obj = cache.get(APP_SETTINGS_CACHE_KEY)
        if obj is None:
            obj = cls.objects.get_or_create(pk=1)[0]
            cache.set(APP_SETTINGS_CACHE_KEY, obj, 300)
        return obj

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.set(APP_SETTINGS_CACHE_KEY, self, 300)

    @property
    def days_list(self):
        return [int(x) for x in re.findall(r"\d+", self.notify_days)] or [7, 3, 1]

    @property
    def threshold(self):
        return max(self.days_list)


class Profile(models.Model):
    """Extends the built-in User with a permission level for this app specifically
    (separate from Django's own is_staff/is_superuser, which still control /admin/ access)."""
    ROLE_VIEW, ROLE_EDIT, ROLE_ADMIN = "view", "edit", "admin"
    ROLES = [(ROLE_VIEW, "مشاهدة فقط"), (ROLE_EDIT, "تعديل (إضافة وتعديل البيانات)"), (ROLE_ADMIN, "مدير كامل الصلاحيات")]

    user = models.OneToOneField(django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField("الصلاحية", max_length=10, choices=ROLES, default=ROLE_VIEW)

    def __str__(self):
        return f"{self.user.username} — {self.get_role_display()}"

    @property
    def can_edit(self):
        return self.role in (self.ROLE_EDIT, self.ROLE_ADMIN)

    @property
    def can_admin(self):
        return self.role == self.ROLE_ADMIN


def get_role(user):
    """Returns 'view' | 'edit' | 'admin' for any logged-in user, creating a Profile
    (defaulting to view-only) the first time an older account is seen."""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return Profile.ROLE_ADMIN
    profile, _ = Profile.objects.get_or_create(user=user, defaults={"role": Profile.ROLE_VIEW})
    return profile.role
