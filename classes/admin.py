from django.contrib import admin

from .models import Student, Subject, WeeklyClass


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("user", "phone_number")
    list_select_related = ("user",)
    search_fields = ("user__username", "user__email", "phone_number")
    autocomplete_fields = ("user",)

    def get_queryset(self, request):
        # list_select_related does not reach the autocomplete endpoint, which
        # renders each Student through its user.
        return super().get_queryset(request).select_related("user")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "price_40_min", "price_60_min")
    list_filter = ("level",)
    search_fields = ("name",)


@admin.register(WeeklyClass)
class WeeklyClassAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "day", "time", "duration")
    list_filter = ("day", "duration", "subject")
    list_select_related = ("student__user", "subject")
    search_fields = (
        "student__user__username",
        "student__user__email",
        "subject__name",
    )
    autocomplete_fields = ("student", "subject")
