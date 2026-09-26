from django.contrib import admin
from .models import AppSettings, Customer, FeedTransaction, Profile, Region
for m in (Region, Customer, FeedTransaction, AppSettings, Profile):
    admin.site.register(m)
