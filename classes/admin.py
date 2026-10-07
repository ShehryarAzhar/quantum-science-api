from django.contrib import admin

from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("user", "phone_number")
    list_select_related = ("user",)
    search_fields = ("user__username", "user__email", "phone_number")
    autocomplete_fields = ("user",)
