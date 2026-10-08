import datetime
from zoneinfo import ZoneInfo

import pytest

from classes.timeslots import DayOfWeek, slot_in_zone, slot_to_utc

KARACHI = ZoneInfo("Asia/Karachi")
KOLKATA = ZoneInfo("Asia/Kolkata")
UTC = datetime.UTC


def t(hour, minute=0):
    return datetime.time(hour, minute)


class TestSlotInZone:
    def test_if_utc_evening_returns_next_day_in_karachi(self):
        assert slot_in_zone("monday", t(21), KARACHI) == ("tuesday", t(2))

    def test_if_utc_midday_returns_same_day_in_karachi(self):
        assert slot_in_zone("wednesday", t(10), KARACHI) == ("wednesday", t(15))

    def test_if_last_utc_hour_before_rollover_returns_same_day(self):
        assert slot_in_zone("monday", t(18), KARACHI) == ("monday", t(23))

    def test_if_first_utc_hour_of_rollover_returns_next_day_midnight(self):
        assert slot_in_zone("monday", t(19), KARACHI) == ("tuesday", t(0))

    def test_if_sunday_evening_utc_returns_monday_in_karachi(self):
        # The week wraps: Sunday is the last day code, Monday the first.
        assert slot_in_zone("sunday", t(20), KARACHI) == ("monday", t(1))

    def test_if_time_has_minutes_returns_them_converted(self):
        assert slot_in_zone("monday", t(21, 30), KARACHI) == ("tuesday", t(2, 30))

    def test_if_zone_has_a_half_hour_offset_returns_shifted_minutes(self):
        # Asia/Kolkata is UTC+5:30: the whole time moves, not only the hour.
        assert slot_in_zone("monday", t(18, 45), KOLKATA) == ("tuesday", t(0, 15))

    def test_if_zone_is_utc_returns_the_slot_unchanged(self):
        assert slot_in_zone("sunday", t(23), UTC) == ("sunday", t(23))

    def test_if_time_has_seconds_returns_them_unchanged(self):
        day, time = slot_in_zone("monday", datetime.time(21, 0, 30), KARACHI)

        assert (day, time) == ("tuesday", datetime.time(2, 0, 30))


class TestSlotToUtc:
    def test_if_karachi_early_morning_returns_previous_day_in_utc(self):
        assert slot_to_utc("monday", t(3), KARACHI) == ("sunday", t(22))

    def test_if_karachi_afternoon_returns_same_day_in_utc(self):
        assert slot_to_utc("wednesday", t(15), KARACHI) == ("wednesday", t(10))

    def test_if_last_karachi_hour_before_rollover_returns_previous_day(self):
        assert slot_to_utc("tuesday", t(4), KARACHI) == ("monday", t(23))

    def test_if_first_karachi_hour_after_rollover_returns_same_day_midnight(self):
        assert slot_to_utc("tuesday", t(5), KARACHI) == ("tuesday", t(0))

    def test_if_monday_early_morning_karachi_returns_sunday_in_utc(self):
        # The week wraps backwards: Monday is the first day code.
        assert slot_to_utc("monday", t(2), KARACHI) == ("sunday", t(21))

    def test_if_time_has_minutes_returns_them_converted(self):
        assert slot_to_utc("tuesday", t(2, 30), KARACHI) == ("monday", t(21, 30))

    def test_if_zone_is_utc_returns_the_slot_unchanged(self):
        assert slot_to_utc("monday", t(0), UTC) == ("monday", t(0))


class TestSlotRoundTrip:
    @pytest.mark.parametrize("day", DayOfWeek.values)
    @pytest.mark.parametrize("hour", range(24))
    def test_if_converted_there_and_back_returns_the_same_slot(self, day, hour):
        local = slot_in_zone(day, t(hour), KARACHI)

        assert slot_to_utc(*local, KARACHI) == (day, t(hour))

    def test_if_every_utc_slot_is_converted_returns_distinct_karachi_slots(self):
        # No two UTC slots may land on the same local slot.
        local_slots = {
            slot_in_zone(day, t(hour), KARACHI)
            for day in DayOfWeek.values
            for hour in range(24)
        }

        assert len(local_slots) == 7 * 24
