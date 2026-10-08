from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

PHONE_NUMBER_MAX_LENGTH = 20

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
