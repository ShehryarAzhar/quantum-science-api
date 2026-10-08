import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from model_bakery import baker
from rest_framework import status

from classes.models import Level, Student, Subject, TrialLesson, WeeklyClass

SCHEDULE_KEYS = {"weekly_classes", "trial_lesson", "weekly_cost"}
CLASS_KEYS = {"id", "subject", "level", "day", "day_display", "time", "duration", "price"}
LESSON_KEYS = {"id", "subject", "level", "starts_at", "completed"}
SUBJECT_KEYS = {"id", "name", "levels"}
LEVEL_KEYS = {"code", "name"}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@pytest.fixture
def get_schedule(api_client):
    def do_get_schedule():
        return api_client.get("/schedule/")
    return do_get_schedule


def get_level(code):
    return Level.objects.get(code=code)


def make_subject(levels=("o_level",), price_40="10.00", price_60="15.00", **kwargs):
    subject = baker.make(
        Subject,
        price_40_min=Decimal(price_40),
        price_60_min=Decimal(price_60),
        **kwargs,
    )
    subject.levels.set([get_level(code) for code in levels])
    return subject


def make_student():
    user = baker.make(get_user_model())
    student = baker.make(Student, user=user, phone_number="+923001234567")
    return user, student


def make_weekly_class(student, day="monday", hour=10, duration=60, subject=None):
    subject = subject or make_subject()
    return baker.make(
        WeeklyClass,
        student=student,
        subject=subject,
        level=subject.levels.first(),
        day=day,
        time=datetime.time(hour, 0),
        duration=duration,
    )


def future_hour(days=3):
    now = timezone.now().replace(minute=0, second=0, microsecond=0)
    return now + datetime.timedelta(days=days)


def make_lesson(student, starts_at=None, subject=None, completed=False):
    subject = subject or make_subject()
    return baker.make(
        TrialLesson,
        student=student,
        subject=subject,
        level=subject.levels.first(),
        starts_at=starts_at or future_hour(),
        completed=completed,
    )


def money(value):
    return Decimal(str(value))


@pytest.mark.django_db
class TestGetSchedule:
    def test_if_user_is_anonymous_returns_401(self, get_schedule):
        response = get_schedule()

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_user_has_no_student_returns_403(self, get_schedule, authenticate):
        authenticate(baker.make(get_user_model()))

        response = get_schedule()

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_if_superuser_has_no_student_returns_403(self, get_schedule, authenticate):
        authenticate(baker.make(get_user_model(), is_superuser=True, is_staff=True))

        response = get_schedule()

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_if_student_has_bookings_returns_exactly_three_top_level_keys(
        self, get_schedule, authenticate
    ):
        user, student = make_student()
        authenticate(user)
        make_weekly_class(student)
        make_lesson(student)

        response = get_schedule()

        assert response.status_code == status.HTTP_200_OK
        assert set(response.json().keys()) == SCHEDULE_KEYS
        assert isinstance(response.json()["weekly_classes"], list)
        assert isinstance(response.json()["trial_lesson"], dict)

    def test_if_student_has_no_bookings_returns_empty_schedule(self, get_schedule, authenticate):
        user, _ = make_student()
        authenticate(user)

        response = get_schedule()

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["weekly_classes"] == []
        assert body["trial_lesson"] is None
        assert money(body["weekly_cost"]) == Decimal("0.00")

    def test_weekly_class_has_expected_shape(self, get_schedule, authenticate):
        user, student = make_student()
        authenticate(user)
        subject = make_subject(levels=("o_level", "a_level"))
        weekly_class = make_weekly_class(student, subject=subject, duration=60)

        response = get_schedule()

        item = response.json()["weekly_classes"][0]
        assert set(item.keys()) == CLASS_KEYS
        assert set(item["subject"].keys()) == SUBJECT_KEYS
        assert item["subject"]["id"] == subject.id
        assert item["subject"]["name"] == subject.name
        assert [lvl["code"] for lvl in item["subject"]["levels"]] == ["o_level", "a_level"]
        assert all(set(lvl.keys()) == LEVEL_KEYS for lvl in item["subject"]["levels"])
        assert set(item["level"].keys()) == LEVEL_KEYS
        assert item["level"]["code"] == weekly_class.level.code
        assert item["id"] == weekly_class.id
        assert item["day"] == "monday"
        assert item["day_display"] == "Monday"
        assert item["time"] == "10:00:00"
        assert item["duration"] == 60

    def test_if_class_is_40_minutes_price_is_40_minute_price(self, get_schedule, authenticate):
        user, student = make_student()
        authenticate(user)
        make_weekly_class(student, duration=40, subject=make_subject(price_40="7.50", price_60="12.25"))

        response = get_schedule()

        assert money(response.json()["weekly_classes"][0]["price"]) == Decimal("7.50")

    def test_if_class_is_60_minutes_price_is_60_minute_price(self, get_schedule, authenticate):
        user, student = make_student()
        authenticate(user)
        make_weekly_class(student, duration=60, subject=make_subject(price_40="7.50", price_60="12.25"))

        response = get_schedule()

        assert money(response.json()["weekly_classes"][0]["price"]) == Decimal("12.25")

    def test_if_same_subject_has_different_durations_each_class_gets_own_price(
        self, get_schedule, authenticate
    ):
        user, student = make_student()
        authenticate(user)
        subject = make_subject(price_40="7.50", price_60="12.25")
        make_weekly_class(student, day="monday", hour=10, duration=40, subject=subject)
        make_weekly_class(student, day="tuesday", hour=10, duration=60, subject=subject)

        response = get_schedule()

        body = response.json()
        prices = {item["duration"]: money(item["price"]) for item in body["weekly_classes"]}
        assert prices == {40: Decimal("7.50"), 60: Decimal("12.25")}
        assert money(body["weekly_cost"]) == Decimal("19.75")

    def test_if_one_class_weekly_cost_equals_its_price(self, get_schedule, authenticate):
        user, student = make_student()
        authenticate(user)
        make_weekly_class(student, duration=60, subject=make_subject(price_40="7.50", price_60="30.00"))

        response = get_schedule()

        assert money(response.json()["weekly_cost"]) == Decimal("30.00")

    def test_if_classes_have_different_subjects_and_durations_weekly_cost_is_sum(
        self, get_schedule, authenticate
    ):
        user, student = make_student()
        authenticate(user)
        physics = make_subject(price_40="20.00", price_60="30.00")
        maths = make_subject(price_40="25.00", price_60="35.00")
        make_weekly_class(student, day="monday", hour=16, duration=60, subject=physics)
        make_weekly_class(student, day="wednesday", hour=10, duration=40, subject=maths)

        response = get_schedule()

        body = response.json()
        prices = [money(item["price"]) for item in body["weekly_classes"]]
        assert prices == [Decimal("30.00"), Decimal("25.00")]
        assert money(body["weekly_cost"]) == Decimal("55.00")
        assert money(body["weekly_cost"]) == sum(prices)

    def test_if_classes_share_a_subject_weekly_cost_is_sum(self, get_schedule, authenticate):
        user, student = make_student()
        authenticate(user)
        subject = make_subject(price_40="8.00", price_60="14.00")
        make_weekly_class(student, day="monday", hour=9, duration=60, subject=subject)
        make_weekly_class(student, day="tuesday", hour=9, duration=60, subject=subject)
        make_weekly_class(student, day="friday", hour=9, duration=40, subject=subject)

        response = get_schedule()

        body = response.json()
        assert money(body["weekly_cost"]) == Decimal("36.00")
        assert money(body["weekly_cost"]) == sum(money(i["price"]) for i in body["weekly_classes"])

    def test_if_prices_need_exact_arithmetic_weekly_cost_is_exact(self, get_schedule, authenticate):
        user, student = make_student()
        authenticate(user)
        cheap = make_subject(price_40="0.10", price_60="0.50")
        other = make_subject(price_40="0.20", price_60="0.60")
        make_weekly_class(student, day="monday", duration=40, subject=cheap)
        make_weekly_class(student, day="tuesday", duration=40, subject=other)

        response = get_schedule()

        assert money(response.json()["weekly_cost"]) == Decimal("0.30")

    def test_if_subject_is_free_class_price_is_zero_and_adds_nothing(
        self, get_schedule, authenticate
    ):
        user, student = make_student()
        authenticate(user)
        free = make_subject(price_40="0.00", price_60="0.00")
        paid = make_subject(price_40="5.00", price_60="9.00")
        make_weekly_class(student, day="monday", duration=60, subject=free)
        make_weekly_class(student, day="tuesday", duration=60, subject=paid)

        response = get_schedule()

        body = response.json()
        prices = [money(item["price"]) for item in body["weekly_classes"]]
        assert prices == [Decimal("0.00"), Decimal("9.00")]
        assert money(body["weekly_cost"]) == Decimal("9.00")

    def test_if_student_has_only_trial_lesson_weekly_cost_is_zero(self, get_schedule, authenticate):
        user, student = make_student()
        authenticate(user)
        lesson = make_lesson(student, subject=make_subject(price_40="20.00", price_60="30.00"))

        response = get_schedule()

        body = response.json()
        assert body["weekly_classes"] == []
        assert body["trial_lesson"]["id"] == lesson.id
        assert money(body["weekly_cost"]) == Decimal("0.00")

    def test_if_trial_lesson_is_added_weekly_cost_does_not_change(self, get_schedule, authenticate):
        user, student = make_student()
        authenticate(user)
        make_weekly_class(student, duration=60, subject=make_subject(price_40="20.00", price_60="30.00"))
        before = money(get_schedule().json()["weekly_cost"])
        make_lesson(student, subject=make_subject(price_40="99.00", price_60="199.00"))

        response = get_schedule()

        assert before == Decimal("30.00")
        assert money(response.json()["weekly_cost"]) == before

    def test_trial_lesson_has_expected_shape_in_utc(self, get_schedule, authenticate):
        user, student = make_student()
        authenticate(user)
        starts_at = future_hour(days=4)
        subject = make_subject(levels=("o_level", "a_level"))
        lesson = make_lesson(student, starts_at=starts_at, subject=subject)

        response = get_schedule()

        item = response.json()["trial_lesson"]
        assert set(item.keys()) == LESSON_KEYS
        assert set(item["subject"].keys()) == SUBJECT_KEYS
        assert set(item["level"].keys()) == LEVEL_KEYS
        assert item["id"] == lesson.id
        assert item["subject"]["id"] == subject.id
        assert item["level"]["code"] == lesson.level.code
        assert item["starts_at"] == starts_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        assert item["completed"] is False

    def test_if_trial_lesson_is_completed_it_is_still_returned(self, get_schedule, authenticate):
        user, student = make_student()
        authenticate(user)
        lesson = make_lesson(student, completed=True)

        response = get_schedule()

        item = response.json()["trial_lesson"]
        assert item["id"] == lesson.id
        assert item["completed"] is True

    def test_if_trial_lesson_has_passed_it_is_still_returned(self, get_schedule, authenticate):
        user, student = make_student()
        authenticate(user)
        lesson = make_lesson(student, starts_at=future_hour(days=-3))

        response = get_schedule()

        item = response.json()["trial_lesson"]
        assert item["id"] == lesson.id
        assert item["completed"] is False

    def test_if_other_student_has_bookings_they_are_not_returned(self, get_schedule, authenticate):
        user, student = make_student()
        authenticate(user)
        _, other = make_student()
        mine = make_weekly_class(student, day="monday", subject=make_subject(price_60="10.00"))
        make_weekly_class(other, day="tuesday", duration=60, subject=make_subject(price_60="50.00"))
        make_lesson(other)

        response = get_schedule()

        body = response.json()
        assert [item["id"] for item in body["weekly_classes"]] == [mine.id]
        assert body["trial_lesson"] is None
        assert money(body["weekly_cost"]) == Decimal("10.00")

    def test_if_student_has_no_bookings_while_other_has_returns_empty_schedule(
        self, get_schedule, authenticate
    ):
        user, _ = make_student()
        authenticate(user)
        _, other = make_student()
        make_weekly_class(other)
        make_lesson(other)

        response = get_schedule()

        body = response.json()
        assert body["weekly_classes"] == []
        assert body["trial_lesson"] is None
        assert money(body["weekly_cost"]) == Decimal("0.00")

    def test_weekly_classes_are_ordered_by_weekday_then_time(self, get_schedule, authenticate):
        user, student = make_student()
        authenticate(user)
        slots = [
            ("sunday", 8),
            ("wednesday", 15),
            ("monday", 18),
            ("wednesday", 9),
            ("saturday", 12),
            ("monday", 7),
            ("friday", 10),
        ]
        for day, hour in slots:
            make_weekly_class(student, day=day, hour=hour)

        response = get_schedule()

        result = [(i["day"], i["time"]) for i in response.json()["weekly_classes"]]
        assert result == sorted(
            [(day, f"{hour:02d}:00:00") for day, hour in slots],
            key=lambda s: (DAYS.index(s[0]), s[1]),
        )

    def test_if_subject_price_changes_schedule_shows_new_price_and_cost(
        self, get_schedule, authenticate
    ):
        user, student = make_student()
        authenticate(user)
        subject = make_subject(price_40="10.00", price_60="30.00")
        make_weekly_class(student, duration=60, subject=subject)
        assert money(get_schedule().json()["weekly_cost"]) == Decimal("30.00")
        subject.price_60_min = Decimal("42.50")
        subject.save()

        response = get_schedule()

        body = response.json()
        assert money(body["weekly_classes"][0]["price"]) == Decimal("42.50")
        assert money(body["weekly_cost"]) == Decimal("42.50")

    def test_query_count_does_not_grow_with_number_of_classes(self, api_client, authenticate):
        user_one, student_one = make_student()
        make_weekly_class(student_one, day="monday", subject=make_subject(levels=("o_level", "a_level")))
        user_many, student_many = make_student()
        for index, day in enumerate(DAYS[:5]):
            subject = make_subject(levels=("o_level", "a_level", "university"))
            make_weekly_class(student_many, day=day, hour=9 + index, subject=subject)

        authenticate(user_one)
        with CaptureQueriesContext(connection) as one_class:
            api_client.get("/schedule/")
        authenticate(user_many)
        with CaptureQueriesContext(connection) as many_classes:
            response = api_client.get("/schedule/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["weekly_classes"]) == 5
        assert len(many_classes) == len(one_class)


@pytest.mark.django_db
class TestScheduleReadOnly:
    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_if_method_is_a_write_returns_405_and_changes_nothing(
        self, api_client, authenticate, method
    ):
        user, student = make_student()
        authenticate(user)
        make_weekly_class(student)
        make_lesson(student)

        response = getattr(api_client, method)("/schedule/", {})

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert WeeklyClass.objects.filter(student=student).count() == 1
        assert TrialLesson.objects.filter(student=student).count() == 1


@pytest.mark.django_db
class TestWeeklyClassPriceProperty:
    def test_if_duration_is_40_price_is_40_minute_price(self):
        _, student = make_student()
        weekly_class = make_weekly_class(
            student, duration=40, subject=make_subject(price_40="7.50", price_60="12.25")
        )

        assert weekly_class.price == Decimal("7.50")
        assert isinstance(weekly_class.price, Decimal)

    def test_if_duration_is_60_price_is_60_minute_price(self):
        _, student = make_student()
        weekly_class = make_weekly_class(
            student, duration=60, subject=make_subject(price_40="7.50", price_60="12.25")
        )

        assert weekly_class.price == Decimal("12.25")
        assert isinstance(weekly_class.price, Decimal)


@pytest.mark.django_db
class TestClassesRouteUnchanged:
    def test_if_student_lists_classes_there_is_no_price(self, api_client, authenticate):
        user, student = make_student()
        authenticate(user)
        make_weekly_class(student)

        response = api_client.get("/classes/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        items = data["results"] if isinstance(data, dict) else data
        assert len(items) == 1
        assert "price" not in items[0]
