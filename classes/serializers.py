from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from .models import (
    TIMESLOT_CONSTRAINT_NAME,
    TIMESLOT_TAKEN_MESSAGE,
    Level,
    Subject,
    WeeklyClass,
)


class LevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Level
        fields = ["code", "name"]


class SubjectSerializer(serializers.ModelSerializer):
    levels = LevelSerializer(many=True, read_only=True)

    class Meta:
        model = Subject
        fields = [
            "id",
            "name",
            "levels",
            "price_40_min",
            "price_60_min",
        ]


class WeeklyClassSubjectSerializer(serializers.ModelSerializer):
    levels = LevelSerializer(many=True, read_only=True)

    class Meta:
        model = Subject
        fields = ["id", "name", "levels"]


class WeeklyClassSerializer(serializers.ModelSerializer):
    day_display = serializers.CharField(source="get_day_display", read_only=True)

    class Meta:
        model = WeeklyClass
        fields = ["id", "subject", "day", "day_display", "time", "duration"]
        validators = [
            # Every student's classes, not only the request user's.
            UniqueTogetherValidator(
                queryset=WeeklyClass.objects.all(),
                fields=["day", "time"],
                message=TIMESLOT_TAKEN_MESSAGE,
            )
        ]

    def to_representation(self, instance):
        # The subject is written as an id and read as a nested object.
        data = super().to_representation(instance)
        data["subject"] = WeeklyClassSubjectSerializer(instance.subject).data
        return data

    def save(self, **kwargs):
        # Two requests can pass the validator together and collide on the
        # unique constraint. Any other integrity failure is not a clash.
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except IntegrityError as exc:
            if TIMESLOT_CONSTRAINT_NAME not in str(exc):
                raise
            raise serializers.ValidationError(
                {"non_field_errors": [TIMESLOT_TAKEN_MESSAGE]}
            ) from exc
