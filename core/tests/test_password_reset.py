import re
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from djoser.utils import encode_uid
from model_bakery import baker
from rest_framework import status
import pytest


User = get_user_model()

OLD_PASSWORD = 'Old-Passw0rd-Zebra!'
NEW_PASSWORD = 'Tr1cky-Giraffe-Lantern!'
RESET_URL = '/auth/users/reset_password/'
CONFIRM_URL = '/auth/users/reset_password_confirm/'
LINK_PATTERN = re.compile(r'http://localhost:3000/reset-password/([^/\s]+)/([^/\s]+)')


def make_user_with_password(password=OLD_PASSWORD, **kwargs):
    user = baker.make(User, **kwargs)
    user.set_password(password)
    user.save()
    return user


def make_uid_and_token(user):
    return encode_uid(user.pk), default_token_generator.make_token(user)


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def reset_password(api_client):
    def do_reset_password(payload):
        return api_client.post(RESET_URL, payload)
    return do_reset_password


@pytest.fixture
def confirm_reset(api_client):
    def do_confirm_reset(payload):
        return api_client.post(CONFIRM_URL, payload)
    return do_confirm_reset


@pytest.fixture
def login(api_client):
    def do_login(user, password):
        return api_client.post(
            '/auth/jwt/create/',
            {'username': user.username, 'password': password},
        )
    return do_login


@pytest.mark.django_db
class TestResetPassword:
    def test_if_email_is_registered_returns_204_and_sends_one_email(self, reset_password):
        user = make_user_with_password(email='student@example.com')

        response = reset_password({'email': user.email})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]

    def test_if_email_is_sent_it_contains_the_frontend_link(self, reset_password):
        user = make_user_with_password(email='student@example.com')

        reset_password({'email': user.email})

        match = LINK_PATTERN.search(mail.outbox[0].body)
        assert match is not None
        uid, token = match.groups()
        assert uid == encode_uid(user.pk)
        assert default_token_generator.check_token(user, token)

    def test_if_user_is_anonymous_returns_204(self, reset_password, api_client):
        user = make_user_with_password(email='student@example.com')
        api_client.force_authenticate(user=None)

        response = reset_password({'email': user.email})

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_if_email_is_unknown_returns_204_and_sends_no_email(self, reset_password):
        response = reset_password({'email': 'nobody@example.com'})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert len(mail.outbox) == 0

    def test_if_user_is_inactive_returns_204_and_sends_no_email(self, reset_password):
        user = make_user_with_password(email='inactive@example.com', is_active=False)

        response = reset_password({'email': user.email})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert len(mail.outbox) == 0

    def test_if_user_has_unusable_password_returns_204_and_sends_no_email(self, reset_password):
        user = baker.make(User, email='nopass@example.com')
        user.set_unusable_password()
        user.save()

        response = reset_password({'email': user.email})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert len(mail.outbox) == 0

    def test_if_email_is_missing_returns_400(self, reset_password):
        response = reset_password({})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'email' in response.data

    @pytest.mark.parametrize('email', ['not-an-email', 'a@', '@example.com', ''])
    def test_if_email_is_malformed_returns_400(self, reset_password, email):
        response = reset_password({'email': email})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'email' in response.data
        assert len(mail.outbox) == 0


@pytest.mark.django_db
class TestResetPasswordThrottle:
    def test_if_sixth_request_in_an_hour_returns_429(self, reset_password):
        responses = [reset_password({'email': 'nobody@example.com'}) for _ in range(6)]

        assert [r.status_code for r in responses[:5]] == [status.HTTP_204_NO_CONTENT] * 5
        assert responses[5].status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_if_throttled_other_routes_are_not_limited(self, reset_password, api_client):
        for _ in range(6):
            reset_password({'email': 'nobody@example.com'})
        user = make_user_with_password()
        uid, token = make_uid_and_token(user)

        subjects = api_client.get('/subjects/')
        confirm = api_client.post(
            CONFIRM_URL,
            {'uid': uid, 'token': token, 'new_password': NEW_PASSWORD},
        )

        assert subjects.status_code == status.HTTP_200_OK
        assert confirm.status_code == status.HTTP_204_NO_CONTENT

    def test_if_confirm_is_called_many_times_it_is_not_limited(self, confirm_reset):
        responses = [
            confirm_reset({'uid': 'MQ', 'token': 'bad', 'new_password': NEW_PASSWORD})
            for _ in range(8)
        ]

        assert all(r.status_code == status.HTTP_400_BAD_REQUEST for r in responses)


@pytest.mark.django_db
class TestResetPasswordConfirm:
    def test_if_uid_and_token_are_valid_returns_204_and_changes_password(self, confirm_reset):
        user = make_user_with_password()
        uid, token = make_uid_and_token(user)

        response = confirm_reset({'uid': uid, 'token': token, 'new_password': NEW_PASSWORD})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        user.refresh_from_db()
        assert user.check_password(NEW_PASSWORD)
        assert not user.check_password(OLD_PASSWORD)

    def test_if_password_is_reset_sends_password_changed_email(self, confirm_reset):
        user = make_user_with_password(email='student@example.com')
        uid, token = make_uid_and_token(user)

        confirm_reset({'uid': uid, 'token': token, 'new_password': NEW_PASSWORD})

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]

    def test_if_link_from_email_is_used_full_flow_returns_204(self, reset_password, confirm_reset):
        user = make_user_with_password(email='student@example.com')
        reset_password({'email': user.email})
        uid, token = LINK_PATTERN.search(mail.outbox[0].body).groups()

        response = confirm_reset({'uid': uid, 'token': token, 'new_password': NEW_PASSWORD})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        user.refresh_from_db()
        assert user.check_password(NEW_PASSWORD)

    def test_if_uid_is_bad_returns_400(self, confirm_reset):
        user = make_user_with_password()
        _, token = make_uid_and_token(user)

        response = confirm_reset({'uid': 'zzzz', 'token': token, 'new_password': NEW_PASSWORD})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'uid' in response.data
        user.refresh_from_db()
        assert user.check_password(OLD_PASSWORD)

    def test_if_token_is_wrong_returns_400(self, confirm_reset):
        user = make_user_with_password()
        uid, _ = make_uid_and_token(user)

        response = confirm_reset({'uid': uid, 'token': 'abc-123', 'new_password': NEW_PASSWORD})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'token' in response.data
        user.refresh_from_db()
        assert user.check_password(OLD_PASSWORD)

    def test_if_link_is_used_a_second_time_returns_400(self, confirm_reset):
        user = make_user_with_password()
        uid, token = make_uid_and_token(user)
        confirm_reset({'uid': uid, 'token': token, 'new_password': NEW_PASSWORD})

        response = confirm_reset(
            {'uid': uid, 'token': token, 'new_password': 'An0ther-Sturdy-Phrase!'}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'token' in response.data
        user.refresh_from_db()
        assert user.check_password(NEW_PASSWORD)

    def test_if_link_is_expired_returns_400(self, confirm_reset):
        user = make_user_with_password()
        uid, token = make_uid_and_token(user)
        later = datetime.now() + timedelta(hours=1, minutes=5)

        with patch.object(default_token_generator, '_now', return_value=later):
            response = confirm_reset({'uid': uid, 'token': token, 'new_password': NEW_PASSWORD})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'token' in response.data
        user.refresh_from_db()
        assert user.check_password(OLD_PASSWORD)

    def test_if_link_is_inside_the_hour_returns_204(self, confirm_reset):
        user = make_user_with_password()
        uid, token = make_uid_and_token(user)
        later = datetime.now() + timedelta(minutes=50)

        with patch.object(default_token_generator, '_now', return_value=later):
            response = confirm_reset({'uid': uid, 'token': token, 'new_password': NEW_PASSWORD})

        assert response.status_code == status.HTTP_204_NO_CONTENT

    @pytest.mark.parametrize('weak_password', ['short1A', 'password', '12345678901', 'student'])
    def test_if_new_password_is_weak_returns_400(self, confirm_reset, weak_password):
        user = make_user_with_password(username='student')
        uid, token = make_uid_and_token(user)

        response = confirm_reset({'uid': uid, 'token': token, 'new_password': weak_password})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'new_password' in response.data
        user.refresh_from_db()
        assert user.check_password(OLD_PASSWORD)

    @pytest.mark.parametrize('missing', ['uid', 'token', 'new_password'])
    def test_if_field_is_missing_returns_400(self, confirm_reset, missing):
        user = make_user_with_password()
        uid, token = make_uid_and_token(user)
        payload = {'uid': uid, 'token': token, 'new_password': NEW_PASSWORD}
        del payload[missing]

        response = confirm_reset(payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert missing in response.data
        user.refresh_from_db()
        assert user.check_password(OLD_PASSWORD)


@pytest.mark.django_db
class TestTokenRevocation:
    def test_if_password_is_reset_old_access_token_returns_401(
        self, api_client, login, confirm_reset
    ):
        user = make_user_with_password()
        access = login(user, OLD_PASSWORD).data['access']
        uid, token = make_uid_and_token(user)
        confirm_reset({'uid': uid, 'token': token, 'new_password': NEW_PASSWORD})

        response = api_client.get('/auth/users/me/', HTTP_AUTHORIZATION=f'JWT {access}')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_access_token_is_not_revoked_it_still_works(self, api_client, login):
        user = make_user_with_password()
        access = login(user, OLD_PASSWORD).data['access']

        response = api_client.get('/auth/users/me/', HTTP_AUTHORIZATION=f'JWT {access}')

        assert response.status_code == status.HTTP_200_OK

    def test_if_password_is_reset_old_password_login_returns_401(self, login, confirm_reset):
        user = make_user_with_password()
        uid, token = make_uid_and_token(user)
        confirm_reset({'uid': uid, 'token': token, 'new_password': NEW_PASSWORD})

        response = login(user, OLD_PASSWORD)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_password_is_reset_new_password_login_returns_200(self, login, confirm_reset):
        user = make_user_with_password()
        uid, token = make_uid_and_token(user)
        confirm_reset({'uid': uid, 'token': token, 'new_password': NEW_PASSWORD})

        response = login(user, NEW_PASSWORD)

        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data

    def test_if_password_is_reset_old_refresh_token_is_rejected(
        self, api_client, login, confirm_reset
    ):
        user = make_user_with_password()
        refresh = login(user, OLD_PASSWORD).data['refresh']
        uid, token = make_uid_and_token(user)
        confirm_reset({'uid': uid, 'token': token, 'new_password': NEW_PASSWORD})

        response = api_client.post('/auth/jwt/refresh/', {'refresh': refresh})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_password_is_changed_with_set_password_old_access_token_returns_401(
        self, api_client, login
    ):
        user = make_user_with_password()
        access = login(user, OLD_PASSWORD).data['access']

        change = api_client.post(
            '/auth/users/set_password/',
            {'new_password': NEW_PASSWORD, 'current_password': OLD_PASSWORD},
            HTTP_AUTHORIZATION=f'JWT {access}',
        )
        response = api_client.get('/auth/users/me/', HTTP_AUTHORIZATION=f'JWT {access}')

        assert change.status_code == status.HTTP_204_NO_CONTENT
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_password_is_changed_with_set_password_sends_password_changed_email(
        self, api_client, login
    ):
        user = make_user_with_password(email='student@example.com')
        access = login(user, OLD_PASSWORD).data['access']

        api_client.post(
            '/auth/users/set_password/',
            {'new_password': NEW_PASSWORD, 'current_password': OLD_PASSWORD},
            HTTP_AUTHORIZATION=f'JWT {access}',
        )

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]
