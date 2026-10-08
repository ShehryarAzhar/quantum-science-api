from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator, UniqueValidator

from .constants import (
    FULL_HOUR_MESSAGE,
    STARTS_AT_IN_PAST_MESSAGE,
    TIMESLOT_CONSTRAINT_NAME,
    TIMESLOT_TAKEN_MESSAGE,
    TRIAL_LESSON_ALREADY_BOOKED_MESSAGE,
    TRIAL_LESSON_FULL_HOUR_CONSTRAINT_NAME,
    TRIAL_LESSON_TIMESLOT_CONSTRAINT_NAME,
)
from .models import Level, Subject, TrialLesson, WeeklyClass
from .rules import (
    level_not_in_subject_error,
    trial_lesson_clash_error,
    weekly_class_clash_error,
)
from .validators import validate_full_hour


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


class SubjectLevelMixin(serializers.Serializer):
    # What a weekly class and a trial lesson share: the subject is written as
    # an id and the level as a code, both are read as nested objects, and the
    # level must be one of the subject's.
    level = serializers.SlugRelatedField(
        slug_field="code", queryset=Level.objects.all()
    )

    def validate_level_in_subject(self, attrs):
        # A PATCH may send only one of the two; the other is the stored one.
        # Both are required on create and PUT, so only a PATCH, which always
        # has an instance, reaches the fallback.
        subject = attrs.get("subject") or self.instance.subject
        level = attrs.get("level") or self.instance.level
        error = level_not_in_subject_error(subject, level)
        if error:
            raise serializers.ValidationError({"level": [error]})

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["subject"] = WeeklyClassSubjectSerializer(instance.subject).data
        data["level"] = LevelSerializer(instance.level).data
        return data


class WeeklyClassSerializer(SubjectLevelMixin, serializers.ModelSerializer):
    day_display = serializers.CharField(source="get_day_display", read_only=True)

    class Meta:
        model = WeeklyClass
        fields = [
            "id",
            "subject",
            "level",
            "day",
            "day_display",
            "time",
            "duration",
        ]
        validators = [
            # Every student's classes, not only the request user's.
            UniqueTogetherValidator(
                queryset=WeeklyClass.objects.all(),
                fields=["day", "time"],
                message=TIMESLOT_TAKEN_MESSAGE,
            )
        ]

    def validate(self, attrs):
        self.validate_level_in_subject(attrs)
        # Any student's upcoming trial lesson holds its weekday + hour.
        day = attrs["day"] if "day" in attrs else self.instance.day
        time = attrs["time"] if "time" in attrs else self.instance.time
        error = trial_lesson_clash_error(day, time)
        if error:
            raise serializers.ValidationError({"non_field_errors": [error]})
        return attrs

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


class TrialLessonSerializer(SubjectLevelMixin, serializers.ModelSerializer):
    class Meta:
        model = TrialLesson
        fields = [
            "id",
            "subject",
            "level",
            "starts_at",
            "completed",
        ]
        read_only_fields = ["completed"]
        extra_kwargs = {
            "starts_at": {
                # Listed in full so a taken time is reported on starts_at
                # with the timeslot message. Every student's lessons, not
                # only the request user's.
                "validators": [
                    validate_full_hour,
                    UniqueValidator(
                        queryset=TrialLesson.objects.all(),
                        message=TIMESLOT_TAKEN_MESSAGE,
                    ),
                ]
            }
        }

    def validate_starts_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError(STARTS_AT_IN_PAST_MESSAGE)
        # Any student's weekly class holds its weekday + hour.
        error = weekly_class_clash_error(value)
        if error:
            raise serializers.ValidationError(error)
        return value

    def validate(self, attrs):
        # A locked lesson still counts as the student's one trial lesson.
        if self.instance is None and self._student_has_trial_lesson():
            raise serializers.ValidationError(
                TRIAL_LESSON_ALREADY_BOOKED_MESSAGE
            )
        self.validate_level_in_subject(attrs)
        return attrs

    def save(self, **kwargs):
        # Two requests can pass validation together and collide on a unique
        # constraint: the timeslot, or the student's one trial lesson. The
        # full-hour constraint is a backstop behind the validator. Any other
        # integrity failure is none of these.
        creating = self.instance is None
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except IntegrityError as exc:
            if TRIAL_LESSON_TIMESLOT_CONSTRAINT_NAME in str(exc):
                raise serializers.ValidationError(
                    {"starts_at": [TIMESLOT_TAKEN_MESSAGE]}
                ) from exc
            if TRIAL_LESSON_FULL_HOUR_CONSTRAINT_NAME in str(exc):
                raise serializers.ValidationError(
                    {"starts_at": [FULL_HOUR_MESSAGE]}
                ) from exc
            if creating and self._student_has_trial_lesson():
                raise serializers.ValidationError(
                    {"non_field_errors": [TRIAL_LESSON_ALREADY_BOOKED_MESSAGE]}
                ) from exc
            raise

    def _student_has_trial_lesson(self):
        student = self.context["request"].user.student
        return TrialLesson.objects.filter(student=student).exists()
