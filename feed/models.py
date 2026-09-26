import re
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

DUE_DAYS = 40


class Region(models.Model):
    name = models.CharField("اسم الشريحة", max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Customer(models.Model):
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="customers", verbose_name="الشريحة")
    name = models.CharField("الاسم", max_length=150)
    phone = models.CharField("رقم الهاتف", max_length=30, blank=True)
    farm_name = models.CharField("اسم المزرعة / الشركة", max_length=150, blank=True)
    address = models.CharField("العنوان", max_length=250, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def last_tx(self):
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


class AppSettings(models.Model):
    notify_days = models.CharField("أيام التنبيه قبل الاستحقاق (مفصولة بفاصلة)", max_length=40, default="7,3,1")
    notifications_enabled = models.BooleanField("تفعيل التنبيهات", default=True)
    late_daily = models.BooleanField("تنبيه يومي للمتأخرين", default=True)
    dark_mode = models.BooleanField("الوضع الليلي", default=False)

    @classmethod
    def get(cls):
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def days_list(self):
        return [int(x) for x in re.findall(r"\d+", self.notify_days)] or [7, 3, 1]

    @property
    def threshold(self):
        return max(self.days_list)
