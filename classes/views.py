from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from .models import Subject, TrialLesson, WeeklyClass
from .permissions import IsStudent, IsTrialLessonOpen
from .serializers import (
    SubjectSerializer,
    TrialLessonSerializer,
    WeeklyClassSerializer,
)


class SubjectViewSet(ReadOnlyModelViewSet):
    queryset = Subject.objects.prefetch_related("levels")
    serializer_class = SubjectSerializer
    permission_classes = [AllowAny]


class WeeklyClassViewSet(ModelViewSet):
    serializer_class = WeeklyClassSerializer
    permission_classes = [IsAuthenticated, IsStudent]

    def get_queryset(self):
        return (
            WeeklyClass.objects.filter(student=self.request.user.student)
            .select_related("subject", "level")
            .prefetch_related("subject__levels")
            .in_week_order()
        )

    def perform_create(self, serializer):
        serializer.save(student=self.request.user.student)


class TrialLessonViewSet(ModelViewSet):
    serializer_class = TrialLessonSerializer
    permission_classes = [IsAuthenticated, IsStudent, IsTrialLessonOpen]

    def get_queryset(self):
        return (
            TrialLesson.objects.filter(student=self.request.user.student)
            .select_related("subject", "level")
            .prefetch_related("subject__levels")
        )

    def perform_create(self, serializer):
        serializer.save(student=self.request.user.student)
