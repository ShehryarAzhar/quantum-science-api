import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import ExtractHour, ExtractWeekDay
from django.utils import timezone

PHONE_NUMBER_MAX_LENGTH = 20

TIMESLOT_TAKEN_MESSAGE = "This timeslot is already booked."
TIMESLOT_CONSTRAINT_NAME = "weekly_class_unique_timeslot"
LEVEL_NOT_IN_SUBJECT_MESSAGE = "{subject} is not taught at {level}."
FULL_HOUR_MESSAGE = "Classes start on the full hour."
TRIAL_LESSON_TIMESLOT_CONSTRAINT_NAME = "trial_lesson_unique_starts_at"
TRIAL_LESSON_FULL_HOUR_CONSTRAINT_NAME = "trial_lesson_starts_at_full_hour"
TRIAL_LESSON_ALREADY_BOOKED_MESSAGE = "You have already booked a trial lesson."
TRIAL_LESSON_LOCKED_MESSAGE = "This trial lesson can no longer be changed."
STARTS_AT_IN_PAST_MESSAGE = "A trial lesson cannot be booked in the past."

phone_number_validator = RegexValidator(
    regex=r"^\+?[0-9]{7,15}\Z",
    message="Enter a valid phone number: 7 to 15 digits, optionally starting with +.",
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


class DayOfWeek(models.TextChoices):
    # Monday first: the index of a code matches date.weekday().
    MONDAY = "monday", "Monday"
    TUESDAY = "tuesday", "Tuesday"
    WEDNESDAY = "wednesday", "Wednesday"
    THURSDAY = "thursday", "Thursday"
    FRIDAY = "friday", "Friday"
    SATURDAY = "saturday", "Saturday"
    SUNDAY = "sunday", "Sunday"


# The number Django's week_day lookup gives each day: it counts from Sunday.
DJANGO_WEEK_DAY = {
    DayOfWeek.SUNDAY: 1,
    DayOfWeek.MONDAY: 2,
    DayOfWeek.TUESDAY: 3,
    DayOfWeek.WEDNESDAY: 4,
    DayOfWeek.THURSDAY: 5,
    DayOfWeek.FRIDAY: 6,
    DayOfWeek.SATURDAY: 7,
}


class ClassDuration(models.IntegerChoices):
    FORTY = 40, "40 minutes"
    SIXTY = 60, "60 minutes"


def validate_full_hour(value):
    # A trial lesson passes a datetime: its full hour is judged in UTC.
    if isinstance(value, datetime.datetime) and timezone.is_aware(value):
        value = value.astimezone(datetime.UTC)
    if value.minute or value.second or value.microsecond:
        raise ValidationError(FULL_HOUR_MESSAGE)


def level_not_in_subject_error(subject, level):
    # The one place the rule lives: the models' clean() and the serializers
    # all ask here. Returns the message, or None when the level is fine.
    if subject.levels.filter(pk=level.pk).exists():
        return None
    return LEVEL_NOT_IN_SUBJECT_MESSAGE.format(subject=subject, level=level)


def weekly_class_clash_error(starts_at):
    # A trial lesson cannot start on a weekday + hour any weekly class holds.
    # TrialLesson.clean() and the serializer both ask here. Returns the
    # message, or None when the slot is free.
    starts_at = starts_at.astimezone(datetime.UTC)
    day = DayOfWeek.values[starts_at.weekday()]
    if WeeklyClass.objects.filter(day=day, time=starts_at.time()).exists():
        return TIMESLOT_TAKEN_MESSAGE
    return None


def trial_lesson_clash_error(day, time):
    # A weekly class cannot take a slot an upcoming trial lesson occupies.
    # WeeklyClass.clean() and the serializer both ask here. Returns the
    # message, or None when the slot is free.
    if TrialLesson.objects.upcoming().on_weekly_slot(day, time).exists():
        return TIMESLOT_TAKEN_MESSAGE
    return None


class WeeklyClassQuerySet(models.QuerySet):
    def in_week_order(self):
        # The day codes do not sort in week order, so rank them.
        day_rank = models.Case(
            *[
                models.When(day=code, then=models.Value(rank))
                for rank, code in enumerate(DayOfWeek.values)
            ],
            output_field=models.IntegerField(),
        )
        return self.order_by(day_rank, "time")


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

    def __str__(self):
        return (
            f"{self.subject} — {self.get_day_display()} "
            f"{self.time:%H:%M} ({self.student})"
        )


class TrialLessonQuerySet(models.QuerySet):
    def upcoming(self):
        return self.filter(starts_at__gt=timezone.now())

    def on_weekly_slot(self, day, time):
        # Lessons start on the full hour, so the hour alone identifies the
        # slot.
        return self.annotate(
            utc_week_day=ExtractWeekDay("starts_at", tzinfo=datetime.UTC),
            utc_hour=ExtractHour("starts_at", tzinfo=datetime.UTC),
        ).filter(utc_week_day=DJANGO_WEEK_DAY[day], utc_hour=time.hour)


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
        return (
            f"{self.subject} trial — {self.starts_at:%Y-%m-%d %H:%M} "
            f"({self.student})"
        )
