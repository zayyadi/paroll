from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.urls import path

from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import CustomUser
from .admin_views import logged_in_users_view


class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    list_display = (
        "email",
        "is_staff",
        "is_active",
    )
    list_filter = (
        "email",
        "is_staff",
        "is_active",
    )
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Permissions",
            {"fields": ("is_staff", "is_active", "groups", "user_permissions")},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_active",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
    )
    search_fields = ("email",)
    ordering = ('email',)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('logged-in-users/', self.admin_site.admin_view(logged_in_users_view), name="logged-in-users"),
        ]
        return my_urls + urls


admin.site.register(CustomUser, CustomUserAdmin)
