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

EXPECTED_KEYS = {
    'id', 'name', 'slug', 'description', 'levels', 'price_40_min', 'price_60_min',
}


def make_subject(levels=('o_level',), **kwargs):
    kwargs.setdefault('price_40_min', Decimal('10.00'))
    kwargs.setdefault('price_60_min', Decimal('15.00'))
    kwargs.setdefault('description', '')
    if 'slug' not in kwargs:
        # Every subject gets its own slug, derived from its (unique) test name.
        kwargs['slug'] = kwargs.get('name', 'subject').lower().replace(' ', '-')
    subject = baker.make(Subject, **kwargs)
    subject.levels.add(*[Level.objects.get(code=code) for code in levels])
    return subject


def expected_body(subject):
    return {
        'id': subject.id,
        'name': subject.name,
        'slug': subject.slug,
        'description': subject.description,
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
    def do_retrieve_subject(slug):
        return api_client.get(f'/subjects/{slug}/')
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

    def test_if_subjects_have_slug_and_description_returns_them_for_each_subject(
            self, list_subjects):
        biology = make_subject(name='Biology', slug='a-level-biology', description='Cells.')
        physics = make_subject(name='Physics', description='')

        response = list_subjects()

        assert response.data == [expected_body(biology), expected_body(physics)]
        assert [item['slug'] for item in response.data] == ['a-level-biology', 'physics']
        assert [item['description'] for item in response.data] == ['Cells.', '']

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

        response = retrieve_subject(subject.slug)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == expected_body(subject)

    def test_if_user_is_authenticated_returns_200(self, retrieve_subject, authenticate):
        authenticate()
        subject = make_subject(name='Physics')

        response = retrieve_subject(subject.slug)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == expected_body(subject)

    def test_if_slug_is_unknown_returns_404(self, retrieve_subject):
        make_subject(name='Physics')

        response = retrieve_subject('no-such-subject')

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_if_numeric_id_is_used_returns_404(self, retrieve_subject):
        subject = make_subject(name='Physics')

        response = retrieve_subject(subject.id)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_if_several_subjects_exist_returns_the_one_with_that_slug(self, retrieve_subject):
        make_subject(name='Biology')
        chemistry = make_subject(name='Chemistry', slug='a-level-chemistry')
        make_subject(name='Physics')

        response = retrieve_subject('a-level-chemistry')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == chemistry.id
        assert response.data == expected_body(chemistry)

    def test_if_subject_is_retrieved_returns_slug_and_description_of_the_subject(
            self, retrieve_subject):
        subject = make_subject(
            name='Physics', slug='physics-101', description='Forces and motion.')

        response = retrieve_subject(subject.slug)

        assert response.data['slug'] == 'physics-101'
        assert response.data['description'] == 'Forces and motion.'
        assert response.data['id'] == subject.id

    def test_if_description_is_blank_returns_empty_string(self, retrieve_subject):
        subject = make_subject(name='Physics', description='')

        response = retrieve_subject(subject.slug)

        assert response.data['description'] == ''

    def test_if_description_has_html_markdown_and_line_breaks_returns_it_unchanged(
            self, retrieve_subject):
        text = '<b>Bold</b> & <script>alert("x")</script>\n\n# Heading\n**strong** [link](http://x.y)\nlast line'
        subject = make_subject(name='Physics', description=text)

        response = retrieve_subject(subject.slug)

        assert response.data['description'] == text

    def test_if_subject_exists_returns_only_the_expected_fields(self, retrieve_subject):
        subject = make_subject(name='Physics')

        response = retrieve_subject(subject.slug)

        assert set(response.data.keys()) == EXPECTED_KEYS

    def test_if_subject_is_retrieved_returns_no_old_level_fields_does_not_return_them(self, retrieve_subject):
        subject = make_subject(name='Physics')

        response = retrieve_subject(subject.slug)

        assert 'level' not in response.data
        assert 'level_display' not in response.data

    def test_if_subject_has_one_level_returns_one_item_list(self, retrieve_subject):
        subject = make_subject(name='Physics', levels=('university',))

        response = retrieve_subject(subject.slug)

        assert response.data['levels'] == [{'code': 'university', 'name': 'University Level'}]

    def test_if_subject_has_several_levels_returns_all_of_them(self, retrieve_subject):
        subject = make_subject(name='Physics', levels=('o_level', 'a_level', 'university'))

        response = retrieve_subject(subject.slug)

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

        response = retrieve_subject(subject.slug)

        assert [level['code'] for level in response.data['levels']] == [
            'o_level', 'a_level', 'all_levels', 'university']

    def test_if_subject_has_levels_returns_objects_with_only_code_and_name(
            self, retrieve_subject):
        subject = make_subject(name='Physics', levels=('o_level', 'a_level'))

        response = retrieve_subject(subject.slug)

        assert all(set(level.keys()) == {'code', 'name'} for level in response.data['levels'])

    @pytest.mark.parametrize('code, name', LEVELS)
    def test_if_subject_has_level_returns_its_code_and_name(self, retrieve_subject, code, name):
        subject = make_subject(name='Physics', levels=(code,))

        response = retrieve_subject(subject.slug)

        assert response.data['levels'] == [{'code': code, 'name': name}]

    def test_if_prices_differ_returns_each_in_the_right_field_as_decimal(self, retrieve_subject):
        subject = make_subject(
            name='Physics', price_40_min=Decimal('12.50'), price_60_min=Decimal('9.75'))

        response = retrieve_subject(subject.slug)

        assert response.data['price_40_min'] == Decimal('12.50')
        assert response.data['price_60_min'] == Decimal('9.75')
        assert isinstance(response.data['price_40_min'], Decimal)
        assert isinstance(response.data['price_60_min'], Decimal)

    def test_if_price_is_zero_returns_200_with_zero_price(self, retrieve_subject):
        subject = make_subject(name='Free', price_40_min=Decimal('0.00'))

        response = retrieve_subject(subject.slug)

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
            'slug': 'chemistry',
            'description': 'Atoms.',
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

        response = api_client.put(f'/subjects/{subject.slug}/', {
            'name': 'Changed',
            'slug': 'changed',
            'description': 'Changed text.',
            'levels': ['university'],
            'price_40_min': '99.00',
            'price_60_min': '99.00',
        })

        subject.refresh_from_db()
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert subject.name == 'Physics'
        assert subject.slug == 'physics'
        assert subject.description == ''
        assert subject.price_40_min == Decimal('10.00')
        assert list(subject.levels.values_list('code', flat=True)) == ['o_level']

    @pytest.mark.parametrize('is_authenticated', [False, True])
    def test_if_method_is_patch_returns_405(self, api_client, authenticate, is_authenticated):
        if is_authenticated:
            authenticate()
        subject = make_subject(name='Physics', price_40_min=Decimal('10.00'))

        response = api_client.patch(
            f'/subjects/{subject.slug}/', {'price_40_min': '99.00', 'slug': 'hacked'})

        subject.refresh_from_db()
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert subject.price_40_min == Decimal('10.00')
        assert subject.slug == 'physics'

    @pytest.mark.parametrize('is_authenticated', [False, True])
    def test_if_method_is_delete_returns_405(self, api_client, authenticate, is_authenticated):
        if is_authenticated:
            authenticate()
        subject = make_subject(name='Physics')

        response = api_client.delete(f'/subjects/{subject.slug}/')

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert Subject.objects.filter(id=subject.id).exists()


@pytest.mark.django_db
class TestSubjectModelRules:
    def build(self, **kwargs):
        data = {
            'name': 'Physics',
            'slug': 'physics',
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
                    name='Physics', slug='physics-two',
                    price_40_min=Decimal('5.00'), price_60_min=Decimal('8.00'))

        assert Subject.objects.filter(name='Physics').count() == 1

    def test_if_slug_is_duplicate_raises_integrity_error(self):
        make_subject(name='Physics', slug='science')

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Subject.objects.create(
                    name='Biology', slug='science',
                    price_40_min=Decimal('5.00'), price_60_min=Decimal('8.00'))

        assert Subject.objects.filter(slug='science').count() == 1

    @pytest.mark.parametrize('slug', ['chemistry', 'a-level-maths', 'physics-101'])
    def test_if_slug_is_valid_passes_full_clean(self, slug):
        subject = self.build(slug=slug)

        subject.full_clean()

    @pytest.mark.parametrize('slug', [
        'Chemistry', 'chem_101', 'chem 101', '-chem', 'chem-', 'chem--101', ''])
    def test_if_slug_is_invalid_fails_full_clean_on_slug(self, slug):
        subject = self.build(slug=slug)

        with pytest.raises(ValidationError) as error:
            subject.full_clean()

        assert 'slug' in error.value.message_dict

    def test_if_subject_is_renamed_keeps_its_slug(self):
        subject = make_subject(name='Physics', slug='physics')

        subject.name = 'Applied Physics'
        subject.save()

        subject.refresh_from_db()
        assert subject.name == 'Applied Physics'
        assert subject.slug == 'physics'

    def test_if_description_is_blank_passes_full_clean(self):
        subject = self.build(description='')

        subject.full_clean()

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
