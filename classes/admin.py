from django import forms
from django.contrib import admin
from django.db.models import Count

from .models import Level, Student, Subject, TrialLesson, WeeklyClass

# The bookings that point at a subject and a level: the Level related name,
# then how one and several of them read in an error.
BOOKING_RELATIONS = (
    ("weekly_classes", "weekly class", "weekly classes"),
    ("trial_lessons", "trial lesson", "trial lessons"),
)


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


@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name",)


class SubjectAdminForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = "__all__"

    def clean_levels(self):
        levels = self.cleaned_data["levels"]
        if self.instance.pk is None:
            return levels
        # A booking must keep a level its subject still has.
        errors = []
        for relation, singular, plural in BOOKING_RELATIONS:
            in_use = (
                Level.objects.filter(**{f"{relation}__subject": self.instance})
                .exclude(pk__in=levels)
                .annotate(booking_count=Count(relation))
            )
            errors += [
                f"{level.name} is used by {level.booking_count} "
                f"{singular if level.booking_count == 1 else plural} "
                "of this subject and cannot be removed."
                for level in in_use
            ]
        if errors:
            raise forms.ValidationError(errors)
        return levels


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    form = SubjectAdminForm
    list_display = ("name", "level_names", "price_40_min", "price_60_min")
    list_filter = ("levels",)
    search_fields = ("name",)
    filter_horizontal = ("levels",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("levels")

    @admin.display(description="levels")
    def level_names(self, subject):
        return ", ".join(level.name for level in subject.levels.all())


@admin.register(WeeklyClass)
class WeeklyClassAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "level", "day", "time", "duration")
    list_filter = ("day", "duration", "subject", "level")
    list_select_related = ("student__user", "subject", "level")
    search_fields = (
        "student__user__username",
        "student__user__email",
        "subject__name",
    )
    autocomplete_fields = ("student", "subject")


@admin.register(TrialLesson)
class TrialLessonAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "level", "starts_at", "completed")
    list_filter = ("completed", "subject", "level")
    list_select_related = ("student__user", "subject", "level")
    date_hierarchy = "starts_at"
    search_fields = (
        "student__user__username",
        "student__user__email",
        "subject__name",
    )
    autocomplete_fields = ("student", "subject")
