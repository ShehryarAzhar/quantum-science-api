import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils import timezone
from model_bakery import baker
from rest_framework import status

from classes.admin import WeeklyClassAdminForm
from classes.models import Level, Student, Subject, TrialLesson, WeeklyClass
from classes.timeslots import DayOfWeek

KARACHI = ZoneInfo("Asia/Karachi")
CLASH_MESSAGE = "This timeslot is already booked."
FULL_HOUR_MESSAGE = "Classes start on the full hour."
WEEKLY_CLASS_URL = "/admin/classes/weeklyclass/"
TRIAL_LESSON_URL = "/admin/classes/triallesson/"


def t(hour, minute=0):
    return datetime.time(hour, minute)


def make_subject():
    subject = baker.make(
        Subject, price_40_min=Decimal("10.00"), price_60_min=Decimal("15.00")
    )
    subject.levels.set([Level.objects.get(code="o_level")])
    return subject


def make_student():
    user = baker.make(get_user_model())
    return baker.make(Student, user=user, phone_number="+923001234567")


def make_weekly_class(day, time, student=None, subject=None):
    """A weekly class stored on the given UTC day and time."""
    subject = subject or make_subject()
    return baker.make(
        WeeklyClass,
        student=student or make_student(),
        subject=subject,
        level=subject.levels.first(),
        day=day,
        time=time,
        duration=60,
    )


def utc_hour_in_future(hour, days=3):
    return timezone.now().replace(
        hour=hour, minute=0, second=0, microsecond=0
    ) + datetime.timedelta(days=days)


def make_lesson(starts_at, student=None):
    subject = make_subject()
    return baker.make(
        TrialLesson,
        student=student or make_student(),
        subject=subject,
        level=subject.levels.first(),
        starts_at=starts_at,
    )


def form_data(day, time, student=None, subject=None, **overrides):
    """What the admin types: the day and time are in Asia/Karachi."""
    subject = subject or make_subject()
    data = {
        "student": (student or make_student()).pk,
        "subject": subject.pk,
        "level": subject.levels.first().pk,
        "day": day,
        "time": time,
        "duration": 60,
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestWeeklyClassAdminForm:
    def test_if_form_opens_an_existing_class_returns_karachi_day_and_time(self):
        weekly_class = make_weekly_class("monday", t(21))

        form = WeeklyClassAdminForm(instance=weekly_class)

        assert form.initial["day"] == "tuesday"
        assert form.initial["time"] == t(2)

    def test_if_form_opens_a_new_class_returns_no_initial_day_or_time(self):
        form = WeeklyClassAdminForm()

        assert form.initial.get("day") is None
        assert form.initial.get("time") is None

    def test_if_karachi_slot_is_entered_returns_it_saved_in_utc(self):
        form = WeeklyClassAdminForm(data=form_data("wednesday", "15:00"))

        assert form.is_valid(), form.errors
        weekly_class = form.save()

        weekly_class.refresh_from_db()
        assert weekly_class.day == "wednesday"
        assert weekly_class.time == t(10)

    def test_if_karachi_early_morning_is_entered_returns_previous_utc_day(self):
        form = WeeklyClassAdminForm(data=form_data("tuesday", "02:00"))

        assert form.is_valid(), form.errors
        weekly_class = form.save()

        weekly_class.refresh_from_db()
        assert weekly_class.day == "monday"
        assert weekly_class.time == t(21)

    def test_if_monday_early_morning_is_entered_returns_sunday_in_utc(self):
        form = WeeklyClassAdminForm(data=form_data("monday", "03:00"))

        assert form.is_valid(), form.errors
        weekly_class = form.save()

        weekly_class.refresh_from_db()
        assert weekly_class.day == "sunday"
        assert weekly_class.time == t(22)

    def test_if_existing_class_is_saved_unchanged_returns_same_utc_slot(self):
        weekly_class = make_weekly_class("monday", t(21))
        data = form_data(
            "tuesday",
            "02:00",
            student=weekly_class.student,
            subject=weekly_class.subject,
        )

        form = WeeklyClassAdminForm(data=data, instance=weekly_class)

        assert form.is_valid(), form.errors
        form.save()
        weekly_class.refresh_from_db()
        assert weekly_class.day == "monday"
        assert weekly_class.time == t(21)

    def test_if_existing_class_is_moved_returns_new_utc_slot(self):
        weekly_class = make_weekly_class("monday", t(21))
        data = form_data(
            "friday",
            "01:00",
            student=weekly_class.student,
            subject=weekly_class.subject,
        )

        form = WeeklyClassAdminForm(data=data, instance=weekly_class)

        assert form.is_valid(), form.errors
        form.save()
        weekly_class.refresh_from_db()
        assert weekly_class.day == "thursday"
        assert weekly_class.time == t(20)

    def test_if_entry_lands_on_a_taken_utc_slot_returns_clash_error(self):
        make_weekly_class("monday", t(21))

        # Tuesday 02:00 in Karachi is Monday 21:00 UTC.
        form = WeeklyClassAdminForm(data=form_data("tuesday", "02:00"))

        assert not form.is_valid()
        assert CLASH_MESSAGE in form.non_field_errors()
        assert WeeklyClass.objects.count() == 1

    def test_if_entry_matches_a_utc_slot_only_by_its_digits_returns_valid(self):
        # A class stored on Tuesday 02:00 UTC is Tuesday 07:00 in Karachi, so
        # typing Tuesday 02:00 (Karachi) does not clash with it.
        make_weekly_class("tuesday", t(2))

        form = WeeklyClassAdminForm(data=form_data("tuesday", "02:00"))

        assert form.is_valid(), form.errors

    def test_if_entry_lands_on_an_upcoming_trial_lesson_returns_clash_error(self):
        starts_at = utc_hour_in_future(21)
        make_lesson(starts_at)
        utc_day = DayOfWeek.values[starts_at.weekday()]
        karachi_day = DayOfWeek.values[(starts_at.weekday() + 1) % 7]

        # 21:00 UTC is 02:00 the next day in Karachi.
        form = WeeklyClassAdminForm(data=form_data(karachi_day, "02:00"))

        assert not form.is_valid()
        assert CLASH_MESSAGE in form.non_field_errors()
        assert not WeeklyClass.objects.filter(day=utc_day).exists()

    def test_if_entry_is_not_on_the_full_hour_returns_error_on_time(self):
        form = WeeklyClassAdminForm(data=form_data("tuesday", "02:30"))

        assert not form.is_valid()
        assert FULL_HOUR_MESSAGE in form.errors["time"]
        assert WeeklyClass.objects.count() == 0

    def test_if_invalid_form_is_shown_again_returns_what_was_typed(self):
        make_weekly_class("monday", t(21))

        form = WeeklyClassAdminForm(data=form_data("tuesday", "02:00"))

        assert not form.is_valid()
        assert form["day"].value() == "tuesday"
        assert form["time"].value() == "02:00"

    def test_if_form_is_rendered_returns_labels_naming_the_timezone(self):
        form = WeeklyClassAdminForm()

        assert form.fields["day"].label == "Day (PKT)"
        assert form.fields["time"].label == "Time (PKT)"


@pytest.mark.django_db
class TestWeeklyClassAdminPages:
    def test_if_class_is_added_through_the_admin_returns_it_saved_in_utc(
        self, admin_client
    ):
        response = admin_client.post(
            f"{WEEKLY_CLASS_URL}add/", form_data("tuesday", "02:00")
        )

        assert response.status_code == status.HTTP_302_FOUND
        weekly_class = WeeklyClass.objects.get()
        assert weekly_class.day == "monday"
        assert weekly_class.time == t(21)

    def test_if_change_page_is_opened_returns_karachi_time_in_the_form(
        self, admin_client
    ):
        weekly_class = make_weekly_class("monday", t(21))

        response = admin_client.get(f"{WEEKLY_CLASS_URL}{weekly_class.id}/change/")

        assert response.status_code == status.HTTP_200_OK
        form = response.context["adminform"].form
        assert form.initial["day"] == "tuesday"
        assert form.initial["time"] == t(2)

    def test_if_list_is_opened_returns_karachi_day_and_time_columns(
        self, admin_client
    ):
        weekly_class = make_weekly_class("monday", t(21))
        model_admin = admin.site._registry[WeeklyClass]

        response = admin_client.get(WEEKLY_CLASS_URL)

        assert response.status_code == status.HTTP_200_OK
        assert model_admin.local_day(weekly_class) == "Tuesday"
        assert model_admin.local_time(weekly_class) == t(2)
        content = response.content.decode()
        assert "(PKT)" in content
        assert "Tuesday" in content

    def test_if_list_is_opened_returns_classes_in_karachi_week_order(
        self, admin_client
    ):
        # In UTC order: monday 02:00, monday 21:00, sunday 20:00.
        # In Karachi: Monday 07:00, Tuesday 02:00, Monday 01:00.
        monday_morning = make_weekly_class("monday", t(2))
        tuesday_night = make_weekly_class("monday", t(21))
        monday_night = make_weekly_class("sunday", t(20))

        response = admin_client.get(WEEKLY_CLASS_URL)

        assert list(response.context["cl"].result_list) == [
            monday_night,
            monday_morning,
            tuesday_night,
        ]

    def test_if_list_is_filtered_by_karachi_day_returns_that_days_classes(
        self, admin_client
    ):
        stored_monday_shown_tuesday = make_weekly_class("monday", t(21))
        stored_tuesday_shown_tuesday = make_weekly_class("tuesday", t(10))
        make_weekly_class("monday", t(10))
        make_weekly_class("tuesday", t(20))

        response = admin_client.get(f"{WEEKLY_CLASS_URL}?local_day=tuesday")

        assert list(response.context["cl"].result_list) == [
            stored_monday_shown_tuesday,
            stored_tuesday_shown_tuesday,
        ]

    def test_if_list_is_filtered_by_monday_returns_class_stored_on_sunday(
        self, admin_client
    ):
        stored_sunday = make_weekly_class("sunday", t(20))
        make_weekly_class("sunday", t(10))

        response = admin_client.get(f"{WEEKLY_CLASS_URL}?local_day=monday")

        assert list(response.context["cl"].result_list) == [stored_sunday]


@pytest.mark.django_db
class TestTrialLessonAdminPages:
    def test_if_list_has_lessons_returns_200(self, admin_client):
        # With date_hierarchy this page needed MySQL's timezone tables.
        make_lesson(utc_hour_in_future(2))
        make_lesson(utc_hour_in_future(21, days=40))

        response = admin_client.get(TRIAL_LESSON_URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.context["cl"].result_count == 2

    def test_if_list_is_filtered_to_today_returns_todays_lesson(
        self, admin_client
    ):
        this_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
        today = make_lesson(this_hour)
        make_lesson(this_hour + datetime.timedelta(days=3))
        changelist = admin_client.get(TRIAL_LESSON_URL).context["cl"]
        date_filter = next(
            spec
            for spec in changelist.filter_specs
            if getattr(spec, "field_path", None) == "starts_at"
        )
        today_link = next(
            choice["query_string"]
            for choice in date_filter.choices(changelist)
            if choice["display"] == "Today"
        )

        response = admin_client.get(f"{TRIAL_LESSON_URL}{today_link}")

        assert response.status_code == status.HTTP_200_OK
        assert list(response.context["cl"].result_list) == [today]

    def test_if_change_page_is_opened_returns_karachi_time_in_the_form(
        self, admin_client
    ):
        # 02:00 UTC is 07:00 in Karachi.
        lesson = make_lesson(utc_hour_in_future(2))

        response = admin_client.get(f"{TRIAL_LESSON_URL}{lesson.id}/change/")

        assert response.status_code == status.HTTP_200_OK
        assert 'value="07:00:00"' in response.content.decode()

    def test_if_karachi_time_is_saved_through_the_admin_returns_it_in_utc(
        self, admin_client
    ):
        lesson = make_lesson(utc_hour_in_future(2))
        local_date = timezone.localtime(lesson.starts_at, KARACHI).date()

        response = admin_client.post(
            f"{TRIAL_LESSON_URL}{lesson.id}/change/",
            {
                "student": lesson.student.pk,
                "subject": lesson.subject.pk,
                "level": lesson.level.pk,
                "starts_at_0": local_date.isoformat(),
                "starts_at_1": "09:00:00",
            },
        )

        assert response.status_code == status.HTTP_302_FOUND
        lesson.refresh_from_db()
        # 09:00 in Karachi is 04:00 UTC.
        assert lesson.starts_at == datetime.datetime.combine(
            local_date, t(4), tzinfo=datetime.UTC
        )


@pytest.mark.django_db
class TestBookingNames:
    def test_if_utc_is_active_returns_weekly_class_name_in_utc(self):
        weekly_class = make_weekly_class("monday", t(21))

        assert "Monday 21:00" in str(weekly_class)

    def test_if_karachi_is_active_returns_weekly_class_name_in_karachi(self):
        weekly_class = make_weekly_class("monday", t(21))

        with timezone.override(KARACHI):
            assert "Tuesday 02:00" in str(weekly_class)

    def test_if_utc_is_active_returns_trial_lesson_name_in_utc(self):
        lesson = make_lesson(utc_hour_in_future(21))

        assert f"{lesson.starts_at:%Y-%m-%d} 21:00" in str(lesson)

    def test_if_karachi_is_active_returns_trial_lesson_name_in_karachi(self):
        lesson = make_lesson(utc_hour_in_future(21))
        next_day = lesson.starts_at.date() + datetime.timedelta(days=1)

        with timezone.override(KARACHI):
            assert f"{next_day:%Y-%m-%d} 02:00" in str(lesson)
