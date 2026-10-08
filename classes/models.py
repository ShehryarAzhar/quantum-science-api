import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

PHONE_NUMBER_MAX_LENGTH = 20

TIMESLOT_TAKEN_MESSAGE = "This timeslot is already booked."
TIMESLOT_CONSTRAINT_NAME = "weekly_class_unique_timeslot"

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


class SubjectLevel(models.TextChoices):
    ALL_GRADES = "all_grades", "All Grades (1-O Level)"
    O_LEVEL = "o_level", "O Level"
    O_A_LEVEL = "o_a_level", "O/A Level"
    UNIVERSITY = "university", "University Level"


class Subject(models.Model):
    Level = SubjectLevel

    name = models.CharField(max_length=100, unique=True)
    level = models.CharField(max_length=20, choices=SubjectLevel.choices)
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
                condition=models.Q(level__in=SubjectLevel.values),
                name="subject_level_valid",
            ),
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


class ClassDuration(models.IntegerChoices):
    FORTY = 40, "40 minutes"
    SIXTY = 60, "60 minutes"


def validate_full_hour(value):
    if value.minute or value.second or value.microsecond:
        raise ValidationError("Classes start on the full hour.")


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

    def __str__(self):
        return (
            f"{self.subject} — {self.get_day_display()} "
            f"{self.time:%H:%M} ({self.student})"
        )
