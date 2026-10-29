from django.contrib import admin

from .models import StaffUser


@admin.register(StaffUser)
class StaffUserAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "mfa_enabled", "created_at")
    list_filter = ("role", "mfa_enabled")
