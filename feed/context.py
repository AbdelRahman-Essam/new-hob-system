from django.conf import settings
from .models import AppSettings, get_role


def branding(request):
    role = get_role(request.user) if request.user.is_authenticated else None
    return {
        "app": AppSettings.get(),
        "APP_NAME_AR": settings.APP_NAME_AR,
        "APP_NAME_EN": settings.APP_NAME_EN,
        "CONTACT_NAME": settings.CONTACT_NAME,
        "CONTACT_PHONE": settings.CONTACT_PHONE,
        "role": role,
        "can_edit": role in ("edit", "admin"),
        "can_admin": role == "admin",
    }
