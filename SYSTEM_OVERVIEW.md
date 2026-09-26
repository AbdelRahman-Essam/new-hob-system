# New Hope Feed Manager — System Overview

A Django 4.2+ web app that tracks feed deliveries to customers ("سحوبات علف") across
regions, flags who's due/overdue for their next delivery every 40 days, and gives
staff, field reps, and customers each their own scoped view of the data.

Live deployment: `/home/trustech/projects/newhob-system` (Ubuntu, Gunicorn + Nginx, SQLite).

## 1. Architecture at a glance

```
Nginx (TLS, static files) → Gunicorn (3 workers) → Django (config/ + feed/) → SQLite (WAL mode)
```

- **`config/`** — Django project shell: `settings.py` (reads secrets from the environment,
  see §5), `urls.py`, `wsgi.py`.
- **`feed/`** — the entire application lives in this one app: `models.py`, `views.py`
  (function-based views), `forms.py`, `urls.py`, `admin.py`, `permissions.py`,
  `context.py` (injects branding/role into every template), `templates/feed/*.html`,
  `static/feed/style.css`.
- **No JavaScript framework / no API** — server-rendered HTML (Arabic, RTL), a small
  inline script only for browser delivery notifications on the dashboard.
- **Database**: SQLite by design (small deployment), tuned with WAL journal mode
  (`feed/apps.py`) so reads and writes don't block each other, plus a `timeout` so
  concurrent writers wait instead of erroring.
- **Caching**: in-process `LocMemCache`, used only to avoid re-querying the single
  `AppSettings` row on every transaction's status check.

## 2. Data model

| Model | Purpose |
|---|---|
| `Region` | A named area/segment ("الشريحة"). Customers belong to exactly one. |
| `Customer` | A farm/company. Holds contact info, its `Region`, an optional `rep` (the staff user responsible for it) and an optional `user` (its own login account). |
| `FeedTransaction` | One delivery: quantity, unit, price → `total_price` is computed on save; `due_date` is `date + 40 days`. Drives the "due soon / due today / late" status shown everywhere. |
| `AppSettings` | Singleton row: notification thresholds, dark mode, whether notifications are on. Cached for 5 minutes. |
| `Profile` | Extends Django's built-in `User` with an app-specific **role** (see §3). Separate from `is_staff`/`is_superuser`, which only control access to Django's own `/admin/`. |

Key computed logic lives on the models, not scattered across views/templates:
`FeedTransaction.status` / `.status_label` / `.remaining_text`, `Customer.last_tx` /
`.whatsapp_url`, `AppSettings.days_list` / `.threshold`.

Performance note: `Customer.objects.with_last_tx()` fetches every customer's most
recent transaction in **two queries total** (a correlated subquery + one bulk lookup)
instead of one query per customer — used everywhere a customer list is rendered
(dashboard, customer list, regions).

## 3. Roles & permissions

Five roles, stored on `Profile.role` (a superuser is *always* treated as `admin`,
regardless of what's stored):

| Role | Arabic label | Can see | Can edit |
|---|---|---|---|
| `view` | مشاهدة فقط | everything | nothing |
| `edit` | تعديل | everything | regions, customers, transactions |
| `rep` | مندوب | only customers where `Customer.rep == self` | only those customers/transactions |
| `client` | عميل | only the one customer where `Customer.user == self` | nothing (read-only) |
| `admin` | مدير كامل الصلاحيات | everything | everything + settings, users, backup/restore |

Enforcement is two-layered:
- **View-level**: `@can_edit` / `@can_edit_own` / `@can_admin` decorators
  (`feed/permissions.py`) gate whole views, raising `403` for the wrong role.
- **Row-level**: `visible_customers(user)` (`feed/models.py`) is the single source of
  truth for *which* customers/transactions a rep or client is allowed to touch — every
  view that lists or fetches a customer filters through it, so a rep can never
  enumerate another rep's customers by guessing an ID (404, not 403, for out-of-scope
  objects — deliberately not revealing that the record exists).

## 4. Linking a "rep" or "client" account to real data — and the bug that was fixed

This is a **two-step, intentional design**, documented in `README.md` and on the
Users page itself:

1. **Create the login account** on الإعدادات ← إدارة المستخدمين, with role مندوب or
   عميل. This alone does *not* connect it to any customer.
2. **Link it to a specific customer** by editing that customer (العملاء ← اختر عميل ←
   تعديل) and choosing it in the "المندوب المسؤول" / "حساب دخول العميل" dropdown.

Each dropdown is intentionally restricted:
- **"المندوب المسؤول"** only lists users with `Profile.role == "rep"`.
- **"حساب دخول العميل"** only lists users with `Profile.role == "client"` **and** not
  already linked to a *different* customer (a login account maps to exactly one
  customer — `Customer.user` is a `OneToOneField`).

**The reported issue** — the dropdown appearing empty with no explanation — happened
because step 1 hadn't been done yet for that role (no `rep`/`client` user existed), or
every existing `client` account was already linked elsewhere. The filtering itself was
correct; the UI just gave no indication of *why* the list was empty or what to do next,
which is indistinguishable from a broken control.

**Fix applied** (`feed/forms.py`, `feed/views.py`, `feed/templates/feed/form.html`,
`feed/templates/feed/users.html` — see the attached patch/zip):
- The customer form now shows an inline explanation under an empty dropdown (why it's
  empty — no such account exists yet, vs. every one is already linked elsewhere) with a
  **direct link to create that account**, pre-selecting the right role.
- That link carries the admin back to the exact customer form they came from once the
  new account is saved, instead of dropping them on the generic Users list.
- Form `help_text` is now rendered at all (previously defined but silently dropped by
  the template) — this benefits any future field, not just this one.
- Fixed a cosmetic mislabeling in the Users list: an account with no `Profile` row yet
  (e.g. a second superuser created via `createsuperuser` who hasn't logged in) was
  silently shown as "مشاهدة فقط"; it now shows an explicit "no role set yet" tag.
- Added regression tests (`feed/tests.py`) covering the empty-state messages and the
  create-and-return-here flow.

No model or database changes were needed — it's a forms/views/templates-only fix, so
**no new migration** is part of this update.

## 5. Configuration & secrets

`config/settings.py` reads everything environment-specific from the process
environment (see `.env.example`), loaded in production via the systemd
`EnvironmentFile` at `/etc/newhope.env`:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django's cryptographic key — must be a long random value in production. |
| `DEBUG` | `1` locally, **must be `0`** in production (verbose error pages otherwise leak internals). |
| `ALLOWED_HOSTS` | Comma-separated hostnames the app will answer for. |
| `CSRF_TRUSTED_ORIGINS` | Needed because Nginx terminates HTTPS in front of Django. |
| `SECURE_SSL_REDIRECT` | Forces HTTP → HTTPS once TLS is set up. |

Branding (`APP_NAME_AR/EN`, `CONTACT_NAME`, `CONTACT_PHONE`) is hard-coded at the
bottom of `settings.py` — edit directly there for a rebrand.

## 6. Suggested next enhancements (not yet implemented)

- **Bulk role assignment during CSV import**: `customers.html`'s import currently
  can't set `rep`/`user` per row — reps still have to be assigned per-customer
  afterwards.
- **Self-service password reset** for `client`/`rep` logins (currently an admin must
  reset passwords manually via the Users page).
- **Superuser profile backfill**: a management command (`ensure_profiles`) that creates
  a `Profile` row for any `User` missing one, so the Users page never has to guess.
- **Audit log** for who changed a customer's `rep`/`user` link and when — useful once
  more than one admin manages the system.
- **WhatsApp/SMS delivery** of the due-date alerts (currently browser push notifications
  only, which require the dashboard tab to be open).

## 7. Where to look for what

| Task | File(s) |
|---|---|
| Change the 40-day due window | `feed/models.py` → `DUE_DAYS` |
| Change who can do what | `feed/permissions.py`, `feed/models.py::visible_customers` |
| Add/edit a page | `feed/views.py` + matching template in `feed/templates/feed/` |
| Rebrand / contact info | `config/settings.py` (bottom) |
| Deployment steps | `DEPLOY.md` (full walkthrough) |
| Run the test suite | `python manage.py test` |
