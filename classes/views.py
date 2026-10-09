from decimal import Decimal

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from .models import Subject, TrialLesson, WeeklyClass
from .permissions import IsStudent, IsTrialLessonOpen
from .serializers import (
    ScheduleSerializer,
    SubjectSerializer,
    TrialLessonSerializer,
    WeeklyClassSerializer,
)


class SubjectViewSet(ReadOnlyModelViewSet):
    queryset = Subject.objects.prefetch_related("levels")
    serializer_class = SubjectSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"


class WeeklyClassViewSet(ModelViewSet):
    serializer_class = WeeklyClassSerializer
    permission_classes = [IsAuthenticated, IsStudent]

    def get_queryset(self):
        return WeeklyClass.objects.for_student(
            self.request.user.student
        ).in_week_order()

    def perform_create(self, serializer):
        serializer.save(student=self.request.user.student)


class TrialLessonViewSet(ModelViewSet):
    serializer_class = TrialLessonSerializer
    permission_classes = [IsAuthenticated, IsStudent, IsTrialLessonOpen]

    def get_queryset(self):
        return TrialLesson.objects.for_student(self.request.user.student)

    def perform_create(self, serializer):
        serializer.save(student=self.request.user.student)


class ScheduleView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        student = request.user.student
        # Evaluated once: the list is both serialized and totalled.
        weekly_classes = list(
            WeeklyClass.objects.for_student(student).in_week_order()
        )
        schedule = {
            "weekly_classes": weekly_classes,
            # Shown even when it is completed or has passed.
            "trial_lesson": TrialLesson.objects.for_student(student).first(),
            "weekly_cost": sum(
                (weekly_class.price for weekly_class in weekly_classes),
                Decimal("0.00"),
            ),
        }
        serializer = ScheduleSerializer(schedule, context={"request": request})
        return Response(serializer.data)
