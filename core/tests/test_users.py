from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from model_bakery import baker
from rest_framework import status
import pytest

from classes.models import Student

User = get_user_model()

PASSWORD = 'Str0ng-Pass-9271'


def make_payload(**overrides):
    payload = {
        'username': 'newstudent',
        'email': 'newstudent@example.com',
        'password': PASSWORD,
        'first_name': 'New',
        'last_name': 'Student',
        'phone_number': '+923001234567',
    }
    payload.update(overrides)
    return payload


def make_user_with_password(**kwargs):
    user = baker.make(User, **kwargs)
    user.set_password(PASSWORD)
    user.save()
    return user


@pytest.fixture
def register_user(api_client):
    def do_register_user(payload):
        return api_client.post('/auth/users/', payload)
    return do_register_user


@pytest.fixture
def get_me(api_client):
    def do_get_me():
        return api_client.get('/auth/users/me/')
    return do_get_me


@pytest.mark.django_db
class TestRegisterUser:
    def test_if_data_is_valid_returns_201(self, register_user):
        response = register_user(make_payload())

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['id'] > 0
        assert response.data['username'] == 'newstudent'
        assert response.data['email'] == 'newstudent@example.com'
        assert response.data['first_name'] == 'New'
        assert response.data['last_name'] == 'Student'

    def test_if_data_is_valid_creates_user_and_student(self, register_user):
        response = register_user(make_payload())

        assert response.status_code == status.HTTP_201_CREATED
        user = User.objects.get(username='newstudent')
        assert user.email == 'newstudent@example.com'
        assert user.check_password(PASSWORD)
        assert Student.objects.get(user=user).phone_number == '+923001234567'

    def test_if_data_is_valid_phone_number_and_password_are_not_exposed(self, register_user):
        response = register_user(make_payload())

        assert response.status_code == status.HTTP_201_CREATED
        assert 'phone_number' not in response.data
        assert 'password' not in response.data

    @pytest.mark.parametrize('phone_number', ['1234567', '123456789012345', '+1234567', '+923001234567'])
    def test_if_phone_number_is_valid_returns_201(self, register_user, phone_number):
        response = register_user(make_payload(phone_number=phone_number))

        assert response.status_code == status.HTTP_201_CREATED
        assert Student.objects.get(user__username='newstudent').phone_number == phone_number

    def test_if_phone_number_is_missing_returns_400(self, register_user):
        payload = make_payload()
        del payload['phone_number']

        response = register_user(payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'phone_number' in response.data
        assert not User.objects.filter(username='newstudent').exists()
        assert Student.objects.count() == 0

    @pytest.mark.parametrize('phone_number', [
        '',
        '123456',
        '1234567890123456',
        '+123456',
        '++1234567',
        '12345abc78',
        '123-456-7890',
        '123 456 7890',
        '1234567+',
    ])
    def test_if_phone_number_is_invalid_returns_400(self, register_user, phone_number):
        response = register_user(make_payload(phone_number=phone_number))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'phone_number' in response.data
        assert not User.objects.filter(username='newstudent').exists()
        assert Student.objects.count() == 0

    @pytest.mark.parametrize('phone_number', [
        '1234567\n',
        '+923001234567\n',
        '\n1234567',
        ' 1234567',
        '1234567 ',
    ])
    def test_if_phone_number_has_surrounding_whitespace_or_newline_returns_400(
            self, register_user, phone_number):
        response = register_user(make_payload(phone_number=phone_number))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'phone_number' in response.data
        assert not User.objects.filter(username='newstudent').exists()
        assert Student.objects.count() == 0

    @pytest.mark.parametrize('phone_number', [
        '1234567\n',
        '+923001234567\n',
        '\n1234567',
        ' 1234567',
        '1234567 ',
    ])
    def test_if_phone_number_has_surrounding_whitespace_or_newline_in_json_returns_400(
            self, api_client, phone_number):
        response = api_client.post('/auth/users/', make_payload(phone_number=phone_number), format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'phone_number' in response.data
        assert not User.objects.filter(username='newstudent').exists()
        assert Student.objects.count() == 0

    def test_if_phone_number_is_shared_with_another_student_returns_201(self, register_user):
        other = baker.make(User)
        baker.make(Student, user=other, phone_number='+923001234567')

        response = register_user(make_payload())

        assert response.status_code == status.HTTP_201_CREATED
        assert Student.objects.filter(phone_number='+923001234567').count() == 2

    def test_if_phone_number_is_missing_returns_required_message(self, register_user):
        payload = make_payload()
        del payload['phone_number']

        response = register_user(payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['phone_number'] == ['This field is required.']

    def test_if_student_cannot_be_created_user_is_not_created(self, register_user):
        with mock.patch.object(Student.objects, 'create', side_effect=RuntimeError('boom')):
            with pytest.raises(RuntimeError):
                register_user(make_payload())

        assert not User.objects.filter(username='newstudent').exists()
        assert Student.objects.count() == 0

    def test_if_email_is_already_taken_returns_400(self, register_user):
        baker.make(User, email='taken@example.com')

        response = register_user(make_payload(email='taken@example.com'))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'email' in response.data
        assert not User.objects.filter(username='newstudent').exists()
        assert Student.objects.count() == 0

    @pytest.mark.parametrize('field', ['username', 'email', 'password'])
    def test_if_required_field_is_missing_returns_400(self, register_user, field):
        payload = make_payload()
        del payload[field]

        response = register_user(payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert field in response.data
        assert Student.objects.count() == 0

    def test_if_password_is_weak_returns_400(self, register_user):
        response = register_user(make_payload(password='123'))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'password' in response.data
        assert not User.objects.filter(username='newstudent').exists()
        assert Student.objects.count() == 0


@pytest.mark.django_db
class TestUsersWithoutStudent:
    def test_if_user_is_made_by_baker_no_student_is_created(self):
        user = baker.make(User)

        assert not Student.objects.filter(user=user).exists()

    def test_if_superuser_is_created_no_student_is_created(self):
        user = User.objects.create_superuser(
            username='root', email='root@example.com', password=PASSWORD)

        assert user.pk is not None
        assert not Student.objects.filter(user=user).exists()

    def test_if_student_exists_str_returns_username(self):
        user = baker.make(User, username='strname')
        student = baker.make(Student, user=user)

        assert str(student) == 'strname'

    def test_if_user_already_has_student_second_student_is_rejected(self):
        user = baker.make(User)
        baker.make(Student, user=user)

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Student.objects.create(user=user, phone_number='+923001234567')

    def test_if_user_is_created_by_create_user_no_student_is_created(self):
        user = User.objects.create_user(
            username='plain', email='plain@example.com', password=PASSWORD)

        assert user.pk is not None
        assert Student.objects.count() == 0


@pytest.mark.django_db
class TestRetrieveCurrentUser:
    def test_if_user_is_anonymous_returns_401(self, get_me):
        response = get_me()

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_user_is_authenticated_returns_expected_fields(self, get_me, authenticate):
        user = baker.make(User, first_name='Ada', last_name='Lovelace')
        baker.make(Student, user=user, phone_number='+923001234567')
        authenticate(user)

        response = get_me()

        assert response.status_code == status.HTTP_200_OK
        assert set(response.data.keys()) == {
            'id', 'username', 'email', 'first_name', 'last_name', 'phone_number'}
        assert 'password' not in response.data

    def test_if_user_has_student_returns_phone_number(self, get_me, authenticate):
        user = baker.make(User)
        baker.make(Student, user=user, phone_number='+923001234567')
        authenticate(user)

        response = get_me()

        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == user.id
        assert response.data['username'] == user.username
        assert response.data['email'] == user.email
        assert response.data['phone_number'] == '+923001234567'

    def test_if_user_has_no_student_phone_number_is_null(self, get_me, authenticate):
        user = authenticate()

        response = get_me()

        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == user.id
        assert 'phone_number' in response.data
        assert response.data['phone_number'] is None

    def test_if_another_student_exists_returns_only_own_data(self, get_me, authenticate):
        other = baker.make(User)
        baker.make(Student, user=other, phone_number='+111111111')
        user = baker.make(User)
        baker.make(Student, user=user, phone_number='+222222222')
        authenticate(user)

        response = get_me()

        assert response.data['id'] == user.id
        assert response.data['phone_number'] == '+222222222'

    def test_if_user_has_names_returns_first_name_and_last_name(self, get_me, authenticate):
        user = baker.make(User, first_name='Ada', last_name='Lovelace')
        authenticate(user)

        response = get_me()

        assert response.status_code == status.HTTP_200_OK
        assert response.data['first_name'] == 'Ada'
        assert response.data['last_name'] == 'Lovelace'

    def test_if_user_registered_returns_registered_phone_number(self, api_client, register_user):
        register_user(make_payload())
        user = User.objects.get(username='newstudent')
        api_client.force_authenticate(user=user)

        response = api_client.get('/auth/users/me/')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['phone_number'] == '+923001234567'


@pytest.mark.django_db
class TestUpdateCurrentUser:
    def test_if_user_is_anonymous_returns_401(self, api_client):
        response = api_client.patch('/auth/users/me/', {'first_name': 'X'})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_put_user_is_anonymous_returns_401(self, api_client):
        response = api_client.put('/auth/users/me/', {'email': 'x@example.com'})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_email_is_changed_updates_email(self, api_client, authenticate):
        user = authenticate()

        response = api_client.patch('/auth/users/me/', {'email': 'changed@example.com'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == 'changed@example.com'
        user.refresh_from_db()
        assert user.email == 'changed@example.com'

    def test_if_other_user_exists_update_does_not_change_other_user(self, api_client, authenticate):
        other = baker.make(User, first_name='Other', username='otheruser')
        user = authenticate()

        response = api_client.patch('/auth/users/me/', {'first_name': 'Mine', 'id': other.id})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == user.id
        other.refresh_from_db()
        assert other.first_name == 'Other'

    def test_if_phone_number_is_sent_it_is_not_changed(self, api_client, authenticate):
        user = baker.make(User)
        baker.make(Student, user=user, phone_number='+923001234567')
        authenticate(user)

        response = api_client.patch('/auth/users/me/', {'phone_number': '+19998887777'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['phone_number'] == '+923001234567'
        assert Student.objects.get(user=user).phone_number == '+923001234567'

    def test_if_phone_number_is_sent_for_user_without_student_no_student_is_created(self, api_client, authenticate):
        user = authenticate()

        response = api_client.patch('/auth/users/me/', {'phone_number': '+19998887777'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['phone_number'] is None
        assert not Student.objects.filter(user=user).exists()

    def test_if_put_includes_phone_number_it_is_not_changed(self, api_client, authenticate):
        user = baker.make(User, username='putuser')
        baker.make(Student, user=user, phone_number='+923001234567')
        authenticate(user)

        response = api_client.put('/auth/users/me/', {
            'username': 'putuser',
            'email': user.email,
            'phone_number': '+19998887777',
        })

        assert response.status_code == status.HTTP_200_OK
        assert Student.objects.get(user=user).phone_number == '+923001234567'

    def test_if_data_is_valid_updates_user_fields(self, api_client, authenticate):
        user = authenticate()

        response = api_client.patch('/auth/users/me/', {'first_name': 'Changed'})

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.first_name == 'Changed'

    def test_if_patch_has_names_updates_and_returns_them(self, api_client, authenticate):
        user = authenticate(baker.make(User, first_name='Old', last_name='Name'))

        response = api_client.patch('/auth/users/me/', {'first_name': 'Grace', 'last_name': 'Hopper'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['first_name'] == 'Grace'
        assert response.data['last_name'] == 'Hopper'
        user.refresh_from_db()
        assert user.first_name == 'Grace'
        assert user.last_name == 'Hopper'

    def test_if_patch_has_only_first_name_last_name_is_unchanged(self, api_client, authenticate):
        user = authenticate(baker.make(User, first_name='Old', last_name='Name'))

        response = api_client.patch('/auth/users/me/', {'first_name': 'Grace'})

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.first_name == 'Grace'
        assert user.last_name == 'Name'

    def test_if_put_has_names_updates_and_returns_them(self, api_client, authenticate):
        user = authenticate(baker.make(User, first_name='Old', last_name='Name'))

        response = api_client.put('/auth/users/me/', {
            'email': user.email,
            'first_name': 'Grace',
            'last_name': 'Hopper',
        })

        assert response.status_code == status.HTTP_200_OK
        assert response.data['first_name'] == 'Grace'
        assert response.data['last_name'] == 'Hopper'
        user.refresh_from_db()
        assert user.first_name == 'Grace'
        assert user.last_name == 'Hopper'

    def test_if_patch_has_username_it_is_not_changed(self, api_client, authenticate):
        user = authenticate(baker.make(User, username='original'))

        response = api_client.patch('/auth/users/me/', {'username': 'hacked'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['username'] == 'original'
        user.refresh_from_db()
        assert user.username == 'original'

    def test_if_put_has_username_it_is_not_changed(self, api_client, authenticate):
        user = authenticate(baker.make(User, username='original'))

        response = api_client.put('/auth/users/me/', {
            'username': 'hacked',
            'email': user.email,
            'first_name': 'Grace',
            'last_name': 'Hopper',
        })

        assert response.status_code == status.HTTP_200_OK
        assert response.data['username'] == 'original'
        user.refresh_from_db()
        assert user.username == 'original'
        assert user.first_name == 'Grace'

    def test_if_names_are_updated_phone_number_is_kept(self, api_client, authenticate):
        user = baker.make(User)
        baker.make(Student, user=user, phone_number='+923001234567')
        authenticate(user)

        response = api_client.patch('/auth/users/me/', {'first_name': 'Grace'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['phone_number'] == '+923001234567'


@pytest.mark.django_db
class TestDeleteCurrentUser:
    def test_if_user_is_anonymous_returns_401(self, api_client):
        response = api_client.delete('/auth/users/me/', {'current_password': PASSWORD})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_user_is_deleted_student_is_deleted(self, api_client, authenticate):
        user = make_user_with_password()
        baker.make(Student, user=user)
        authenticate(user)

        response = api_client.delete('/auth/users/me/', {'current_password': PASSWORD})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not User.objects.filter(pk=user.pk).exists()
        assert Student.objects.count() == 0

    def test_if_user_is_deleted_other_students_are_kept(self, api_client, authenticate):
        user = make_user_with_password()
        baker.make(Student, user=user)
        other = baker.make(User)
        other_student = baker.make(Student, user=other)
        authenticate(user)

        response = api_client.delete('/auth/users/me/', {'current_password': PASSWORD})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert User.objects.filter(pk=other.pk).exists()
        assert Student.objects.filter(pk=other_student.pk).exists()
        assert Student.objects.filter(user_id=user.pk).count() == 0

    def test_if_user_without_student_is_deleted_returns_204(self, api_client, authenticate):
        user = make_user_with_password()
        authenticate(user)

        response = api_client.delete('/auth/users/me/', {'current_password': PASSWORD})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not User.objects.filter(pk=user.pk).exists()


@pytest.mark.django_db
class TestCreateToken:
    def test_if_credentials_are_valid_returns_200_with_tokens(self, api_client):
        make_user_with_password(username='tokenuser')

        response = api_client.post('/auth/jwt/create/', {'username': 'tokenuser', 'password': PASSWORD})

        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data

    def test_if_password_is_wrong_returns_401(self, api_client):
        make_user_with_password(username='tokenuser')

        response = api_client.post('/auth/jwt/create/', {'username': 'tokenuser', 'password': 'wrong-pass'})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert 'access' not in response.data

    def test_if_credentials_are_missing_returns_400(self, api_client):
        response = api_client.post('/auth/jwt/create/', {})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'username' in response.data
        assert 'password' in response.data


@pytest.mark.django_db
class TestJwtHeaderPrefix:
    def _login(self, api_client):
        user = make_user_with_password(username='headeruser')
        response = api_client.post('/auth/jwt/create/', {'username': 'headeruser', 'password': PASSWORD})
        return user, response.data['access']

    def test_if_header_prefix_is_jwt_returns_200(self, api_client):
        user, token = self._login(api_client)

        response = api_client.get('/auth/users/me/', HTTP_AUTHORIZATION=f'JWT {token}')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == user.id

    def test_if_header_prefix_is_bearer_returns_401(self, api_client):
        _, token = self._login(api_client)

        response = api_client.get('/auth/users/me/', HTTP_AUTHORIZATION=f'Bearer {token}')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_token_is_invalid_returns_401(self, api_client):
        response = api_client.get('/auth/users/me/', HTTP_AUTHORIZATION='JWT not-a-real-token')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
