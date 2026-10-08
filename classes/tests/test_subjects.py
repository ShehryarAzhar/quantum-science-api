from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from model_bakery import baker
from rest_framework import status

from classes.models import Level, Subject

# The four levels created by the data migration, in the order of the spec table.
LEVELS = [
    ('o_level', 'O Level'),
    ('a_level', 'A Level'),
    ('all_levels', 'All Levels (1-O Level)'),
    ('university', 'University Level'),
]

EXPECTED_KEYS = {'id', 'name', 'levels', 'price_40_min', 'price_60_min'}


def make_subject(levels=('o_level',), **kwargs):
    kwargs.setdefault('price_40_min', Decimal('10.00'))
    kwargs.setdefault('price_60_min', Decimal('15.00'))
    subject = baker.make(Subject, **kwargs)
    subject.levels.add(*[Level.objects.get(code=code) for code in levels])
    return subject


def expected_body(subject):
    return {
        'id': subject.id,
        'name': subject.name,
        'levels': [
            {'code': level.code, 'name': level.name}
            for level in subject.levels.order_by('id')
        ],
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

    def test_if_subject_has_several_levels_returns_each_level_in_the_list(self, list_subjects):
        subject = make_subject(name='Physics', levels=('o_level', 'a_level'))

        response = list_subjects()

        assert response.data == [expected_body(subject)]
        assert len(response.data[0]['levels']) == 2

    def test_if_user_is_authenticated_returns_same_body_as_anonymous(
            self, api_client, authenticate):
        make_subject(name='Physics', levels=('o_level', 'a_level'))
        make_subject(name='Biology')
        anonymous_response = api_client.get('/subjects/')
        authenticate()

        authenticated_response = api_client.get('/subjects/')

        assert authenticated_response.status_code == status.HTTP_200_OK
        assert authenticated_response.data == anonymous_response.data

    def test_if_there_are_more_subjects_runs_the_same_number_of_queries(self, list_subjects):
        make_subject(name='Biology', levels=('o_level', 'a_level'))
        with CaptureQueriesContext(connection) as one_subject:
            list_subjects()
        for name in ('Chemistry', 'Maths', 'Physics', 'English'):
            make_subject(name=name, levels=('o_level', 'university'))

        with CaptureQueriesContext(connection) as five_subjects:
            response = list_subjects()

        assert len(response.data) == 5
        assert len(five_subjects) == len(one_subject)


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

    def test_if_subject_has_old_level_fields_does_not_return_them(self, retrieve_subject):
        subject = make_subject(name='Physics')

        response = retrieve_subject(subject.id)

        assert 'level' not in response.data
        assert 'level_display' not in response.data

    def test_if_subject_has_one_level_returns_one_item_list(self, retrieve_subject):
        subject = make_subject(name='Physics', levels=('university',))

        response = retrieve_subject(subject.id)

        assert response.data['levels'] == [{'code': 'university', 'name': 'University Level'}]

    def test_if_subject_has_several_levels_returns_all_of_them(self, retrieve_subject):
        subject = make_subject(name='Physics', levels=('o_level', 'a_level', 'university'))

        response = retrieve_subject(subject.id)

        assert response.data['levels'] == [
            {'code': 'o_level', 'name': 'O Level'},
            {'code': 'a_level', 'name': 'A Level'},
            {'code': 'university', 'name': 'University Level'},
        ]

    def test_if_levels_were_added_out_of_order_returns_them_in_level_order(
            self, retrieve_subject):
        subject = baker.make(
            Subject, name='Physics', price_40_min=Decimal('10.00'),
            price_60_min=Decimal('15.00'))
        for code in ('university', 'all_levels', 'a_level', 'o_level'):
            subject.levels.add(Level.objects.get(code=code))

        response = retrieve_subject(subject.id)

        assert [level['code'] for level in response.data['levels']] == [
            'o_level', 'a_level', 'all_levels', 'university']

    def test_if_subject_has_levels_returns_objects_with_only_code_and_name(
            self, retrieve_subject):
        subject = make_subject(name='Physics', levels=('o_level', 'a_level'))

        response = retrieve_subject(subject.id)

        assert all(set(level.keys()) == {'code', 'name'} for level in response.data['levels'])

    @pytest.mark.parametrize('code, name', LEVELS)
    def test_if_subject_has_level_returns_its_code_and_name(self, retrieve_subject, code, name):
        subject = make_subject(name='Physics', levels=(code,))

        response = retrieve_subject(subject.id)

        assert response.data['levels'] == [{'code': code, 'name': name}]

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
            'levels': ['o_level'],
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
            'levels': ['university'],
            'price_40_min': '99.00',
            'price_60_min': '99.00',
        })

        subject.refresh_from_db()
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert subject.name == 'Physics'
        assert subject.price_40_min == Decimal('10.00')
        assert list(subject.levels.values_list('code', flat=True)) == ['o_level']

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
            'price_40_min': Decimal('10.00'),
            'price_60_min': Decimal('15.00'),
        }
        data.update(kwargs)
        return Subject(**data)

    def test_if_name_is_duplicate_raises_integrity_error(self):
        make_subject(name='Physics', levels=('o_level',))

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Subject.objects.create(
                    name='Physics',
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


@pytest.mark.django_db
class TestLevelRules:
    def test_if_data_migration_ran_the_four_levels_exist_in_order(self):
        levels = [(level.code, level.name) for level in Level.objects.all()]

        assert levels == LEVELS

    def test_if_level_code_is_duplicate_raises_integrity_error(self):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Level.objects.create(code='o_level', name='Another Name')

        assert Level.objects.filter(code='o_level').count() == 1

    def test_if_level_name_is_duplicate_raises_integrity_error(self):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Level.objects.create(code='another_code', name='O Level')

        assert Level.objects.filter(name='O Level').count() == 1

    def test_if_two_subjects_share_a_level_both_are_linked_to_it(self):
        physics = make_subject(name='Physics', levels=('o_level',))
        biology = make_subject(name='Biology', levels=('o_level', 'a_level'))

        o_level = Level.objects.get(code='o_level')

        assert set(o_level.subjects.all()) == {physics, biology}
