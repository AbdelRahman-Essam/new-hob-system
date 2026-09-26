from django.conf import settings
from .models import AppSettings
def branding(request):
    return {"app": AppSettings.get(), "APP_NAME_AR": settings.APP_NAME_AR, "APP_NAME_EN": settings.APP_NAME_EN,
            "CONTACT_NAME": settings.CONTACT_NAME, "CONTACT_PHONE": settings.CONTACT_PHONE}
