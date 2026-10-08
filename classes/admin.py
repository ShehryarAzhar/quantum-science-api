from django.contrib import admin

from .models import Student, Subject


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("user", "phone_number")
    list_select_related = ("user",)
    search_fields = ("user__username", "user__email", "phone_number")
    autocomplete_fields = ("user",)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "price_40_min", "price_60_min")
    list_filter = ("level",)
    search_fields = ("name",)
