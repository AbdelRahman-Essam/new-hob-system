from django import forms
from django.contrib.auth.models import User
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

    def __init__(self, *args, allow_assign=False, **kwargs):
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
            linked_elsewhere = Customer.objects.exclude(pk=self.instance.pk if self.instance else None).values_list("user_id", flat=True)
            self.fields["user"].queryset = User.objects.filter(profile__role=Profile.ROLE_CLIENT).exclude(pk__in=linked_elsewhere)


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
