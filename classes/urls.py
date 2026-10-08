from rest_framework.routers import SimpleRouter

from .views import SubjectViewSet, TrialLessonViewSet, WeeklyClassViewSet

router = SimpleRouter()
router.register("subjects", SubjectViewSet)
router.register("classes", WeeklyClassViewSet, basename="weekly-class")
router.register("trial-lessons", TrialLessonViewSet, basename="trial-lesson")

urlpatterns = router.urls
