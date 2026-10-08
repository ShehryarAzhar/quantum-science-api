from rest_framework import serializers

from .models import Subject


class SubjectSerializer(serializers.ModelSerializer):
    level_display = serializers.CharField(source="get_level_display", read_only=True)

    class Meta:
        model = Subject
        fields = [
            "id",
            "name",
            "level",
            "level_display",
            "price_40_min",
            "price_60_min",
        ]
