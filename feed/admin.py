from django.contrib import admin
from .models import AppSettings, Customer, FeedTransaction, Region
for m in (Region, Customer, FeedTransaction, AppSettings):
    admin.site.register(m)
