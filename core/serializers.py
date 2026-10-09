from django.contrib.auth import get_user_model
from django.db import transaction
from djoser.conf import settings as djoser_settings
from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer
from djoser.serializers import UserSerializer as BaseUserSerializer
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import (
    TokenRefreshSerializer as BaseTokenRefreshSerializer,
)
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.utils import get_md5_hash_password

from classes.constants import PHONE_NUMBER_MAX_LENGTH
from classes.models import Student
from classes.validators import phone_number_validator

from .signals import PHONE_NUMBER_ATTR

User = get_user_model()


class UserCreateSerializer(BaseUserCreateSerializer):
    phone_number = serializers.CharField(
        write_only=True,
        max_length=PHONE_NUMBER_MAX_LENGTH,
        # Reject surrounding whitespace instead of silently stripping it.
        trim_whitespace=False,
        validators=[phone_number_validator],
    )

    class Meta(BaseUserCreateSerializer.Meta):
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "password",
            "phone_number",
        ]

    def validate(self, attrs):
        # Djoser builds User(**attrs) to validate the password, and User has
        # no phone_number field.
        phone_number = attrs.pop("phone_number")
        attrs = super().validate(attrs)
        attrs["phone_number"] = phone_number
        return attrs

    def perform_create(self, validated_data):
        # create_user() saves in the same call that builds the user, leaving
        # no chance to attach the phone number for the post_save handler in
        # core.signals, so the user is built here instead.
        phone_number = validated_data.pop("phone_number")
        password = validated_data.pop("password")
        with transaction.atomic():
            user = User(**validated_data)
            user.username = User.normalize_username(user.username)
            user.email = User.objects.normalize_email(user.email)
            user.set_password(password)
            if djoser_settings.SEND_ACTIVATION_EMAIL:
                user.is_active = False
            setattr(user, PHONE_NUMBER_ATTR, phone_number)
            user.save()
        return user


class TokenRefreshSerializer(BaseTokenRefreshSerializer):
    default_error_messages = {
        "password_changed": "The user's password has been changed.",
    }

    def validate(self, attrs):
        # CHECK_REVOKE_TOKEN is only checked when an access token
        # authenticates a request, so a refresh token issued before a password
        # change is rejected here.
        refresh = self.token_class(attrs["refresh"])
        user = User.objects.filter(
            **{jwt_settings.USER_ID_FIELD: refresh.payload.get(jwt_settings.USER_ID_CLAIM)}
        ).first()
        if user is not None and refresh.payload.get(
            jwt_settings.REVOKE_TOKEN_CLAIM
        ) != get_md5_hash_password(user.password):
            raise AuthenticationFailed(
                self.error_messages["password_changed"], "password_changed"
            )
        return super().validate(attrs)


class CurrentUserSerializer(BaseUserSerializer):
    phone_number = serializers.SerializerMethodField()

    class Meta(BaseUserSerializer.Meta):
        fields = tuple(BaseUserSerializer.Meta.fields) + (
            "first_name",
            "last_name",
            "phone_number",
        )

    def get_phone_number(self, user):
        try:
            return user.student.phone_number
        except Student.DoesNotExist:
            return None
