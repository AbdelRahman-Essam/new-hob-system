from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Customer, FeedTransaction, Region


class FeedTests(TestCase):
    def setUp(self):
        self.r = Region.objects.create(name="برج العرب")
        self.c = Customer.objects.create(region=self.r, name="مزرعة أحمد", phone="01000000000")

    def tx(self, d, q="10", p="100"):
        return FeedTransaction.objects.create(customer=self.c, date=d, quantity=Decimal(q), unit_price=Decimal(p))

    def test_40_days(self):
        self.assertEqual(self.tx(date(2026, 9, 21)).due_date, date(2026, 10, 31))
        self.assertEqual(self.tx(date(2024, 1, 25)).due_date, date(2024, 3, 5))   # leap year
        self.assertEqual(self.tx(date(2026, 12, 1)).due_date, date(2027, 1, 10))  # year rollover

    def test_total(self):
        self.assertEqual(self.tx(date.today(), "2.5", "3.33").total_price, Decimal("8.33"))

    def test_status(self):
        t = timezone.localdate()
        self.assertEqual(self.tx(t - timedelta(days=40)).status, "due")
        self.assertEqual(self.tx(t - timedelta(days=41)).status, "late")
        self.assertEqual(self.tx(t - timedelta(days=35)).status, "soon")
        self.assertEqual(self.tx(t).status, "ok")

    def test_history_kept_and_last(self):
        self.tx(date(2026, 1, 1)); new = self.tx(date(2026, 3, 1))
        self.assertEqual(self.c.transactions.count(), 2)
        self.assertEqual(self.c.last_tx, new)

    def test_invalid_quantity(self):
        t = FeedTransaction(customer=self.c, date=date.today(), quantity=Decimal("0"), unit_price=Decimal("1"))
        with self.assertRaises(ValidationError):
            t.full_clean()

    def test_delete_cascade_and_pages(self):
        self.tx(date.today())
        for name, args in [("dashboard", []), ("regions", []), ("customers", []), ("report", []), ("settings", []),
                           ("customer_detail", [self.c.pk]), ("backup", [])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200, name)
        self.client.post(reverse("delete", args=["customer", self.c.pk]))
        self.assertEqual(FeedTransaction.objects.count(), 0)
