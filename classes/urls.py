from rest_framework.routers import SimpleRouter

from .views import SubjectViewSet

router = SimpleRouter()
router.register("subjects", SubjectViewSet)

urlpatterns = router.urls
