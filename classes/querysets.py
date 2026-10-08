import datetime

from django.db import models
from django.db.models.functions import (
    ExtractHour,
    ExtractMinute,
    ExtractWeekDay,
    Mod,
)
from django.utils import timezone

from .timeslots import (
    DJANGO_WEEK_DAY,
    MINUTES_PER_DAY,
    MINUTES_PER_WEEK,
    day_rank,
    utc_offset_minutes,
)


class WeeklyClassQuerySet(models.QuerySet):
    def in_week_order(self):
        return self.order_by(day_rank(), "time")

    def with_week_minute(self, tz):
        # The minute of the week each class starts on as it reads in tz
        # (Monday 00:00 is 0): slot_in_zone() in SQL, to order and filter by.
        return self.annotate(
            week_minute=Mod(
                day_rank() * MINUTES_PER_DAY
                + ExtractHour("time") * 60
                + ExtractMinute("time")
                + utc_offset_minutes(tz)
                + MINUTES_PER_WEEK,
                MINUTES_PER_WEEK,
                output_field=models.IntegerField(),
            )
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
