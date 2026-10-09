import datetime

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone

from .constants import FULL_HOUR_MESSAGE

phone_number_validator = RegexValidator(
    regex=r"^\+?[0-9]{7,15}\Z",
    message="Enter a valid phone number: 7 to 15 digits, optionally starting with +.",
)

# Stricter than SlugField's own validator, which also takes capitals and
# underscores: the slug is the subject's public URL on the frontend.
subject_slug_validator = RegexValidator(
    regex=r"^[a-z0-9]+(?:-[a-z0-9]+)*\Z",
    message="Enter a valid slug: lowercase letters, digits and hyphens.",
)


def validate_full_hour(value):
    # A trial lesson passes a datetime: its full hour is judged in UTC.
    if isinstance(value, datetime.datetime) and timezone.is_aware(value):
        value = value.astimezone(datetime.UTC)
    if value.minute or value.second or value.microsecond:
        raise ValidationError(FULL_HOUR_MESSAGE)
