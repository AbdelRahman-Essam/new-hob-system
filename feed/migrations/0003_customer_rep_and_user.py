import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('feed', '0002_profile_and_indexes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='role',
            field=models.CharField(choices=[('view', 'مشاهدة فقط (كل البيانات)'), ('edit', 'تعديل (كل البيانات)'), ('rep', 'مندوب (عملاؤه فقط)'), ('client', 'عميل (بياناته فقط)'), ('admin', 'مدير كامل الصلاحيات')], default='view', max_length=10, verbose_name='الصلاحية'),
        ),
        migrations.AddField(
            model_name='customer',
            name='rep',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='clients', to=settings.AUTH_USER_MODEL, verbose_name='المندوب المسؤول'),
        ),
        migrations.AddField(
            model_name='customer',
            name='user',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='customer_profile', to=settings.AUTH_USER_MODEL, verbose_name='حساب دخول العميل'),
        ),
    ]
