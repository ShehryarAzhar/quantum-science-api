from django.conf import settings
from django.core.validators import RegexValidator
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
