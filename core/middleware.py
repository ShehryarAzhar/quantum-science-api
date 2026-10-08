from functools import cached_property
from zoneinfo import ZoneInfo

from django.conf import settings
from django.urls import reverse
from django.utils import timezone


class AdminTimezoneMiddleware:
    """Run the Django admin in settings.ADMIN_TIME_ZONE; the API stays UTC."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.admin_time_zone = ZoneInfo(settings.ADMIN_TIME_ZONE)

    @cached_property
    def admin_prefix(self):
        return reverse("admin:index")

    def __call__(self, request):
        if not request.path.startswith(self.admin_prefix):
            return self.get_response(request)
        # override, not activate: the timezone must not stay set on the
        # thread, or the next API request it serves would answer in it.
        with timezone.override(self.admin_time_zone):
            return self.get_response(request)
