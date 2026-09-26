from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Customer, FeedTransaction, Profile, Region, get_role


class FeedTests(TestCase):
    def setUp(self):
        self.r = Region.objects.create(name="برج العرب")
        self.c = Customer.objects.create(region=self.r, name="مزرعة أحمد", phone="01000000000")
        self.admin = User.objects.create_superuser("admin", password="pw12345")
        self.client.login(username="admin", password="pw12345")

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

    def test_bulk_last_tx_matches_per_customer_query(self):
        # The bulk with_last_tx() helper (used by dashboard/customers/regions to avoid N+1
        # queries) must return the exact same "last transaction" as the naive per-customer lookup.
        c2 = Customer.objects.create(region=self.r, name="مزرعة بلا نقلات")
        self.tx(date(2026, 1, 1)); newest = self.tx(date(2026, 5, 1))
        by_pk = {c.pk: c for c in Customer.objects.with_last_tx()}
        self.assertEqual(by_pk[self.c.pk].last_tx, newest)
        self.assertIsNone(by_pk[c2.pk].last_tx)

    def test_roles_gate_access(self):
        viewer = User.objects.create_user("viewer", password="pw12345")
        Profile.objects.create(user=viewer, role=Profile.ROLE_VIEW)
        editor = User.objects.create_user("editor", password="pw12345")
        Profile.objects.create(user=editor, role=Profile.ROLE_EDIT)

        self.assertEqual(get_role(viewer), "view")
        self.assertEqual(get_role(editor), "edit")
        self.assertEqual(get_role(self.admin), "admin")  # superuser, no Profile row needed

        self.client.logout(); self.client.login(username="viewer", password="pw12345")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)          # can view
        self.assertEqual(self.client.get(reverse("region_new")).status_code, 403)          # can't edit
        self.assertEqual(self.client.get(reverse("settings")).status_code, 403)            # can't admin

        self.client.logout(); self.client.login(username="editor", password="pw12345")
        self.assertEqual(self.client.get(reverse("region_new")).status_code, 200)          # can edit
        self.assertEqual(self.client.get(reverse("settings")).status_code, 403)            # still can't admin
