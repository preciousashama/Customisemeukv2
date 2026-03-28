
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import CustomUser, EmailVerificationToken, PasswordResetToken


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    ordering      = ["-created_at"]
    list_display  = ("email", "full_name", "role", "is_active",
                     "is_email_verified", "is_staff", "created_at")
    list_filter   = ("role", "is_active", "is_email_verified", "is_staff")
    search_fields = ("email", "full_name")

    fieldsets = (
        (None,                    {"fields": ("email", "password")}),
        (_("Personal info"),      {"fields": ("full_name",)}),
        (_("Permissions"),        {"fields": ("role", "is_active", "is_email_verified",
                                              "is_staff", "is_superuser",
                                              "groups", "user_permissions")}),
        (_("Security"),           {"fields": ("failed_login_attempts", "locked_until",
                                              "last_login_ip")}),
        (_("Important dates"),    {"fields": ("last_login", "created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at", "last_login", "last_login_ip")

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields":  ("email", "full_name", "role", "password1", "password2"),
        }),
    )

    def save_model(self, request, obj, form, change):
        if obj.role == CustomUser.Role.ADMIN:
            obj.is_staff           = True
            obj.is_email_verified  = True
            obj.is_active          = True
        super().save_model(request, obj, form, change)


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display    = ("user", "token", "created_at", "used")
    list_filter     = ("used",)
    search_fields   = ("user__email",)
    readonly_fields = ("token", "created_at")


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display    = ("user", "token", "created_at", "used")
    list_filter     = ("used",)
    search_fields   = ("user__email",)
    readonly_fields = ("token", "created_at")