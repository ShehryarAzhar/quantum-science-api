import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from .constants import (
    PHONE_NUMBER_MAX_LENGTH,
    TIMESLOT_CONSTRAINT_NAME,
    TIMESLOT_TAKEN_MESSAGE,
    TRIAL_LESSON_FULL_HOUR_CONSTRAINT_NAME,
    TRIAL_LESSON_TIMESLOT_CONSTRAINT_NAME,
)
from .querysets import TrialLessonQuerySet, WeeklyClassQuerySet
from .rules import (
    level_not_in_subject_error,
    trial_lesson_clash_error,
    weekly_class_clash_error,
)
from .timeslots import DayOfWeek, slot_in_zone
from .validators import (
    phone_number_validator,
    subject_slug_validator,
    validate_full_hour,
)


class Student(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student",
    )
    phone_number = models.CharField(
        max_length=PHONE_NUMBER_MAX_LENGTH,
        validators=[phone_number_validator],
    )

    def __str__(self):
        return self.user.get_username()


class Level(models.Model):
    code = models.SlugField(max_length=20, unique=True)
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        # The order the data migration creates the levels in.
        ordering = ["id"]

    def __str__(self):
        return self.name


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)
    # The subject's public URL on the frontend: never rebuilt from the name.
    slug = models.SlugField(
        max_length=100,
        unique=True,
        validators=[subject_slug_validator],
    )
    description = models.TextField(blank=True)
    levels = models.ManyToManyField(Level, related_name="subjects")
    price_40_min = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    price_60_min = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price_40_min__gte=0),
                name="subject_price_40_min_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(price_60_min__gte=0),
                name="subject_price_60_min_gte_0",
            ),
        ]

    def __str__(self):
        return self.name


class ClassDuration(models.IntegerChoices):
    FORTY = 40, "40 minutes"
    SIXTY = 60, "60 minutes"


class WeeklyClass(models.Model):
    Day = DayOfWeek
    Duration = ClassDuration

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="weekly_classes",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="weekly_classes",
    )
    # The level the student studies the subject at: one of subject.levels.
    level = models.ForeignKey(
        Level,
        on_delete=models.PROTECT,
        related_name="weekly_classes",
    )
    day = models.CharField(max_length=9, choices=DayOfWeek.choices)
    time = models.TimeField(validators=[validate_full_hour])
    duration = models.PositiveSmallIntegerField(choices=ClassDuration.choices)

    objects = WeeklyClassQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "weekly classes"
        constraints = [
            # One class per weekday + hour across all students.
            models.UniqueConstraint(
                fields=["day", "time"],
                name=TIMESLOT_CONSTRAINT_NAME,
                violation_error_message=TIMESLOT_TAKEN_MESSAGE,
            ),
            models.CheckConstraint(
                condition=models.Q(day__in=DayOfWeek.values),
                name="weekly_class_day_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(duration__in=ClassDuration.values),
                name="weekly_class_duration_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    time__in=[datetime.time(hour) for hour in range(24)]
                ),
                name="weekly_class_time_full_hour",
            ),
        ]

    def clean(self):
        # Neither rule can be a database constraint (a many-to-many
        # membership, and rows of another table), so the admin form relies
        # on this and the API on WeeklyClassSerializer.
        errors = {}
        if self.subject_id is not None and self.level_id is not None:
            error = level_not_in_subject_error(self.subject, self.level)
            if error:
                errors["level"] = error
        if self.day and self.time is not None:
            error = trial_lesson_clash_error(self.day, self.time)
            if error:
                errors[NON_FIELD_ERRORS] = error
        if errors:
            raise ValidationError(errors)

    @property
    def price(self):
        # Priced by its own duration, from the subject's current prices.
        if self.duration == ClassDuration.FORTY:
            return self.subject.price_40_min
        return self.subject.price_60_min

    def __str__(self):
        # In the active timezone: the admin's inside the admin, UTC elsewhere.
        day, time = slot_in_zone(
            self.day, self.time, timezone.get_current_timezone()
        )
        return (
            f"{self.subject} — {DayOfWeek(day).label} "
            f"{time:%H:%M} ({self.student})"
        )


class TrialLesson(models.Model):
    # One per student: the one-to-one is the uniqueness constraint.
    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name="trial_lesson",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="trial_lessons",
    )
    # The level the student studies the subject at: one of subject.levels.
    level = models.ForeignKey(
        Level,
        on_delete=models.PROTECT,
        related_name="trial_lessons",
    )
    starts_at = models.DateTimeField(validators=[validate_full_hour])
    completed = models.BooleanField(default=False)

    objects = TrialLessonQuerySet.as_manager()

    class Meta:
        ordering = ["starts_at"]
        constraints = [
            # One trial lesson per date and time across all students.
            models.UniqueConstraint(
                fields=["starts_at"],
                name=TRIAL_LESSON_TIMESLOT_CONSTRAINT_NAME,
                violation_error_message=TIMESLOT_TAKEN_MESSAGE,
            ),
            models.CheckConstraint(
                condition=models.Q(starts_at__minute=0, starts_at__second=0),
                name=TRIAL_LESSON_FULL_HOUR_CONSTRAINT_NAME,
            ),
        ]

    @property
    def is_locked(self):
        # Completed, or its start time has been reached.
        return self.completed or self.starts_at <= timezone.now()

    def clean(self):
        # Neither rule can be a database constraint, so the admin form relies
        # on this and the API on TrialLessonSerializer. A past starts_at is
        # allowed here: only student bookings are refused one.
        errors = {}
        if self.subject_id is not None and self.level_id is not None:
            error = level_not_in_subject_error(self.subject, self.level)
            if error:
                errors["level"] = error
        # A lesson that has passed no longer holds its weekly slot.
        if self.starts_at is not None and self.starts_at > timezone.now():
            error = weekly_class_clash_error(self.starts_at)
            if error:
                errors["starts_at"] = error
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        # In the active timezone: the admin's inside the admin, UTC elsewhere.
        starts_at = timezone.localtime(self.starts_at)
        return (
            f"{self.subject} trial — {starts_at:%Y-%m-%d %H:%M} "
            f"({self.student})"
        )
