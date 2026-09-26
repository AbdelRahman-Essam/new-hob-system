import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('feed', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('view', 'مشاهدة فقط'), ('edit', 'تعديل (إضافة وتعديل البيانات)'), ('admin', 'مدير كامل الصلاحيات')], default='view', max_length=10, verbose_name='الصلاحية')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['region', 'name'], name='feed_custom_region__b2e6b1_idx'),
        ),
        migrations.AddIndex(
            model_name='feedtransaction',
            index=models.Index(fields=['customer', '-date'], name='feed_feedtr_custome_2f7a3d_idx'),
        ),
        migrations.AddIndex(
            model_name='feedtransaction',
            index=models.Index(fields=['due_date'], name='feed_feedtr_due_dat_9c1e44_idx'),
        ),
    ]
