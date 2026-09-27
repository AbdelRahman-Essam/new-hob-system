from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .forms import CustomerForm
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

    def test_rep_sees_only_own_customers(self):
        rep = User.objects.create_user("rep1", password="pw12345")
        Profile.objects.create(user=rep, role=Profile.ROLE_REP)
        mine = Customer.objects.create(region=self.r, name="عميل المندوب", rep=rep)
        self.client.logout(); self.client.login(username="rep1", password="pw12345")

        resp = self.client.get(reverse("customers"))
        self.assertContains(resp, "عميل المندوب")
        self.assertNotContains(resp, self.c.name)  # self.c belongs to no one — invisible to the rep

        self.assertEqual(self.client.get(reverse("customer_detail", args=[self.c.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("customer_detail", args=[mine.pk])).status_code, 200)

        self.client.post(reverse("tx_new", args=[mine.pk]),
                          {"date": date.today(), "quantity": "5", "unit": "طن", "unit_price": "10"})
        self.assertEqual(mine.transactions.count(), 1)
        self.assertEqual(self.client.get(reverse("region_new")).status_code, 403)  # reps don't manage regions

    def test_client_sees_only_own_record(self):
        cu = User.objects.create_user("client1", password="pw12345")
        Profile.objects.create(user=cu, role=Profile.ROLE_CLIENT)
        mine = Customer.objects.create(region=self.r, name="عميل شخصي", user=cu)
        self.client.logout(); self.client.login(username="client1", password="pw12345")

        resp = self.client.get(reverse("dashboard"))  # clients land straight on their own record
        self.assertContains(resp, "عميل شخصي")
        self.assertEqual(self.client.get(reverse("customer_detail", args=[self.c.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("region_new")).status_code, 403)
        self.assertEqual(self.client.get(reverse("customer_new")).status_code, 403)  # clients never add/edit
        edit_url = reverse("customer_edit", args=[mine.pk])
        self.assertNotContains(resp, edit_url)  # no edit link shown to a client viewing their own record

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

    def test_client_login_dropdown_not_emptied_by_sql_null_gotcha(self):
        # Regression test: CustomerForm's "user" (client login) field queryset used to build its
        # "already linked elsewhere" exclusion list from ALL other customers' user_id, including
        # NULLs. `NOT IN (list containing NULL)` matches zero rows in SQL, so as soon as one
        # customer had no linked client account (the normal case), the dropdown went empty for
        # every customer, always.
        Customer.objects.create(region=self.r, name="عميل بلا حساب دخول")  # user=None, the normal case
        available_client = User.objects.create_user("client2", password="pw12345")
        Profile.objects.create(user=available_client, role=Profile.ROLE_CLIENT)
        form = CustomerForm(allow_assign=True)
        self.assertIn(available_client, form.fields["user"].queryset)
