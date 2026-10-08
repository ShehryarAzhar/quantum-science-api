from django import forms
from django.contrib import admin
from django.db.models import Count

from .models import Level, Student, Subject, WeeklyClass


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
        # A weekly class must keep a level its subject still has.
        in_use = (
            Level.objects.filter(weekly_classes__subject=self.instance)
            .exclude(pk__in=levels)
            .annotate(class_count=Count("weekly_classes"))
        )
        errors = [
            f"{level.name} is used by {level.class_count} weekly "
            f"class{'' if level.class_count == 1 else 'es'} of this subject "
            "and cannot be removed."
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
