# Spec: Subjects

## Overview
A subject is what a student books a class in, and it carries the two prices the rest of the domain is built on: one for a 40-minute class and one for a 60-minute class. It also states the level the tutor teaches it at. This feature adds the `Subject` model, registers it in the Django admin, where admins create and edit subjects, and exposes a read-only API so the frontend can list subjects and their prices. It is built second, straight after users, because weekly classes and trial lessons both point at a subject and the schedule's weekly cost is a sum of subject prices: none of them can be built without it.

## Depends on
No feature dependencies. `Subject` does not reference the user or the Student, and its routes are public, so it does not rely on `.claude/specs/01-users.md` beyond the project setup that feature left in place (the `classes` app, DRF and its settings).

## Requirements
1. A subject has a name, a level and two prices in USD: the price of a 40-minute class and the price of a 60-minute class.
2. Both prices are stored in `DecimalField`, never `FloatField`.
3. The API is read-only for subjects: a subject can be listed and retrieved, and nothing else. `POST`, `PUT`, `PATCH` and `DELETE` are not allowed and return 405.
4. Subjects are created, edited and deleted only in the Django admin site, so the model is registered in `classes/admin.py`.
5. The viewset is a `ReadOnlyModelViewSet` registered on a DRF router.

Decisions the user made on points `CLAUDE.md` leaves open:

6. **Access** — both routes are public (`AllowAny`). An anonymous request gets 200, so the frontend can show subjects and prices before a student registers. A logged-in student gets the same response.
7. **Fields** — a subject has a name, a level and the two prices and nothing else: no description and no active flag.
8. **Name** — the name is unique. A second subject with an existing name is rejected in the admin.
9. **Lowest price** — a price is zero or more. A negative price is rejected; a free subject (0.00) is allowed. The 40-minute and the 60-minute price are independent: neither has to be lower than the other.
10. **Level** — the level is the level the tutor teaches the subject at. Each subject has exactly one level; it is required and is one of four fixed values:

    | Code | Label |
    | --- | --- |
    | `all_grades` | All Grades (1-O Level) |
    | `o_level` | O Level |
    | `o_a_level` | O/A Level |
    | `university` | University Level |

    Because the name is unique, a subject exists at one level only: the same name cannot be added again at another level.
11. **Level in the API** — the API returns both the code, as `level`, and the label, as `level_display`.

## Deferred rules
No rule of this feature is deferred, and `.claude/specs/01-users.md` deferred nothing to it.

Later specs build on `Subject` and own these decisions, which are not made here:
- The foreign key from a weekly class to its subject, and what happens to a subject's weekly classes when an admin deletes the subject (`on_delete`) — `.claude/specs/03-weekly-classes.md`.
- The same for trial lessons — `.claude/specs/04-trial-lessons.md`.
- Using the two prices to total a student's weekly cost — `.claude/specs/05-schedule.md`.

## Routes
- `GET /subjects/` — list every subject, ordered by name — public
- `GET /subjects/{id}/` — retrieve one subject; 404 if the id does not exist — public

No other method is routed: `POST /subjects/` and `PUT` / `PATCH` / `DELETE /subjects/{id}/` return 405 for anonymous and authenticated requests alike.

## Models and database changes
`classes.Subject` (new, in `classes/models.py` next to `Student`):
- `name` — `CharField(max_length=100, unique=True)`, required.
- `level` — `CharField(max_length=20, choices=SubjectLevel.choices)`, required, no default. `SubjectLevel` is a module-level `models.TextChoices` in `classes/models.py` with the four members `ALL_GRADES`, `O_LEVEL`, `O_A_LEVEL` and `UNIVERSITY` (codes and labels as in Requirements 10), also reachable as `Subject.Level`.
- `price_40_min` — `DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])`, required. USD price of one 40-minute class.
- `price_60_min` — the same field definition. USD price of one 60-minute class.
- `Meta.ordering = ["name"]`.
- `Meta.constraints`:
  - `CheckConstraint(condition=Q(level__in=SubjectLevel.values), name="subject_level_valid")`
  - `CheckConstraint(condition=Q(price_40_min__gte=0), name="subject_price_40_min_gte_0")`
  - `CheckConstraint(condition=Q(price_60_min__gte=0), name="subject_price_60_min_gte_0")`
- `__str__` returns the name.

The uniqueness of `name` is a database constraint (`unique=True`). `max_length=100` and `max_digits=6` (prices up to 9999.99) are sizing choices of this spec, not product rules.

`Student` and `core.User` are unchanged. There is no relation between `Subject` and either of them.

The migration is generated with `uv run python manage.py makemigrations classes` (expected `classes/migrations/0002_subject.py`, depending on `0001_initial`). It is not written by hand.

## Serializers and validation
`classes.serializers.SubjectSerializer` (`ModelSerializer`, new file `classes/serializers.py`):
- Fields: `id`, `name`, `level`, `level_display`, `price_40_min`, `price_60_min`.
- `level` is the stored code (e.g. `"o_level"`). `level_display` is a declared read-only `CharField(source="get_level_display")` returning the label (e.g. `"O Level"`); the label is derived, not stored.
- The API never writes a subject, so the serializer is only used for output and no field is writable through any route.
- Prices are serialized as JSON numbers, not strings, because `REST_FRAMEWORK["COERCE_DECIMAL_TO_STRING"]` is `False`. In `response.data` they are `Decimal` values.

Validation happens where subjects are written, which is the admin:
- Negative price — rejected by `MinValueValidator` on the model field (shown as a form error in the admin) and by the `CheckConstraint` in the database (for anything that bypasses the form).
- Duplicate name — rejected by `unique=True` (form error in the admin, unique index in the database).
- Missing or unknown level — the admin form offers only the four choices and requires one; `full_clean()` rejects any other value, and the `subject_level_valid` `CheckConstraint` rejects it in the database.
- More than two decimal places or more than six digits — rejected by the `DecimalField` itself.

There is no serializer `validate` method and no API error payload for these rules, because no route accepts input.

## Views and URLs
`classes.views.SubjectViewSet`:
- Base class: `rest_framework.viewsets.ReadOnlyModelViewSet`.
- `permission_classes = [AllowAny]`, declared on the viewset (no default permission class is set in settings).
- `queryset = Subject.objects.all()`. It is not scoped to `request.user`: subjects are not bookings and belong to no student. Ordering comes from `Meta.ordering`.
- `serializer_class = SubjectSerializer`.
- No pagination: none is configured in `REST_FRAMEWORK`, so `GET /subjects/` returns a plain JSON array.

`classes/urls.py` (new):
- A `rest_framework.routers.SimpleRouter` with `router.register("subjects", SubjectViewSet)`; `urlpatterns = router.urls`. `SimpleRouter` rather than `DefaultRouter`, so that no API root view is added at `/` (a route the route tables do not list). The later features register their viewsets on this same router.

`config/urls.py`:
- Add `path("", include("classes.urls"))`, so the routes are mounted without an app prefix: `/subjects/` and `/subjects/{id}/`.

`classes/views.py` currently holds only the `startapp` stub (`from django.shortcuts import render`); the stub import is removed, since there are no templates.

## Admin
`classes/admin.py` registers `Subject` (`SubjectAdmin`) alongside the existing `StudentAdmin`:
- `list_display`: name, level, 40-minute price, 60-minute price.
- `list_filter`: level.
- `search_fields`: name. This also lets the later weekly class and trial lesson admins use an autocomplete subject field.

Admin-only: creating a subject, editing its name, level or prices, and deleting it. None of these is possible through the API.

## Files to change
- `classes/models.py` — add `Subject`
- `classes/admin.py` — register `Subject`
- `classes/views.py` — replace the stub with `SubjectViewSet`
- `config/urls.py` — mount `classes.urls`
- `CLAUDE.md`:
  - "Implemented vs Stub Routes" > Subjects: both routes go from Stub to Implemented
  - Product requirements: the "Only requirement 1 is built so far" line, and requirement 2 gains the decisions above (public access, unique name, the level and its four values, prices zero or more)
  - Architecture: `classes/` no longer has "only `Student`"; describe `Subject` and that `classes/urls.py` is mounted at the root
- `.claude/agents/quantum-test-writer.md` — its copy of the subject rules gains the level (code plus label). The other command and agent files do not describe subject fields and are unchanged

## Files to create
- `classes/serializers.py`
- `classes/urls.py`
- `classes/migrations/0002_subject.py` (generated by `makemigrations`)

`classes/tests/` and `classes/tests/test_subjects.py` are created later by `/test-feature subjects`, not during implementation. There is no `classes/tests.py` stub to delete.

## New dependencies
No new dependencies.

## Rules for implementation
- Money is stored in `DecimalField`, never `FloatField`
- Reference the user via `settings.AUTH_USER_MODEL` / `get_user_model()`, never `django.contrib.auth.models.User`
- Every view declares its own `permission_classes`; no default permission class is set
- Booking querysets are scoped to `request.user`; timeslot clash checks look at every user's bookings
- Booking rules are enforced on the server in serializers/models, backed by a database constraint where possible
- Prefer `ModelViewSet` on a DRF router; subjects use `ReadOnlyModelViewSet`
- No teacher- or admin-facing endpoints; register every model in `admin.py` instead
- No templates or server-rendered pages
- Update the "Implemented vs Stub Routes" tables in `CLAUDE.md` in the same change
- `SubjectViewSet` is a `ReadOnlyModelViewSet`, never a `ModelViewSet` with methods switched off
- `SubjectViewSet` declares `permission_classes = [AllowAny]` explicitly; do not rely on DRF's default
- Subject prices, names and levels are never writable through the API
- The level is a `TextChoices` on the model, never free text, and is backed by a `CheckConstraint`; the label comes from `get_level_display`, never from a stored column or a copy of the labels in the serializer
- The subject queryset is not filtered by user
- Do not add fields the spec does not list (no description, no active flag, no currency field: prices are USD by definition)
- The non-negative price rule is enforced twice: a `MinValueValidator` on each price field and a `CheckConstraint` per price
- Use `Decimal("0")`, not a float, in the validator
- Do not change `COERCE_DECIMAL_TO_STRING`; prices stay JSON numbers
- Register on a `SimpleRouter` in `classes/urls.py` and mount it at the root of `config/urls.py`; do not add a `/api/` or app prefix
- Generate the migration with `makemigrations`; do not write it by hand
- Do not write tests during implementation

## Tests
Covered by `classes/tests/test_subjects.py`, written and run with `/test-feature subjects`, not as part of implementation. It must cover:
- `GET /subjects/`: 200 for an anonymous request and for an authenticated student; returns every subject; an empty list when there are none; subjects ordered by name; the body is a plain list (not paginated)
- `GET /subjects/{id}/`: 200 for an anonymous request and for an authenticated student; 404 for an id that does not exist
- Response shape: exactly `id`, `name`, `level`, `level_display`, `price_40_min`, `price_60_min`; for each of the four levels `level` is the code and `level_display` the matching label; both prices returned as decimals and compared as `Decimal`; a subject whose two prices differ returns each in the right field
- Read-only: `POST /subjects/` and `PUT` / `PATCH` / `DELETE /subjects/{id}/` return 405, anonymous and authenticated, and create, change or delete nothing
- Model rules: a duplicate name raises `IntegrityError`; a negative price fails `full_clean()` and, saved without validation, raises `IntegrityError`; a price of 0 is accepted; an unknown level and a missing level fail `full_clean()`, and an unknown level saved without validation raises `IntegrityError`

## Definition of done
- [ ] `uv run python manage.py makemigrations --check` reports no missing migrations
- [ ] Each route returns the expected status for an anonymous request (`GET /subjects/` and `GET /subjects/{id}/` return 200; `POST /subjects/` and `PUT` / `PATCH` / `DELETE /subjects/{id}/` return 405)
- [ ] The feature's routes are marked Implemented in `CLAUDE.md`
- [ ] `uv run python manage.py migrate` applies `classes.0002` cleanly
- [ ] A subject created in the Django admin appears in `GET /subjects/` with `id`, `name`, `level`, `level_display`, `price_40_min` and `price_60_min`, the level as its code and its label and the prices as JSON numbers
- [ ] `GET /subjects/` lists subjects in name order
- [ ] `GET /subjects/{id}/` returns that subject, and 404 for an unknown id
- [ ] `GET /subjects/` with a valid `JWT` token returns the same body as the anonymous request
- [ ] In the Django admin, Subject has a list page showing name, level and both prices, can be searched by name and filtered by level, and its form offers exactly the four levels
- [ ] The admin rejects a negative price and a duplicate name with a form error, and accepts a price of 0
- [ ] `GET /` returns 404 (no API root view was added)
- [ ] `uv run pytest classes/tests/test_subjects.py` passes (after `/test-feature subjects`)
