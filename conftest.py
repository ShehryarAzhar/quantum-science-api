from django.contrib.auth import get_user_model
from model_bakery import baker
from rest_framework.test import APIClient
import pytest


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticate(api_client):
    def do_authenticate(user=None):
        if user is None:
            user = baker.make(get_user_model())
        api_client.force_authenticate(user=user)
        return user
    return do_authenticate
