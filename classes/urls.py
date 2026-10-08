from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    ScheduleView,
    SubjectViewSet,
    TrialLessonViewSet,
    WeeklyClassViewSet,
)

router = SimpleRouter()
router.register("subjects", SubjectViewSet)
router.register("classes", WeeklyClassViewSet, basename="weekly-class")
router.register("trial-lessons", TrialLessonViewSet, basename="trial-lesson")

urlpatterns = [
    # Not a viewset, so it sits beside the router's routes.
    path("schedule/", ScheduleView.as_view(), name="schedule"),
    *router.urls,
]
