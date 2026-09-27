from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from feed.models import Profile


class Command(BaseCommand):
    help = "Creates a missing Profile (default role: view) for any existing user that doesn't have one yet."

    def handle(self, *args, **options):
        made = 0
        for user in User.objects.select_related("profile"):
            try:
                user.profile
            except Profile.DoesNotExist:
                Profile.objects.create(user=user, role=Profile.ROLE_VIEW)
                made += 1
                self.stdout.write(f"  + created profile for '{user.username}' (role: مشاهدة فقط — عدّله من صفحة المستخدمين)")
        if made:
            self.stdout.write(self.style.SUCCESS(f"تم إنشاء {made} ملف صلاحية ناقص."))
        else:
            self.stdout.write(self.style.SUCCESS("كل المستخدمين لديهم بالفعل ملف صلاحية. لا شيء لعمله."))
