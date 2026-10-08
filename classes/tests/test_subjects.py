from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from model_bakery import baker
from rest_framework import status

from classes.models import Subject

LEVELS = [
    ('all_grades', 'All Grades (1-O Level)'),
    ('o_level', 'O Level'),
    ('o_a_level', 'O/A Level'),
    ('university', 'University Level'),
]

EXPECTED_KEYS = {'id', 'name', 'level', 'level_display', 'price_40_min', 'price_60_min'}


def make_subject(**kwargs):
    kwargs.setdefault('level', Subject.Level.O_LEVEL)
    kwargs.setdefault('price_40_min', Decimal('10.00'))
    kwargs.setdefault('price_60_min', Decimal('15.00'))
    return baker.make(Subject, **kwargs)


def expected_body(subject):
    return {
        'id': subject.id,
        'name': subject.name,
        'level': subject.level,
        'level_display': subject.get_level_display(),
        'price_40_min': subject.price_40_min,
        'price_60_min': subject.price_60_min,
    }


@pytest.fixture
def list_subjects(api_client):
    def do_list_subjects():
        return api_client.get('/subjects/')
    return do_list_subjects


@pytest.fixture
def retrieve_subject(api_client):
    def do_retrieve_subject(subject_id):
        return api_client.get(f'/subjects/{subject_id}/')
    return do_retrieve_subject


@pytest.mark.django_db
class TestListSubjects:
    def test_if_user_is_anonymous_returns_200(self, list_subjects):
        make_subject(name='Physics')

        response = list_subjects()

        assert response.status_code == status.HTTP_200_OK

    def test_if_user_is_authenticated_returns_200(self, list_subjects, authenticate):
        authenticate()
        make_subject(name='Physics')

        response = list_subjects()

        assert response.status_code == status.HTTP_200_OK

    def test_if_there_are_no_subjects_returns_200_with_empty_list(self, list_subjects):
        response = list_subjects()

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_if_subjects_exist_returns_all_of_them_as_plain_list(self, list_subjects):
        subjects = [make_subject(name=name) for name in ('Biology', 'Chemistry', 'Physics')]

        response = list_subjects()

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        assert {item['id'] for item in response.data} == {s.id for s in subjects}

    def test_if_subjects_exist_returns_them_ordered_by_name(self, list_subjects):
        make_subject(name='Physics')
        make_subject(name='Biology')
        make_subject(name='Chemistry')

        response = list_subjects()

        assert [item['name'] for item in response.data] == ['Biology', 'Chemistry', 'Physics']

    def test_if_subject_exists_returns_only_the_expected_fields(self, list_subjects):
        subject = make_subject(name='Physics')

        response = list_subjects()

        assert response.data == [expected_body(subject)]
        assert set(response.data[0].keys()) == EXPECTED_KEYS

    def test_if_user_is_authenticated_returns_same_body_as_anonymous(
            self, api_client, authenticate):
        make_subject(name='Physics')
        make_subject(name='Biology')
        anonymous_response = api_client.get('/subjects/')
        authenticate()

        authenticated_response = api_client.get('/subjects/')

        assert authenticated_response.status_code == status.HTTP_200_OK
        assert authenticated_response.data == anonymous_response.data


@pytest.mark.django_db
class TestRetrieveSubject:
    def test_if_user_is_anonymous_returns_200(self, retrieve_subject):
        subject = make_subject(name='Physics')

        response = retrieve_subject(subject.id)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == expected_body(subject)

    def test_if_user_is_authenticated_returns_200(self, retrieve_subject, authenticate):
        authenticate()
        subject = make_subject(name='Physics')

        response = retrieve_subject(subject.id)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == expected_body(subject)

    def test_if_subject_does_not_exist_returns_404(self, retrieve_subject):
        subject = make_subject(name='Physics')

        response = retrieve_subject(subject.id + 1000)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_if_subject_exists_returns_only_the_expected_fields(self, retrieve_subject):
        subject = make_subject(name='Physics')

        response = retrieve_subject(subject.id)

        assert set(response.data.keys()) == EXPECTED_KEYS

    @pytest.mark.parametrize('code, label', LEVELS)
    def test_if_subject_has_level_returns_code_and_label(self, retrieve_subject, code, label):
        subject = make_subject(name='Physics', level=code)

        response = retrieve_subject(subject.id)

        assert response.data['level'] == code
        assert response.data['level_display'] == label

    def test_if_prices_differ_returns_each_in_the_right_field_as_decimal(self, retrieve_subject):
        subject = make_subject(
            name='Physics', price_40_min=Decimal('12.50'), price_60_min=Decimal('9.75'))

        response = retrieve_subject(subject.id)

        assert response.data['price_40_min'] == Decimal('12.50')
        assert response.data['price_60_min'] == Decimal('9.75')
        assert isinstance(response.data['price_40_min'], Decimal)
        assert isinstance(response.data['price_60_min'], Decimal)

    def test_if_price_is_zero_returns_200_with_zero_price(self, retrieve_subject):
        subject = make_subject(name='Free', price_40_min=Decimal('0.00'))

        response = retrieve_subject(subject.id)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['price_40_min'] == Decimal('0')


@pytest.mark.django_db
class TestWriteSubjectsIsNotAllowed:
    @pytest.mark.parametrize('is_authenticated', [False, True])
    def test_if_method_is_post_returns_405(self, api_client, authenticate, is_authenticated):
        if is_authenticated:
            authenticate()

        response = api_client.post('/subjects/', {
            'name': 'Chemistry',
            'level': 'o_level',
            'price_40_min': '10.00',
            'price_60_min': '15.00',
        })

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert not Subject.objects.filter(name='Chemistry').exists()

    @pytest.mark.parametrize('is_authenticated', [False, True])
    def test_if_method_is_put_returns_405(self, api_client, authenticate, is_authenticated):
        if is_authenticated:
            authenticate()
        subject = make_subject(name='Physics', price_40_min=Decimal('10.00'))

        response = api_client.put(f'/subjects/{subject.id}/', {
            'name': 'Changed',
            'level': 'university',
            'price_40_min': '99.00',
            'price_60_min': '99.00',
        })

        subject.refresh_from_db()
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert subject.name == 'Physics'
        assert subject.price_40_min == Decimal('10.00')

    @pytest.mark.parametrize('is_authenticated', [False, True])
    def test_if_method_is_patch_returns_405(self, api_client, authenticate, is_authenticated):
        if is_authenticated:
            authenticate()
        subject = make_subject(name='Physics', price_40_min=Decimal('10.00'))

        response = api_client.patch(f'/subjects/{subject.id}/', {'price_40_min': '99.00'})

        subject.refresh_from_db()
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert subject.price_40_min == Decimal('10.00')

    @pytest.mark.parametrize('is_authenticated', [False, True])
    def test_if_method_is_delete_returns_405(self, api_client, authenticate, is_authenticated):
        if is_authenticated:
            authenticate()
        subject = make_subject(name='Physics')

        response = api_client.delete(f'/subjects/{subject.id}/')

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert Subject.objects.filter(id=subject.id).exists()


@pytest.mark.django_db
class TestSubjectModelRules:
    def build(self, **kwargs):
        data = {
            'name': 'Physics',
            'level': 'o_level',
            'price_40_min': Decimal('10.00'),
            'price_60_min': Decimal('15.00'),
        }
        data.update(kwargs)
        return Subject(**data)

    def test_if_name_is_duplicate_raises_integrity_error(self):
        make_subject(name='Physics', level='o_level')

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Subject.objects.create(
                    name='Physics', level='university',
                    price_40_min=Decimal('5.00'), price_60_min=Decimal('8.00'))

        assert Subject.objects.filter(name='Physics').count() == 1

    @pytest.mark.parametrize('field', ['price_40_min', 'price_60_min'])
    def test_if_price_is_negative_fails_full_clean(self, field):
        subject = self.build(**{field: Decimal('-0.01')})

        with pytest.raises(ValidationError) as error:
            subject.full_clean()

        assert field in error.value.message_dict

    @pytest.mark.parametrize('field', ['price_40_min', 'price_60_min'])
    def test_if_price_is_negative_and_saved_without_validation_raises_integrity_error(self, field):
        subject = self.build(**{field: Decimal('-1.00')})

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                subject.save()

        assert not Subject.objects.filter(name='Physics').exists()

    @pytest.mark.parametrize('field', ['price_40_min', 'price_60_min'])
    def test_if_price_is_zero_is_accepted(self, field):
        subject = self.build(**{field: Decimal('0.00')})

        subject.full_clean()
        subject.save()

        subject.refresh_from_db()
        assert getattr(subject, field) == Decimal('0.00')

    def test_if_prices_are_independent_is_accepted(self):
        subject = self.build(price_40_min=Decimal('20.00'), price_60_min=Decimal('10.00'))

        subject.full_clean()
        subject.save()

        subject.refresh_from_db()
        assert subject.price_40_min == Decimal('20.00')
        assert subject.price_60_min == Decimal('10.00')

    @pytest.mark.parametrize('code, label', LEVELS)
    def test_if_level_is_valid_is_accepted(self, code, label):
        subject = self.build(level=code)

        subject.full_clean()
        subject.save()

        assert Subject.objects.get(id=subject.id).get_level_display() == label

    def test_if_level_is_unknown_fails_full_clean(self):
        subject = self.build(level='primary')

        with pytest.raises(ValidationError) as error:
            subject.full_clean()

        assert 'level' in error.value.message_dict

    def test_if_level_is_missing_fails_full_clean(self):
        subject = Subject(
            name='Physics', price_40_min=Decimal('10.00'), price_60_min=Decimal('15.00'))

        with pytest.raises(ValidationError) as error:
            subject.full_clean()

        assert 'level' in error.value.message_dict

    def test_if_level_is_unknown_and_saved_without_validation_raises_integrity_error(self):
        subject = self.build(level='primary')

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                subject.save()

        assert not Subject.objects.filter(name='Physics').exists()
