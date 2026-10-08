import datetime

from django.db import models


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


MINUTES_PER_DAY = 24 * 60
MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY


def utc_offset_minutes(tz):
    # The zone's own offset right now, so nothing hard-codes it.
    offset = datetime.datetime.now(tz).utcoffset()
    return int(offset.total_seconds() // 60)


def _shift_slot(day, time, minutes):
    # A weekly slot has no date, so it is moved as a minute of the week: the
    # day rolls over and the week wraps (Sunday to Monday) in the modulo.
    week_minute = (
        DayOfWeek.values.index(day) * MINUTES_PER_DAY
        + time.hour * 60
        + time.minute
        + minutes
    ) % MINUTES_PER_WEEK
    day_index, day_minute = divmod(week_minute, MINUTES_PER_DAY)
    hour, minute = divmod(day_minute, 60)
    return DayOfWeek.values[day_index], time.replace(hour=hour, minute=minute)


def slot_in_zone(day, time, tz):
    """A weekly class's UTC day and time as they read in tz."""
    return _shift_slot(day, time, utc_offset_minutes(tz))


def slot_to_utc(day, time, tz):
    """A day and time given in tz as the UTC day and time that are stored."""
    return _shift_slot(day, time, -utc_offset_minutes(tz))


def day_rank():
    # The day codes do not sort in week order, so rank them.
    return models.Case(
        *[
            models.When(day=code, then=models.Value(rank))
            for rank, code in enumerate(DayOfWeek.values)
        ],
        output_field=models.IntegerField(),
    )
