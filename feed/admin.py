from django.contrib import admin
from .models import AppSettings, Customer, FeedTransaction, Profile, Region


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "phone", "rep", "user")
    list_filter = ("region", "rep")
    search_fields = ("name", "phone", "farm_name")
    autocomplete_fields = ("rep", "user")


for m in (Region, FeedTransaction, AppSettings, Profile):
    admin.site.register(m)
