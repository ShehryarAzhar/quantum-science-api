from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from classes.models import Student

from .models import User


class StudentInline(admin.StackedInline):
    model = Student
    can_delete = False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [StudentInline]
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "usable_password",
                    "first_name",
                    "last_name",
                    "email",
                    "password1",
                    "password2",
                ),
            },
        ),
    )
