import datetime
from zoneinfo import ZoneInfo

from django import forms
from django.conf import settings
from django.contrib import admin
from django.db.models import Count

from .models import Level, Student, Subject, TrialLesson, WeeklyClass
from .timeslots import MINUTES_PER_DAY, slot_in_zone, slot_to_utc

# The admin shows and accepts this timezone; the database and the API are
# UTC. core.middleware.AdminTimezoneMiddleware activates it, which converts
# datetimes; a weekly class's day and time are converted here.
ADMIN_TIME_ZONE = ZoneInfo(settings.ADMIN_TIME_ZONE)
ADMIN_TZ_NAME = datetime.datetime.now(ADMIN_TIME_ZONE).tzname()

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


class WeeklyClassAdminForm(forms.ModelForm):
    # The admin reads and enters the day and time in the admin timezone; they
    # are stored in UTC.
    class Meta:
        model = WeeklyClass
        fields = "__all__"
        labels = {
            "day": f"Day ({ADMIN_TZ_NAME})",
            "time": f"Time ({ADMIN_TZ_NAME})",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk is not None:
            self.initial["day"], self.initial["time"] = slot_in_zone(
                self.instance.day, self.instance.time, ADMIN_TIME_ZONE
            )

    def clean(self):
        # Model validation runs after this, so the full-hour, clash and trial
        # lesson rules all see the UTC values.
        cleaned_data = super().clean()
        day, time = cleaned_data.get("day"), cleaned_data.get("time")
        if day and time is not None:
            cleaned_data["day"], cleaned_data["time"] = slot_to_utc(
                day, time, ADMIN_TIME_ZONE
            )
        return cleaned_data


class WeeklyClassDayFilter(admin.SimpleListFilter):
    title = f"day ({ADMIN_TZ_NAME})"
    parameter_name = "local_day"

    def lookups(self, request, model_admin):
        return WeeklyClass.Day.choices

    def queryset(self, request, queryset):
        if self.value() not in WeeklyClass.Day.values:
            return queryset
        start = WeeklyClass.Day.values.index(self.value()) * MINUTES_PER_DAY
        return queryset.filter(
            week_minute__gte=start, week_minute__lt=start + MINUTES_PER_DAY
        )


@admin.register(WeeklyClass)
class WeeklyClassAdmin(admin.ModelAdmin):
    form = WeeklyClassAdminForm
    list_display = (
        "student",
        "subject",
        "level",
        "local_day",
        "local_time",
        "duration",
    )
    list_filter = (WeeklyClassDayFilter, "duration", "subject", "level")
    list_select_related = ("student__user", "subject", "level")
    search_fields = (
        "student__user__username",
        "student__user__email",
        "subject__name",
    )
    autocomplete_fields = ("student", "subject")

    def get_queryset(self, request):
        # Monday to Sunday in the admin timezone. Ordered here, not through
        # the ordering attribute, which cannot name an annotation.
        return (
            super()
            .get_queryset(request)
            .with_week_minute(ADMIN_TIME_ZONE)
            .order_by("week_minute")
        )

    @admin.display(description=f"day ({ADMIN_TZ_NAME})", ordering="week_minute")
    def local_day(self, weekly_class):
        day, _ = slot_in_zone(
            weekly_class.day, weekly_class.time, ADMIN_TIME_ZONE
        )
        return WeeklyClass.Day(day).label

    @admin.display(description=f"time ({ADMIN_TZ_NAME})", ordering="week_minute")
    def local_time(self, weekly_class):
        _, time = slot_in_zone(
            weekly_class.day, weekly_class.time, ADMIN_TIME_ZONE
        )
        return time


class TrialLessonAdminForm(forms.ModelForm):
    class Meta:
        model = TrialLesson
        fields = "__all__"
        labels = {"starts_at": f"Starts at ({ADMIN_TZ_NAME})"}


@admin.register(TrialLesson)
class TrialLessonAdmin(admin.ModelAdmin):
    # No date_hierarchy: outside UTC it needs MySQL's timezone tables.
    form = TrialLessonAdminForm
    list_display = (
        "student",
        "subject",
        "level",
        "local_starts_at",
        "completed",
    )
    list_filter = ("completed", "starts_at", "subject", "level")
    list_select_related = ("student__user", "subject", "level")
    search_fields = (
        "student__user__username",
        "student__user__email",
        "subject__name",
    )
    autocomplete_fields = ("student", "subject")

    @admin.display(
        description=f"starts at ({ADMIN_TZ_NAME})", ordering="starts_at"
    )
    def local_starts_at(self, trial_lesson):
        # Django shows it in the active timezone, the admin's.
        return trial_lesson.starts_at
