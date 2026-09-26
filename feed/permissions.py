"""Three-tier permission system for this app (separate from Django's own admin site):

    view  - can log in and see everything, but every add/edit/delete control is hidden and blocked
    edit  - can additionally add/edit/delete regions, customers and feed transactions
    admin - can additionally manage settings, users, and backup/restore

Superusers (created with `createsuperuser`) are always treated as 'admin' here.

Both decorators assume @login_required has already run (it's applied above these on every
view that uses them), so by this point request.user is always a real logged-in account —
lacking the *role* to proceed is a 403 (Forbidden), not a redirect back to the login page.
"""
from functools import wraps
from django.core.exceptions import PermissionDenied
from .models import get_role


def _require_role(allowed):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if get_role(request.user) not in allowed:
                raise PermissionDenied("صلاحيتك الحالية لا تسمح بهذا الإجراء")
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


can_edit = _require_role({"edit", "admin"})
can_admin = _require_role({"admin"})
