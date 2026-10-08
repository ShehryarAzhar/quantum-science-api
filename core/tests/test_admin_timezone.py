import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory
from django.utils import timezone
from model_bakery import baker
from rest_framework import status

from classes.models import Level, Student, Subject, TrialLesson
from core.middleware import AdminTimezoneMiddleware

ADMIN_ZONE = "Asia/Karachi"


def active_zone_response(request):
    return HttpResponse(timezone.get_current_timezone_name())


def failing_response(request):
    raise RuntimeError("view failed")


def make_lesson(student):
    subject = baker.make(
        Subject, price_40_min=Decimal("10.00"), price_60_min=Decimal("15.00")
    )
    level = Level.objects.get(code="o_level")
    subject.levels.set([level])
    # 02:00 UTC is 07:00 in Asia/Karachi, on the same date.
    starts_at = timezone.now().replace(
        hour=2, minute=0, second=0, microsecond=0
    ) + datetime.timedelta(days=3)
    return baker.make(
        TrialLesson,
        student=student,
        subject=subject,
        level=level,
        starts_at=starts_at,
    )


class TestAdminTimezoneMiddleware:
    def test_if_request_is_for_the_admin_returns_admin_timezone_active(self):
        middleware = AdminTimezoneMiddleware(active_zone_response)

        response = middleware(RequestFactory().get("/admin/"))

        assert response.content.decode() == ADMIN_ZONE

    def test_if_request_is_for_an_admin_subpage_returns_admin_timezone_active(self):
        middleware = AdminTimezoneMiddleware(active_zone_response)

        response = middleware(
            RequestFactory().get("/admin/classes/weeklyclass/")
        )

        assert response.content.decode() == ADMIN_ZONE

    @pytest.mark.parametrize(
        "path",
        ["/classes/", "/trial-lessons/", "/subjects/", "/auth/users/me/", "/"],
    )
    def test_if_request_is_for_the_api_returns_utc_active(self, path):
        middleware = AdminTimezoneMiddleware(active_zone_response)

        response = middleware(RequestFactory().get(path))

        assert response.content.decode() == "UTC"

    def test_if_path_only_starts_like_the_admin_returns_utc_active(self):
        middleware = AdminTimezoneMiddleware(active_zone_response)

        response = middleware(RequestFactory().get("/administrators/"))

        assert response.content.decode() == "UTC"

    def test_if_admin_request_has_finished_returns_utc_restored(self):
        middleware = AdminTimezoneMiddleware(active_zone_response)

        middleware(RequestFactory().get("/admin/"))

        assert timezone.get_current_timezone_name() == "UTC"

    def test_if_admin_request_raises_returns_utc_restored(self):
        middleware = AdminTimezoneMiddleware(failing_response)

        with pytest.raises(RuntimeError):
            middleware(RequestFactory().get("/admin/"))

        assert timezone.get_current_timezone_name() == "UTC"

    def test_if_api_request_follows_an_admin_request_returns_utc_active(self):
        middleware = AdminTimezoneMiddleware(active_zone_response)
        middleware(RequestFactory().get("/admin/"))

        response = middleware(RequestFactory().get("/classes/"))

        assert response.content.decode() == "UTC"


@pytest.mark.django_db
class TestAdminTimezoneThroughRequests:
    def test_if_admin_page_is_requested_returns_200(self, admin_client):
        response = admin_client.get("/admin/")

        assert response.status_code == status.HTTP_200_OK

    def test_if_api_is_called_after_the_admin_returns_starts_at_in_utc(
        self, admin_client, api_client, authenticate
    ):
        user = baker.make(get_user_model())
        student = baker.make(Student, user=user, phone_number="+923001234567")
        lesson = make_lesson(student)
        authenticate(user)

        admin_response = admin_client.get(
            f"/admin/classes/triallesson/{lesson.id}/change/"
        )
        api_response = api_client.get(f"/trial-lessons/{lesson.id}/")

        # The admin showed the lesson in its own timezone...
        assert admin_response.status_code == status.HTTP_200_OK
        assert 'value="07:00:00"' in admin_response.content.decode()
        # ...and the API still answers in UTC.
        assert api_response.status_code == status.HTTP_200_OK
        assert api_response.data["starts_at"] == lesson.starts_at.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
