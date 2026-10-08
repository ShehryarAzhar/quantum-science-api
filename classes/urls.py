from rest_framework.routers import SimpleRouter

from .views import SubjectViewSet, WeeklyClassViewSet

router = SimpleRouter()
router.register("subjects", SubjectViewSet)
router.register("classes", WeeklyClassViewSet, basename="weekly-class")

urlpatterns = router.urls
