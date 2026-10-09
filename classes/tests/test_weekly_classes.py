import datetime
import itertools
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.test.utils import CaptureQueriesContext
from model_bakery import baker
from rest_framework import status

from classes.admin import SubjectAdminForm
from classes.models import Level, Student, Subject, WeeklyClass

DAYS = [
    ("monday", "Monday"),
    ("tuesday", "Tuesday"),
    ("wednesday", "Wednesday"),
    ("thursday", "Thursday"),
    ("friday", "Friday"),
    ("saturday", "Saturday"),
    ("sunday", "Sunday"),
]

SUBJECT_KEYS = {"id", "name", "slug", "levels"}
SLUG_COUNTER = itertools.count(1)
LEVEL_KEYS = {"code", "name"}
CLASS_KEYS = {"id", "subject", "level", "day", "day_display", "time", "duration"}
CLASH_MESSAGE = "This timeslot is already booked."


def get_level(code):
    return Level.objects.get(code=code)


def level_data(code):
    level = get_level(code)
    return {"code": level.code, "name": level.name}


def make_subject(levels=("o_level",), **kwargs):
    defaults = {
        "price_40_min": Decimal("10.00"),
        "price_60_min": Decimal("15.00"),
        "slug": f"subject-{next(SLUG_COUNTER)}",
    }
    defaults.update(kwargs)
    subject = baker.make(Subject, **defaults)
    subject.levels.set([get_level(code) for code in levels])
    return subject


def subject_data(subject):
    return {
        "id": subject.id,
        "name": subject.name,
        "slug": subject.slug,
        "levels": [
            {"code": level.code, "name": level.name} for level in subject.levels.all()
        ],
    }


def make_student():
    user = baker.make(get_user_model())
    student = baker.make(Student, user=user, phone_number="+923001234567")
    return user, student


def make_class(
    student, subject=None, day="monday", hour=16, duration=60, level=None
):
    subject = subject or make_subject()
    return baker.make(
        WeeklyClass,
        student=student,
        subject=subject,
        level=level or subject.levels.first(),
        day=day,
        time=datetime.time(hour),
        duration=duration,
    )


def payload(subject, /, **overrides):
    data = {
        "subject": subject.id,
        "level": subject.levels.first().code,
        "day": "monday",
        "time": "16:00",
        "duration": 60,
    }
    data.update(overrides)
    return data


@pytest.fixture
def student_user(authenticate):
    user, student = make_student()
    authenticate(user)
    return user, student


@pytest.fixture
def list_classes(api_client):
    def do_list():
        return api_client.get("/classes/")

    return do_list


@pytest.fixture
def create_class(api_client):
    def do_create(data):
        return api_client.post("/classes/", data, format="json")

    return do_create


@pytest.fixture
def retrieve_class(api_client):
    def do_retrieve(class_id):
        return api_client.get(f"/classes/{class_id}/")

    return do_retrieve


@pytest.fixture
def put_class(api_client):
    def do_put(class_id, data):
        return api_client.put(f"/classes/{class_id}/", data, format="json")

    return do_put


@pytest.fixture
def patch_class(api_client):
    def do_patch(class_id, data):
        return api_client.patch(f"/classes/{class_id}/", data, format="json")

    return do_patch


@pytest.fixture
def delete_class(api_client):
    def do_delete(class_id):
        return api_client.delete(f"/classes/{class_id}/")

    return do_delete


@pytest.mark.django_db
class TestAccess:
    def test_if_user_is_anonymous_on_list_returns_401(self, list_classes):
        response = list_classes()

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_user_is_anonymous_on_create_returns_401(self, create_class):
        response = create_class({})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_user_is_anonymous_on_retrieve_returns_401(self, retrieve_class):
        response = retrieve_class(1)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_user_is_anonymous_on_put_returns_401(self, put_class):
        response = put_class(1, {})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_user_is_anonymous_on_patch_returns_401(self, patch_class):
        response = patch_class(1, {})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_user_is_anonymous_on_delete_returns_401(self, delete_class):
        response = delete_class(1)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_user_has_no_student_on_list_returns_403(
        self, authenticate, list_classes
    ):
        authenticate()

        response = list_classes()

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_if_user_has_no_student_on_create_returns_403(
        self, authenticate, create_class
    ):
        authenticate()
        subject = make_subject()

        response = create_class(payload(subject))

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert WeeklyClass.objects.count() == 0

    def test_if_user_has_no_student_on_retrieve_returns_403(
        self, authenticate, retrieve_class
    ):
        authenticate()
        _, other = make_student()
        weekly_class = make_class(other)

        response = retrieve_class(weekly_class.id)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_if_user_has_no_student_on_put_returns_403(self, authenticate, put_class):
        authenticate()
        _, other = make_student()
        weekly_class = make_class(other)

        response = put_class(weekly_class.id, payload(weekly_class.subject))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_if_user_has_no_student_on_patch_returns_403(
        self, authenticate, patch_class
    ):
        authenticate()
        _, other = make_student()
        weekly_class = make_class(other)

        response = patch_class(weekly_class.id, {"duration": 40})

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_if_user_has_no_student_on_delete_returns_403(
        self, authenticate, delete_class
    ):
        authenticate()
        _, other = make_student()
        weekly_class = make_class(other)

        response = delete_class(weekly_class.id)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert WeeklyClass.objects.filter(id=weekly_class.id).exists()

    def test_if_user_is_superuser_without_student_returns_403(
        self, api_client, list_classes
    ):
        superuser = baker.make(get_user_model(), is_superuser=True, is_staff=True)
        api_client.force_authenticate(user=superuser)

        response = list_classes()

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestCreateWeeklyClass:
    def test_if_data_is_valid_returns_201(self, student_user, create_class):
        _, student = student_user
        subject = make_subject(name="Physics")

        response = create_class(payload(subject))

        assert response.status_code == status.HTTP_201_CREATED
        assert set(response.data.keys()) == CLASS_KEYS
        assert response.data == {
            "id": response.data["id"],
            "subject": {
                "id": subject.id,
                "name": "Physics",
                "slug": subject.slug,
                "levels": [level_data("o_level")],
            },
            "level": level_data("o_level"),
            "day": "monday",
            "day_display": "Monday",
            "time": "16:00:00",
            "duration": 60,
        }

    def test_if_subject_has_two_levels_both_are_returned_in_subject(
        self, student_user, create_class
    ):
        subject = make_subject(levels=("o_level", "a_level"))

        response = create_class(payload(subject, level="a_level"))

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["subject"]["levels"] == [
            level_data("o_level"),
            level_data("a_level"),
        ]
        assert response.data["level"] == level_data("a_level")

    def test_if_level_is_returned_it_has_only_code_and_name(
        self, student_user, create_class
    ):
        subject = make_subject(levels=("university",))

        response = create_class(payload(subject))

        assert set(response.data["level"].keys()) == LEVEL_KEYS
        assert response.data["level"] == level_data("university")

    @pytest.mark.parametrize(
        "levels, chosen",
        [
            (("a_level",), "a_level"),
            (("o_level", "a_level", "university"), "o_level"),
            (("o_level", "a_level", "university"), "university"),
        ],
    )
    def test_if_level_belongs_to_subject_returns_201(
        self, student_user, create_class, levels, chosen
    ):
        subject = make_subject(levels=levels)

        response = create_class(payload(subject, level=chosen))

        assert response.status_code == status.HTTP_201_CREATED
        assert WeeklyClass.objects.get(id=response.data["id"]).level.code == chosen

    def test_if_level_does_not_belong_to_subject_returns_400(
        self, student_user, create_class
    ):
        subject = make_subject(levels=("o_level", "a_level"))

        response = create_class(payload(subject, level="university"))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "level" in response.data
        assert WeeklyClass.objects.count() == 0

    def test_if_level_does_not_belong_to_single_level_subject_returns_400(
        self, student_user, create_class
    ):
        subject = make_subject(levels=("o_level",))

        response = create_class(payload(subject, level="a_level"))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "level" in response.data
        assert WeeklyClass.objects.count() == 0

    def test_if_level_code_is_unknown_returns_400(self, student_user, create_class):
        subject = make_subject()

        response = create_class(payload(subject, level="primary"))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "level" in response.data
        assert WeeklyClass.objects.count() == 0

    def test_if_level_is_a_nested_object_returns_400(self, student_user, create_class):
        subject = make_subject()

        response = create_class(
            payload(subject, level={"code": "o_level", "name": "O Level"})
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "level" in response.data
        assert WeeklyClass.objects.count() == 0

    def test_if_data_is_valid_class_is_stored_for_logged_in_student(
        self, student_user, create_class
    ):
        _, student = student_user
        subject = make_subject(levels=("o_level", "a_level"))

        response = create_class(
            payload(subject, level="a_level", day="friday", time="09:00", duration=40)
        )

        weekly_class = WeeklyClass.objects.get(id=response.data["id"])
        assert weekly_class.student == student
        assert weekly_class.subject == subject
        assert weekly_class.level == get_level("a_level")
        assert weekly_class.day == "friday"
        assert weekly_class.time == datetime.time(9)
        assert weekly_class.duration == 40

    def test_if_subject_is_returned_it_has_no_price_fields(
        self, student_user, create_class
    ):
        subject = make_subject()

        response = create_class(payload(subject))

        assert set(response.data["subject"].keys()) == SUBJECT_KEYS
        assert "description" not in response.data["subject"]
        assert "price_40_min" not in response.data["subject"]
        assert "price_60_min" not in response.data["subject"]
        assert "description" not in response.data["subject"]
        assert response.data["subject"]["slug"] == subject.slug

    def test_if_student_or_user_in_body_is_ignored_returns_201(
        self, student_user, create_class
    ):
        _, student = student_user
        other_user, other_student = make_student()
        subject = make_subject()

        response = create_class(
            payload(subject, student=other_student.id, user=other_user.id)
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert "student" not in response.data
        assert "user" not in response.data
        assert WeeklyClass.objects.get(id=response.data["id"]).student == student

    @pytest.mark.parametrize("duration", [40, 60])
    def test_if_duration_is_allowed_returns_201(
        self, student_user, create_class, duration
    ):
        subject = make_subject()

        response = create_class(payload(subject, duration=duration))

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["duration"] == duration

    @pytest.mark.parametrize("code, label", DAYS)
    def test_if_day_is_allowed_returns_201_with_day_display(
        self, student_user, create_class, code, label
    ):
        subject = make_subject()

        response = create_class(payload(subject, day=code))

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["day"] == code
        assert response.data["day_display"] == label

    @pytest.mark.parametrize("missing", ["subject", "level", "day", "time", "duration"])
    def test_if_field_is_missing_returns_400(self, student_user, create_class, missing):
        subject = make_subject()
        data = payload(subject)
        del data[missing]

        response = create_class(data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert missing in response.data
        assert WeeklyClass.objects.count() == 0

    def test_if_subject_does_not_exist_returns_400(self, student_user, create_class):
        subject = make_subject()

        response = create_class(payload(subject, subject=subject.id + 1000))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "subject" in response.data
        assert WeeklyClass.objects.count() == 0

    def test_if_subject_is_a_nested_object_returns_400(
        self, student_user, create_class
    ):
        subject = make_subject()

        response = create_class(
            payload(subject, subject={"id": subject.id, "name": subject.name})
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "subject" in response.data
        assert WeeklyClass.objects.count() == 0

    def test_if_day_is_unknown_returns_400(self, student_user, create_class):
        subject = make_subject()

        response = create_class(payload(subject, day="funday"))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "day" in response.data
        assert WeeklyClass.objects.count() == 0

    @pytest.mark.parametrize("duration", [0, 30, 45, 50, 90, -60])
    def test_if_duration_is_not_40_or_60_returns_400(
        self, student_user, create_class, duration
    ):
        subject = make_subject()

        response = create_class(payload(subject, duration=duration))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "duration" in response.data
        assert WeeklyClass.objects.count() == 0

    @pytest.mark.parametrize("time", ["16:00", "16:00:00", "00:00", "23:00"])
    def test_if_time_is_on_the_full_hour_returns_201(
        self, student_user, create_class, time
    ):
        subject = make_subject()

        response = create_class(payload(subject, time=time))

        assert response.status_code == status.HTTP_201_CREATED
        assert WeeklyClass.objects.count() == 1

    def test_if_time_is_midnight_returns_time_with_seconds(
        self, student_user, create_class
    ):
        subject = make_subject()

        response = create_class(payload(subject, time="00:00"))

        assert response.data["time"] == "00:00:00"

    @pytest.mark.parametrize("time", ["16:30", "16:00:01", "16:15"])
    def test_if_time_is_not_on_the_full_hour_returns_400(
        self, student_user, create_class, time
    ):
        subject = make_subject()

        response = create_class(payload(subject, time=time))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "time" in response.data
        assert WeeklyClass.objects.count() == 0

    def test_if_time_is_not_on_the_full_hour_message_is_returned(
        self, student_user, create_class
    ):
        subject = make_subject()

        response = create_class(payload(subject, time="16:30"))

        assert response.data["time"] == ["Classes start on the full hour."]

    def test_if_timeslot_is_taken_by_same_student_returns_400(
        self, student_user, create_class
    ):
        _, student = student_user
        make_class(student, day="monday", hour=16)
        subject = make_subject()

        response = create_class(payload(subject, day="monday", time="16:00"))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["non_field_errors"] == [CLASH_MESSAGE]
        assert WeeklyClass.objects.count() == 1

    def test_if_timeslot_is_taken_by_another_student_returns_400(
        self, student_user, create_class
    ):
        _, other = make_student()
        make_class(other, day="monday", hour=16)
        subject = make_subject()

        response = create_class(payload(subject, day="monday", time="16:00"))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["non_field_errors"] == [CLASH_MESSAGE]
        assert WeeklyClass.objects.count() == 1

    def test_if_40_minute_class_holds_slot_60_minute_booking_returns_400(
        self, student_user, create_class
    ):
        _, other = make_student()
        make_class(other, day="tuesday", hour=10, duration=40)
        subject = make_subject()

        response = create_class(
            payload(subject, day="tuesday", time="10:00", duration=60)
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["non_field_errors"] == [CLASH_MESSAGE]

    def test_if_60_minute_class_holds_slot_40_minute_booking_returns_400(
        self, student_user, create_class
    ):
        _, other = make_student()
        make_class(other, day="tuesday", hour=10, duration=60)
        subject = make_subject()

        response = create_class(
            payload(subject, day="tuesday", time="10:00", duration=40)
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["non_field_errors"] == [CLASH_MESSAGE]

    def test_if_same_time_on_another_day_returns_201(self, student_user, create_class):
        _, other = make_student()
        make_class(other, day="monday", hour=16)
        subject = make_subject()

        response = create_class(payload(subject, day="tuesday", time="16:00"))

        assert response.status_code == status.HTTP_201_CREATED

    def test_if_another_hour_on_same_day_returns_201(self, student_user, create_class):
        _, other = make_student()
        make_class(other, day="monday", hour=16)
        subject = make_subject()

        response = create_class(payload(subject, day="monday", time="17:00"))

        assert response.status_code == status.HTTP_201_CREATED

    def test_if_same_subject_is_booked_in_different_slots_returns_201(
        self, student_user, create_class
    ):
        _, student = student_user
        subject = make_subject()

        first = create_class(payload(subject, day="monday", time="16:00"))
        second = create_class(payload(subject, day="wednesday", time="16:00"))
        third = create_class(payload(subject, day="wednesday", time="17:00"))

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_201_CREATED
        assert third.status_code == status.HTTP_201_CREATED
        assert WeeklyClass.objects.filter(student=student, subject=subject).count() == 3


@pytest.mark.django_db
class TestListWeeklyClasses:
    def test_if_student_has_no_classes_returns_empty_list(
        self, student_user, list_classes
    ):
        response = list_classes()

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_if_classes_exist_returns_only_own_classes(
        self, student_user, list_classes
    ):
        _, student = student_user
        _, other = make_student()
        own = make_class(student, day="monday", hour=9)
        make_class(other, day="tuesday", hour=9)

        response = list_classes()

        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.data] == [own.id]

    def test_if_classes_exist_returns_plain_list_with_expected_shape(
        self, student_user, list_classes
    ):
        _, student = student_user
        subject = make_subject(name="Chemistry", levels=("a_level", "university"))
        weekly_class = make_class(
            student,
            subject=subject,
            level=get_level("university"),
            day="thursday",
            hour=8,
            duration=40,
        )

        response = list_classes()

        assert isinstance(response.data, list)
        assert response.data == [
            {
                "id": weekly_class.id,
                "subject": {
                    "id": subject.id,
                    "name": "Chemistry",
                    "slug": subject.slug,
                    "levels": [level_data("a_level"), level_data("university")],
                },
                "level": level_data("university"),
                "day": "thursday",
                "day_display": "Thursday",
                "time": "08:00:00",
                "duration": 40,
            }
        ]

    def test_if_classes_exist_returns_them_ordered_monday_to_sunday_then_time(
        self, student_user, list_classes
    ):
        _, student = student_user
        subject = make_subject()
        slots = [
            ("sunday", 8),
            ("wednesday", 15),
            ("monday", 17),
            ("friday", 9),
            ("monday", 9),
            ("wednesday", 8),
            ("saturday", 12),
            ("tuesday", 20),
            ("thursday", 7),
        ]
        for day, hour in slots:
            make_class(student, subject=subject, day=day, hour=hour)

        response = list_classes()

        result = [(item["day"], item["time"]) for item in response.data]
        assert result == [
            ("monday", "09:00:00"),
            ("monday", "17:00:00"),
            ("tuesday", "20:00:00"),
            ("wednesday", "08:00:00"),
            ("wednesday", "15:00:00"),
            ("thursday", "07:00:00"),
            ("friday", "09:00:00"),
            ("saturday", "12:00:00"),
            ("sunday", "08:00:00"),
        ]

    def test_if_student_has_many_classes_query_count_equals_one_class_count(
        self, api_client
    ):
        one_user, one_student = make_student()
        make_class(
            one_student,
            subject=make_subject(levels=("o_level", "a_level")),
            day="monday",
            hour=9,
        )
        many_user, many_student = make_student()
        for index, day in enumerate(
            ["tuesday", "wednesday", "thursday", "friday", "saturday"]
        ):
            subject = make_subject(levels=("o_level", "a_level", "university"))
            make_class(
                many_student,
                subject=subject,
                level=get_level(("o_level", "a_level", "university")[index % 3]),
                day=day,
                hour=9 + index,
            )

        api_client.force_authenticate(user=one_user)
        with CaptureQueriesContext(connection) as one_class_queries:
            one_response = api_client.get("/classes/")
        api_client.force_authenticate(user=many_user)
        with CaptureQueriesContext(connection) as many_class_queries:
            many_response = api_client.get("/classes/")

        assert len(one_response.data) == 1
        assert len(many_response.data) == 5
        assert len(many_class_queries) == len(one_class_queries)


@pytest.mark.django_db
class TestRetrieveWeeklyClass:
    def test_if_class_is_own_returns_200(self, student_user, retrieve_class):
        _, student = student_user
        subject = make_subject(name="Biology", levels=("o_level", "a_level"))
        weekly_class = make_class(
            student,
            subject=subject,
            level=get_level("a_level"),
            day="saturday",
            hour=11,
            duration=40,
        )

        response = retrieve_class(weekly_class.id)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "id": weekly_class.id,
            "subject": {
                "id": subject.id,
                "name": "Biology",
                "slug": subject.slug,
                "levels": [level_data("o_level"), level_data("a_level")],
            },
            "level": level_data("a_level"),
            "day": "saturday",
            "day_display": "Saturday",
            "time": "11:00:00",
            "duration": 40,
        }

    def test_if_class_is_retrieved_subject_has_no_price_fields(
        self, student_user, retrieve_class
    ):
        _, student = student_user
        weekly_class = make_class(student)

        response = retrieve_class(weekly_class.id)

        assert set(response.data["subject"].keys()) == SUBJECT_KEYS
        assert "description" not in response.data["subject"]
        assert set(response.data["level"].keys()) == LEVEL_KEYS

    def test_if_class_belongs_to_another_student_returns_404(
        self, student_user, retrieve_class
    ):
        _, other = make_student()
        weekly_class = make_class(other)

        response = retrieve_class(weekly_class.id)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_if_class_does_not_exist_returns_404(self, student_user, retrieve_class):
        response = retrieve_class(999999)

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestUpdateWeeklyClass:
    def test_if_put_changes_all_fields_returns_200(self, student_user, put_class):
        _, student = student_user
        weekly_class = make_class(student, day="monday", hour=16, duration=60)
        new_subject = make_subject(name="Maths", levels=("all_levels",))

        response = put_class(
            weekly_class.id,
            payload(new_subject, day="friday", time="10:00", duration=40),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["subject"] == {
            "id": new_subject.id,
            "name": "Maths",
            "slug": new_subject.slug,
            "levels": [level_data("all_levels")],
        }
        assert response.data["level"] == level_data("all_levels")
        assert response.data["day"] == "friday"
        assert response.data["day_display"] == "Friday"
        assert response.data["time"] == "10:00:00"
        assert response.data["duration"] == 40
        weekly_class.refresh_from_db()
        assert weekly_class.subject == new_subject
        assert weekly_class.level == get_level("all_levels")
        assert weekly_class.day == "friday"
        assert weekly_class.time == datetime.time(10)
        assert weekly_class.duration == 40
        assert weekly_class.student == student

    def test_if_put_level_is_another_of_the_subject_returns_200(
        self, student_user, put_class
    ):
        _, student = student_user
        subject = make_subject(levels=("o_level", "a_level"))
        weekly_class = make_class(student, subject=subject, level=get_level("o_level"))

        response = put_class(weekly_class.id, payload(subject, level="a_level"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["level"] == level_data("a_level")
        weekly_class.refresh_from_db()
        assert weekly_class.level == get_level("a_level")

    def test_if_put_level_is_not_one_of_the_subject_returns_400(
        self, student_user, put_class
    ):
        _, student = student_user
        subject = make_subject(levels=("o_level", "a_level"))
        weekly_class = make_class(
            student, subject=subject, level=get_level("o_level"), day="monday"
        )

        response = put_class(
            weekly_class.id,
            payload(subject, level="university", day="friday", time="10:00"),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "level" in response.data
        weekly_class.refresh_from_db()
        assert weekly_class.level == get_level("o_level")
        assert weekly_class.day == "monday"

    def test_if_put_new_subject_lacks_the_level_returns_400(
        self, student_user, put_class
    ):
        _, student = student_user
        weekly_class = make_class(student, level=get_level("o_level"))
        new_subject = make_subject(levels=("a_level",))

        response = put_class(
            weekly_class.id, payload(new_subject, level="o_level")
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "level" in response.data
        weekly_class.refresh_from_db()
        assert weekly_class.subject != new_subject

    def test_if_put_level_is_missing_returns_400(self, student_user, put_class):
        _, student = student_user
        weekly_class = make_class(student)
        data = payload(weekly_class.subject)
        del data["level"]

        response = put_class(weekly_class.id, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "level" in response.data

    def test_if_put_keeps_own_slot_returns_200(self, student_user, put_class):
        _, student = student_user
        weekly_class = make_class(student, day="monday", hour=16)

        response = put_class(
            weekly_class.id, payload(weekly_class.subject, day="monday", time="16:00")
        )

        assert response.status_code == status.HTTP_200_OK

    def test_if_put_is_missing_a_field_returns_400(self, student_user, put_class):
        _, student = student_user
        weekly_class = make_class(student)
        data = payload(weekly_class.subject)
        del data["duration"]

        response = put_class(weekly_class.id, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "duration" in response.data

    def test_if_put_time_is_not_on_the_full_hour_returns_400(
        self, student_user, put_class
    ):
        _, student = student_user
        weekly_class = make_class(student, day="monday", hour=16)

        response = put_class(
            weekly_class.id, payload(weekly_class.subject, time="16:30")
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "time" in response.data
        weekly_class.refresh_from_db()
        assert weekly_class.time == datetime.time(16)

    def test_if_put_moves_into_slot_held_by_another_student_returns_400(
        self, student_user, put_class
    ):
        _, student = student_user
        _, other = make_student()
        make_class(other, day="tuesday", hour=10)
        weekly_class = make_class(student, day="monday", hour=16)

        response = put_class(
            weekly_class.id, payload(weekly_class.subject, day="tuesday", time="10:00")
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["non_field_errors"] == [CLASH_MESSAGE]
        weekly_class.refresh_from_db()
        assert weekly_class.day == "monday"

    def test_if_put_moves_into_slot_held_by_own_other_class_returns_400(
        self, student_user, put_class
    ):
        _, student = student_user
        make_class(student, day="tuesday", hour=10)
        weekly_class = make_class(student, day="monday", hour=16)

        response = put_class(
            weekly_class.id, payload(weekly_class.subject, day="tuesday", time="10:00")
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["non_field_errors"] == [CLASH_MESSAGE]

    def test_if_put_class_belongs_to_another_student_returns_404(
        self, student_user, put_class
    ):
        _, other = make_student()
        weekly_class = make_class(other, day="monday", hour=16, duration=60)
        subject = make_subject()

        response = put_class(
            weekly_class.id, payload(subject, day="friday", time="10:00", duration=40)
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        weekly_class.refresh_from_db()
        assert weekly_class.day == "monday"
        assert weekly_class.time == datetime.time(16)
        assert weekly_class.duration == 60

    def test_if_patch_changes_only_duration_returns_200(
        self, student_user, patch_class
    ):
        _, student = student_user
        weekly_class = make_class(student, day="monday", hour=16, duration=60)

        response = patch_class(weekly_class.id, {"duration": 40})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["duration"] == 40
        weekly_class.refresh_from_db()
        assert weekly_class.duration == 40
        assert weekly_class.day == "monday"
        assert weekly_class.time == datetime.time(16)

    def test_if_patch_changes_only_subject_returns_200(self, student_user, patch_class):
        _, student = student_user
        weekly_class = make_class(student, day="monday", hour=16)
        new_subject = make_subject(name="Computer Science")

        response = patch_class(weekly_class.id, {"subject": new_subject.id})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["subject"]["id"] == new_subject.id
        assert set(response.data["subject"].keys()) == SUBJECT_KEYS
        assert "description" not in response.data["subject"]
        weekly_class.refresh_from_db()
        assert weekly_class.subject == new_subject

    def test_if_patch_changes_only_level_to_another_of_subject_returns_200(
        self, student_user, patch_class
    ):
        _, student = student_user
        subject = make_subject(levels=("o_level", "a_level"))
        weekly_class = make_class(student, subject=subject, level=get_level("o_level"))

        response = patch_class(weekly_class.id, {"level": "a_level"})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["level"] == level_data("a_level")
        weekly_class.refresh_from_db()
        assert weekly_class.level == get_level("a_level")
        assert weekly_class.subject == subject

    def test_if_patch_changes_only_level_to_one_subject_lacks_returns_400(
        self, student_user, patch_class
    ):
        _, student = student_user
        subject = make_subject(levels=("o_level", "a_level"))
        weekly_class = make_class(student, subject=subject, level=get_level("o_level"))

        response = patch_class(weekly_class.id, {"level": "university"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "level" in response.data
        weekly_class.refresh_from_db()
        assert weekly_class.level == get_level("o_level")

    def test_if_patch_changes_only_subject_to_one_with_current_level_returns_200(
        self, student_user, patch_class
    ):
        _, student = student_user
        weekly_class = make_class(
            student,
            subject=make_subject(levels=("o_level",)),
            level=get_level("o_level"),
        )
        new_subject = make_subject(levels=("o_level", "a_level"))

        response = patch_class(weekly_class.id, {"subject": new_subject.id})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["subject"]["id"] == new_subject.id
        assert response.data["level"] == level_data("o_level")
        weekly_class.refresh_from_db()
        assert weekly_class.subject == new_subject
        assert weekly_class.level == get_level("o_level")

    def test_if_patch_changes_only_subject_to_one_lacking_current_level_returns_400(
        self, student_user, patch_class
    ):
        _, student = student_user
        old_subject = make_subject(levels=("o_level",))
        weekly_class = make_class(
            student, subject=old_subject, level=get_level("o_level")
        )
        new_subject = make_subject(levels=("a_level", "university"))

        response = patch_class(weekly_class.id, {"subject": new_subject.id})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "level" in response.data
        weekly_class.refresh_from_db()
        assert weekly_class.subject == old_subject

    def test_if_patch_changes_subject_and_level_to_matching_pair_returns_200(
        self, student_user, patch_class
    ):
        _, student = student_user
        weekly_class = make_class(
            student,
            subject=make_subject(levels=("o_level",)),
            level=get_level("o_level"),
        )
        new_subject = make_subject(levels=("a_level", "university"))

        response = patch_class(
            weekly_class.id, {"subject": new_subject.id, "level": "university"}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["level"] == level_data("university")
        weekly_class.refresh_from_db()
        assert weekly_class.subject == new_subject
        assert weekly_class.level == get_level("university")

    def test_if_patch_changes_subject_and_level_to_mismatched_pair_returns_400(
        self, student_user, patch_class
    ):
        _, student = student_user
        weekly_class = make_class(student)
        new_subject = make_subject(levels=("a_level",))

        response = patch_class(
            weekly_class.id, {"subject": new_subject.id, "level": "university"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "level" in response.data

    def test_if_patch_level_code_is_unknown_returns_400(
        self, student_user, patch_class
    ):
        _, student = student_user
        weekly_class = make_class(student)

        response = patch_class(weekly_class.id, {"level": "primary"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "level" in response.data

    def test_if_patch_changes_day_to_free_slot_returns_200(
        self, student_user, patch_class
    ):
        _, student = student_user
        weekly_class = make_class(student, day="monday", hour=16)

        response = patch_class(weekly_class.id, {"day": "sunday"})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["day"] == "sunday"
        assert response.data["day_display"] == "Sunday"
        weekly_class.refresh_from_db()
        assert weekly_class.day == "sunday"

    def test_if_patch_changes_time_to_free_slot_returns_200(
        self, student_user, patch_class
    ):
        _, student = student_user
        weekly_class = make_class(student, day="monday", hour=16)

        response = patch_class(weekly_class.id, {"time": "18:00"})

        assert response.status_code == status.HTTP_200_OK
        weekly_class.refresh_from_db()
        assert weekly_class.time == datetime.time(18)

    def test_if_patch_sends_own_current_slot_returns_200(
        self, student_user, patch_class
    ):
        _, student = student_user
        weekly_class = make_class(student, day="monday", hour=16)

        response = patch_class(weekly_class.id, {"day": "monday", "time": "16:00"})

        assert response.status_code == status.HTTP_200_OK

    def test_if_patch_time_is_not_on_the_full_hour_returns_400(
        self, student_user, patch_class
    ):
        _, student = student_user
        weekly_class = make_class(student, day="monday", hour=16)

        response = patch_class(weekly_class.id, {"time": "16:30"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "time" in response.data

    def test_if_patch_day_moves_into_taken_slot_returns_400(
        self, student_user, patch_class
    ):
        _, student = student_user
        _, other = make_student()
        make_class(other, day="tuesday", hour=16)
        weekly_class = make_class(student, day="monday", hour=16)

        response = patch_class(weekly_class.id, {"day": "tuesday"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["non_field_errors"] == [CLASH_MESSAGE]
        weekly_class.refresh_from_db()
        assert weekly_class.day == "monday"

    def test_if_patch_time_moves_into_taken_slot_returns_400(
        self, student_user, patch_class
    ):
        _, student = student_user
        _, other = make_student()
        make_class(other, day="monday", hour=18)
        weekly_class = make_class(student, day="monday", hour=16)

        response = patch_class(weekly_class.id, {"time": "18:00"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["non_field_errors"] == [CLASH_MESSAGE]
        weekly_class.refresh_from_db()
        assert weekly_class.time == datetime.time(16)

    def test_if_patch_duration_is_invalid_returns_400(self, student_user, patch_class):
        _, student = student_user
        weekly_class = make_class(student, duration=60)

        response = patch_class(weekly_class.id, {"duration": 45})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "duration" in response.data

    def test_if_patch_body_has_student_it_is_ignored(self, student_user, patch_class):
        _, student = student_user
        _, other = make_student()
        weekly_class = make_class(student)

        response = patch_class(weekly_class.id, {"duration": 40, "student": other.id})

        assert response.status_code == status.HTTP_200_OK
        weekly_class.refresh_from_db()
        assert weekly_class.student == student

    def test_if_patch_class_belongs_to_another_student_returns_404(
        self, student_user, patch_class
    ):
        _, other = make_student()
        weekly_class = make_class(other, duration=60)

        response = patch_class(weekly_class.id, {"duration": 40})

        assert response.status_code == status.HTTP_404_NOT_FOUND
        weekly_class.refresh_from_db()
        assert weekly_class.duration == 60


@pytest.mark.django_db
class TestDeleteWeeklyClass:
    def test_if_class_is_own_returns_204(self, student_user, delete_class):
        _, student = student_user
        weekly_class = make_class(student)

        response = delete_class(weekly_class.id)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not WeeklyClass.objects.filter(id=weekly_class.id).exists()

    def test_if_class_is_deleted_slot_can_be_booked_by_another_student(
        self, api_client, delete_class, create_class
    ):
        owner_user, owner = make_student()
        other_user, _ = make_student()
        weekly_class = make_class(owner, day="monday", hour=16)
        subject = make_subject()
        api_client.force_authenticate(user=owner_user)
        delete_class(weekly_class.id)
        api_client.force_authenticate(user=other_user)

        response = create_class(payload(subject, day="monday", time="16:00"))

        assert response.status_code == status.HTTP_201_CREATED

    def test_if_class_belongs_to_another_student_returns_404(
        self, student_user, delete_class
    ):
        _, other = make_student()
        weekly_class = make_class(other)

        response = delete_class(weekly_class.id)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert WeeklyClass.objects.filter(id=weekly_class.id).exists()

    def test_if_class_does_not_exist_returns_404(self, student_user, delete_class):
        response = delete_class(999999)

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestWeeklyClassCascades:
    def test_if_user_account_is_deleted_their_classes_are_deleted(self):
        user, student = make_student()
        other_user, other = make_student()
        make_class(student, day="monday", hour=9)
        make_class(student, day="tuesday", hour=9)
        kept = make_class(other, day="wednesday", hour=9)

        user.delete()

        assert list(WeeklyClass.objects.values_list("id", flat=True)) == [kept.id]

    def test_if_student_is_deleted_slot_is_free_again(self, api_client, create_class):
        user, student = make_student()
        make_class(student, day="monday", hour=16)
        other_user, _ = make_student()
        subject = make_subject()
        student.delete()
        api_client.force_authenticate(user=other_user)

        response = create_class(payload(subject, day="monday", time="16:00"))

        assert response.status_code == status.HTTP_201_CREATED

    def test_if_subject_has_weekly_class_deleting_it_raises_protected_error(self):
        _, student = make_student()
        subject = make_subject()
        make_class(student, subject=subject)

        with pytest.raises(ProtectedError):
            subject.delete()

        assert Subject.objects.filter(id=subject.id).exists()

    def test_if_subject_has_no_weekly_class_deleting_it_succeeds(self):
        subject = make_subject()

        subject.delete()

        assert not Subject.objects.filter(id=subject.id).exists()


@pytest.mark.django_db
class TestWeeklyClassModelRules:
    def test_if_day_and_time_are_duplicated_save_raises_integrity_error(self):
        _, first = make_student()
        _, second = make_student()
        make_class(first, day="monday", hour=16)
        subject = make_subject()

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                WeeklyClass(
                    student=second,
                    subject=subject,
                    level=subject.levels.first(),
                    day="monday",
                    time=datetime.time(16),
                    duration=40,
                ).save()

    def test_if_day_is_unknown_save_raises_integrity_error(self):
        _, student = make_student()
        subject = make_subject()

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                WeeklyClass(
                    student=student,
                    subject=subject,
                    level=subject.levels.first(),
                    day="funday",
                    time=datetime.time(16),
                    duration=60,
                ).save()

    @pytest.mark.parametrize("duration", [0, 30, 45, 90])
    def test_if_duration_is_not_40_or_60_save_raises_integrity_error(self, duration):
        _, student = make_student()
        subject = make_subject()

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                WeeklyClass(
                    student=student,
                    subject=subject,
                    level=subject.levels.first(),
                    day="monday",
                    time=datetime.time(16),
                    duration=duration,
                ).save()

    @pytest.mark.parametrize(
        "time", [datetime.time(16, 30), datetime.time(16, 0, 1), datetime.time(16, 15)]
    )
    def test_if_time_is_not_on_the_full_hour_save_raises_integrity_error(self, time):
        _, student = make_student()
        subject = make_subject()

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                WeeklyClass(
                    student=student,
                    subject=subject,
                    level=subject.levels.first(),
                    day="monday",
                    time=time,
                    duration=60,
                ).save()

    def test_if_time_is_not_on_the_full_hour_full_clean_rejects_it(self):
        _, student = make_student()
        subject = make_subject()
        weekly_class = WeeklyClass(
            student=student,
            subject=subject,
            level=subject.levels.first(),
            day="monday",
            time=datetime.time(16, 30),
            duration=60,
        )

        with pytest.raises(ValidationError) as error:
            weekly_class.full_clean()

        assert "time" in error.value.message_dict

    def test_if_level_is_not_one_of_the_subjects_full_clean_rejects_it(self):
        _, student = make_student()
        subject = make_subject(levels=("o_level",))
        weekly_class = WeeklyClass(
            student=student,
            subject=subject,
            level=get_level("university"),
            day="monday",
            time=datetime.time(16),
            duration=60,
        )

        with pytest.raises(ValidationError) as error:
            weekly_class.full_clean()

        assert "level" in error.value.message_dict

    def test_if_level_is_one_of_the_subjects_full_clean_accepts_it(self):
        _, student = make_student()
        subject = make_subject(levels=("o_level", "a_level"))
        weekly_class = WeeklyClass(
            student=student,
            subject=subject,
            level=get_level("a_level"),
            day="monday",
            time=datetime.time(16),
            duration=60,
        )

        weekly_class.full_clean()


@pytest.mark.django_db
class TestLevelProtection:
    def test_if_level_is_used_by_weekly_class_deleting_it_raises_protected_error(
        self,
    ):
        _, student = make_student()
        subject = make_subject(levels=("o_level", "a_level"))
        make_class(student, subject=subject, level=get_level("a_level"))

        with pytest.raises(ProtectedError):
            get_level("a_level").delete()

        assert Level.objects.filter(code="a_level").exists()


def subject_form(subject, levels, **overrides):
    data = {
        "name": subject.name,
        "slug": subject.slug,
        "levels": [get_level(code).pk for code in levels],
        "price_40_min": "10.00",
        "price_60_min": "15.00",
    }
    data.update(overrides)
    return SubjectAdminForm(data=data, instance=subject)


@pytest.mark.django_db
class TestSubjectAdminForm:
    def test_if_level_used_by_weekly_class_is_removed_form_is_invalid(self):
        _, student = make_student()
        subject = make_subject(levels=("o_level", "a_level"))
        make_class(student, subject=subject, level=get_level("a_level"))

        form = subject_form(subject, levels=("o_level",))

        assert not form.is_valid()
        assert "levels" in form.errors

    def test_if_level_used_by_weekly_class_is_kept_form_is_valid(self):
        _, student = make_student()
        subject = make_subject(levels=("o_level", "a_level"))
        make_class(student, subject=subject, level=get_level("a_level"))

        form = subject_form(subject, levels=("a_level",))

        assert form.is_valid(), form.errors

    def test_if_level_no_class_uses_is_removed_form_is_valid(self):
        _, student = make_student()
        subject = make_subject(levels=("o_level", "a_level"))
        make_class(student, subject=subject, level=get_level("o_level"))

        form = subject_form(subject, levels=("o_level",))

        assert form.is_valid(), form.errors

    def test_if_level_is_used_only_by_another_subjects_classes_form_is_valid(self):
        _, student = make_student()
        subject = make_subject(levels=("o_level", "a_level"))
        other_subject = make_subject(levels=("a_level",))
        make_class(student, subject=other_subject, level=get_level("a_level"))

        form = subject_form(subject, levels=("o_level",))

        assert form.is_valid(), form.errors
