from django import forms
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from .models import AppSettings, Customer, FeedTransaction, Profile, Region


class UserForm(forms.ModelForm):
    password = forms.CharField(label="كلمة المرور (اتركها فارغة للإبقاء عليها عند التعديل)", required=False,
                                widget=forms.PasswordInput(render_value=False))
    role = forms.ChoiceField(label="الصلاحية", choices=Profile.ROLES, initial=Profile.ROLE_VIEW)

    class Meta:
        model = User
        fields = ["username", "is_active"]
        labels = {"username": "اسم المستخدم", "is_active": "الحساب مفعّل"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["role"].initial = getattr(self.instance, "profile", None) and self.instance.profile.role


class RegionForm(forms.ModelForm):
    class Meta:
        model = Region
        fields = ["name"]


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["region", "name", "phone", "farm_name", "address", "notes", "rep", "user"]
        labels = {"rep": "المندوب المسؤول", "user": "حساب دخول العميل (اختياري)"}
        widgets = {"notes": forms.Textarea(attrs={"rows": 2}), "phone": forms.TextInput(attrs={"inputmode": "tel"})}

    def __init__(self, *args, allow_assign=False, next_url=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not allow_assign:
            # Only an admin reassigns who a customer belongs to (their rep) or which login
            # account can see them (their client user) — everyone else edits the rest as usual.
            del self.fields["rep"]
            del self.fields["user"]
        else:
            self.fields["rep"].required = False
            self.fields["rep"].queryset = User.objects.filter(profile__role=Profile.ROLE_REP)
            self.fields["user"].required = False
            # A client login account can only ever be linked to ONE customer, so once it's
            # assigned elsewhere it must disappear from every other customer's list — except
            # this customer's own current instance, which stays selectable (self.instance.pk
            # is None for a brand-new customer, and no row has pk=None, so nothing is excluded).
            linked_elsewhere = Customer.objects.exclude(pk=self.instance.pk).values_list("user_id", flat=True)
            self.fields["user"].queryset = User.objects.filter(profile__role=Profile.ROLE_CLIENT).exclude(pk__in=linked_elsewhere)

            # Both dropdowns are ONLY ever populated from users created on the "المستخدمون" page
            # with the matching role ("مندوب"/"عميل"). If none exist yet — or every client account
            # is already linked to a different customer — the <select> is legitimately empty with
            # no on-screen explanation, which looks like a bug. Spell out why and link straight to
            # creating one, carrying the user back here afterwards.
            if not self.fields["rep"].queryset.exists():
                self.fields["rep"].help_text = self._empty_role_hint(Profile.ROLE_REP, next_url,
                    "لا يوجد أي مستخدم بصلاحية «مندوب» بعد.")
            if not self.fields["user"].queryset.exists():
                reason = ("كل حسابات «عميل» الموجودة مرتبطة بعملاء آخرين بالفعل."
                          if User.objects.filter(profile__role=Profile.ROLE_CLIENT).exists()
                          else "لا يوجد أي مستخدم بصلاحية «عميل» بعد.")
                self.fields["user"].help_text = self._empty_role_hint(Profile.ROLE_CLIENT, next_url, reason)

    @staticmethod
    def _empty_role_hint(role, next_url, reason):
        url = reverse("user_new") + "?" + urlencode({"role": role, **({"next": next_url} if next_url else {})})
        return format_html('{} <a href="{}">أنشئ حساب مستخدم بهذه الصلاحية الآن</a>.', reason, url)


class CustomerImportForm(forms.Form):
    file = forms.FileField(label="ملف CSV")
    default_region = forms.ModelChoiceField(label="الشريحة الافتراضية (تُستخدم إن لم يحدد الملف شريحة للسطر)",
                                             queryset=Region.objects.all(), required=False)


class TransactionForm(forms.ModelForm):
    class Meta:
        model = FeedTransaction
        fields = ["date", "time", "feed_type", "quantity", "unit", "unit_price", "vehicle_number", "invoice_number", "notes"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
                   "notes": forms.Textarea(attrs={"rows": 2})}


class SettingsForm(forms.ModelForm):
    class Meta:
        model = AppSettings
        fields = ["notifications_enabled", "notify_days", "late_daily", "dark_mode"]

    def clean_notify_days(self):
        parts = [p.strip() for p in self.cleaned_data["notify_days"].split(",") if p.strip()]
        if not parts or not all(p.isdigit() and 1 <= int(p) <= 39 for p in parts):
            raise forms.ValidationError("اكتب أرقامًا من 1 إلى 39 مفصولة بفاصلة، مثل 7,3,1")
        return ",".join(parts)
