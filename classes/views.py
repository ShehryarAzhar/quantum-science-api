from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ReadOnlyModelViewSet

from .models import Subject
from .serializers import SubjectSerializer


class SubjectViewSet(ReadOnlyModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [AllowAny]
