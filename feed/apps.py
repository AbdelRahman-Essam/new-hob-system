from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _tune_sqlite(sender, connection, **kwargs):
    if connection.vendor == "sqlite":
        cursor = connection.cursor()
        # WAL: readers don't block writers and vice versa (default SQLite mode locks the whole file).
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")


def _ensure_profile(sender, instance, created, **kwargs):
    # Guarantees every User gets a Profile row (default: view-only) no matter how the account
    # was created — including through Django's own /admin/ "Add user" form, which has no idea
    # our app even has a Profile model. Without this, a user created that way is invisible to
    # any profile__role=... filter (e.g. the "client login" / "rep" dropdowns on the customer
    # form) until someone happens to re-save them through the app's own user_form view.
    if created:
        from .models import Profile
        Profile.objects.get_or_create(user=instance)


class FeedConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "feed"

    def ready(self):
        from django.contrib.auth.models import User
        from django.db.models.signals import post_save
        connection_created.connect(_tune_sqlite)
        post_save.connect(_ensure_profile, sender=User)
