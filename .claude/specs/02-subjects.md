# Spec: Subjects

## Overview
A subject is what a student books a class in, and it carries the two prices the rest of the domain is built on: one for a 40-minute class and one for a 60-minute class. It also states the levels the tutor teaches it at; a subject can have several. This feature adds the `Level` and `Subject` models, registers them in the Django admin, where admins create and edit subjects, and exposes a read-only API so the frontend can list subjects and their prices. It is built second, straight after users, because weekly classes and trial lessons both point at a subject and the schedule's weekly cost is a sum of subject prices: none of them can be built without it.

## Depends on
No feature dependencies. `Subject` does not reference the user or the Student, and its routes are public, so it does not rely on `.claude/specs/01-users.md` beyond the project setup that feature left in place (the `classes` app, DRF and its settings).

## Requirements
1. A subject has a name, one or more levels and two prices in USD: the price of a 40-minute class and the price of a 60-minute class.
2. Both prices are stored in `DecimalField`, never `FloatField`.
3. The API is read-only for subjects: a subject can be listed and retrieved, and nothing else. `POST`, `PUT`, `PATCH` and `DELETE` are not allowed and return 405.
4. Subjects are created, edited and deleted only in the Django admin site, so the model is registered in `classes/admin.py`.
5. The viewset is a `ReadOnlyModelViewSet` registered on a DRF router.

Decisions the user made on points `CLAUDE.md` leaves open:

6. **Access** — both routes are public (`AllowAny`). An anonymous request gets 200, so the frontend can show subjects and prices before a student registers. A logged-in student gets the same response.
7. **Fields** — a subject has a name, its levels and the two prices and nothing else: no description and no active flag.
8. **Name** — the name is unique. A second subject with an existing name is rejected in the admin.
9. **Lowest price** — a price is zero or more. A negative price is rejected; a free subject (0.00) is allowed. The 40-minute and the 60-minute price are independent: neither has to be lower than the other.
10. **Levels** — a level is a level the tutor teaches the subject at. A subject has one or more levels, chosen in the Django admin. There are four levels, which exist in every environment because a data migration creates them:

    | Code | Name |
    | --- | --- |
    | `o_level` | O Level |
    | `a_level` | A Level |
    | `all_levels` | All Levels (1-O Level) |
    | `university` | University Level |

    The name is still unique, so a subject taught at several levels is one subject with several levels, not one subject per level, and it has one pair of prices whatever the level.
11. **Levels in the API** — the API returns `levels`, a list with one object per level of the subject. Each object has the level's `code` and `name`, e.g. `"levels": [{"code": "o_level", "name": "O Level"}, {"code": "a_level", "name": "A Level"}]`. The levels of a subject come in the order of the table above.
12. **Replacing the single level** — a subject used to have exactly one level, stored as a text code. Subjects that existed before the change keep it as one of their levels: `o_level` and `university` map to the level with the same code, `all_grades` ("All Grades (1-O Level)") to `all_levels`, and `o_a_level` ("O/A Level"), which no longer exists, to both `o_level` and `a_level`.

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
`classes.Level` (in `classes/models.py`, above `Subject`):
- `code` — `SlugField(max_length=20, unique=True)`, required. The stable value the frontend filters on.
- `name` — `CharField(max_length=50, unique=True)`, required. The text shown to people.
- `Meta.ordering = ["id"]`, the order the data migration creates the levels in.
- `__str__` returns the name.

A model, not an array column, because MySQL has no `ArrayField`.

`classes.Subject` (in `classes/models.py` next to `Student`):
- `name` — `CharField(max_length=100, unique=True)`, required.
- `levels` — `ManyToManyField(Level, related_name="subjects")`. Not `blank`, so a form requires at least one.
- `price_40_min` — `DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])`, required. USD price of one 40-minute class.
- `price_60_min` — the same field definition. USD price of one 60-minute class.
- `Meta.ordering = ["name"]`.
- `Meta.constraints`:
  - `CheckConstraint(condition=Q(price_40_min__gte=0), name="subject_price_40_min_gte_0")`
  - `CheckConstraint(condition=Q(price_60_min__gte=0), name="subject_price_60_min_gte_0")`
- `__str__` returns the name.

The uniqueness of `name` is a database constraint (`unique=True`). `max_length=100` and `max_digits=6` (prices up to 9999.99) are sizing choices of this spec, not product rules.

`Student` and `core.User` are unchanged. There is no relation between `Subject` and either of them.

"At least one level" cannot be a database constraint on a many-to-many; it is enforced by the admin form, the only place subjects are written. The old single `level` column, its `subject_level_valid` check constraint, the `SubjectLevel` choices and the `Subject.Level` alias no longer exist.

Migrations:
- `classes/migrations/0002_subject.py` — creates `Subject` with the old single `level`. Generated.
- `classes/migrations/0004_level_subject_levels.py` — creates `Level` and adds `Subject.levels`. Generated.
- `classes/migrations/0005_seed_levels.py` — the data migration, written by hand. It removes the `subject_level_valid` constraint, creates the four levels in the order of Requirements 10 with `get_or_create` on `code`, and gives every existing subject the levels its old code maps to (Requirements 12). It uses the historical models from `apps.get_model`. Unapplying it writes one old code back per subject, which is lossy for a subject with several levels; a subject with no level, or only levels added later, gets `all_grades`.
- `classes/migrations/0006_remove_subject_level.py` — drops the old `level` column. Generated.

Schema migrations are generated with `uv run python manage.py makemigrations classes`, never written by hand.

## Serializers and validation
`classes.serializers.LevelSerializer` (`ModelSerializer` on `Level`, in `classes/serializers.py`):
- Fields: `code`, `name`. No `id`. Used only nested, for output.

`classes.serializers.SubjectSerializer` (`ModelSerializer`, in `classes/serializers.py`):
- Fields: `id`, `name`, `levels`, `price_40_min`, `price_60_min`.
- `levels` is a declared `LevelSerializer(many=True, read_only=True)`: a list of `{"code", "name"}` objects, in `Level` order. There is no `level` or `level_display` field.
- The API never writes a subject, so the serializer is only used for output and no field is writable through any route.
- Prices are serialized as JSON numbers, not strings, because `REST_FRAMEWORK["COERCE_DECIMAL_TO_STRING"]` is `False`. In `response.data` they are `Decimal` values.

Validation happens where subjects are written, which is the admin:
- Negative price — rejected by `MinValueValidator` on the model field (shown as a form error in the admin) and by the `CheckConstraint` in the database (for anything that bypasses the form).
- Duplicate name — rejected by `unique=True` (form error in the admin, unique index in the database).
- No level chosen — the admin form requires at least one, because `levels` is not `blank`. This is a form rule only: nothing in the database stops a subject without levels, and `full_clean()` does not check a many-to-many.
- Unknown level — a subject can only be linked to an existing `Level` row (foreign keys of the many-to-many table).
- Duplicate level code or name — rejected by `unique=True` on `Level.code` and `Level.name`.
- More than two decimal places or more than six digits — rejected by the `DecimalField` itself.

There is no serializer `validate` method and no API error payload for these rules, because no route accepts input.

## Views and URLs
`classes.views.SubjectViewSet`:
- Base class: `rest_framework.viewsets.ReadOnlyModelViewSet`.
- `permission_classes = [AllowAny]`, declared on the viewset (no default permission class is set in settings).
- `queryset = Subject.objects.prefetch_related("levels")`. It is not scoped to `request.user`: subjects are not bookings and belong to no student. Ordering comes from `Meta.ordering`. The prefetch keeps the list at two queries however many subjects there are.
- `serializer_class = SubjectSerializer`.
- No pagination: none is configured in `REST_FRAMEWORK`, so `GET /subjects/` returns a plain JSON array.

`classes/urls.py` (new):
- A `rest_framework.routers.SimpleRouter` with `router.register("subjects", SubjectViewSet)`; `urlpatterns = router.urls`. `SimpleRouter` rather than `DefaultRouter`, so that no API root view is added at `/` (a route the route tables do not list). The later features register their viewsets on this same router.

`config/urls.py`:
- Add `path("", include("classes.urls"))`, so the routes are mounted without an app prefix: `/subjects/` and `/subjects/{id}/`.

`classes/views.py` currently holds only the `startapp` stub (`from django.shortcuts import render`); the stub import is removed, since there are no templates.

## Admin
`classes/admin.py` registers `Subject` (`SubjectAdmin`) alongside the existing `StudentAdmin`:
- `list_display`: name, levels (a `level_names` method joining the level names, since a many-to-many cannot be a list column), 40-minute price, 60-minute price. `get_queryset` prefetches `levels` for it.
- `list_filter`: levels.
- `filter_horizontal`: levels, so an admin picks several levels in the two-box widget.
- `search_fields`: name. This also lets the later weekly class and trial lesson admins use an autocomplete subject field.

`classes/admin.py` also registers `Level` (`LevelAdmin`): `list_display` name and code, `search_fields` name. The four levels come from the data migration; an admin can rename one or add another there. Deleting a level removes it from its subjects, which can leave a subject with none; a level that weekly classes use cannot be deleted at all (`PROTECT`, see `.claude/specs/03-weekly-classes.md`).

`SubjectAdmin` uses `SubjectAdminForm`, which refuses to remove a level from a subject while weekly classes of that subject use it (`.claude/specs/03-weekly-classes.md`, Requirements 21).

Admin-only: creating a subject, editing its name, levels or prices, and deleting it. None of these is possible through the API.

## Files to change
- `classes/models.py` — add `Level` and `Subject`
- `classes/admin.py` — register `Level` and `Subject`
- `classes/migrations/` — the migrations listed under Models and database changes
- `classes/views.py` — replace the stub with `SubjectViewSet`
- `config/urls.py` — mount `classes.urls`
- `CLAUDE.md`:
  - "Implemented vs Stub Routes" > Subjects: both routes go from Stub to Implemented
  - Product requirements: the "Only requirement 1 is built so far" line, and requirement 2 gains the decisions above (public access, unique name, the level and its four values, prices zero or more)
  - Architecture: `classes/` no longer has "only `Student`"; describe `Subject` and that `classes/urls.py` is mounted at the root
- `.claude/agents/quantum-test-writer.md` — its copies of the subject rules describe `levels`. The other command and agent files do not describe subject fields and are unchanged
- For the change to several levels per subject: `classes/serializers.py`, `classes/views.py`, `classes/admin.py`, and, because a weekly class returns its subject's levels, `.claude/specs/03-weekly-classes.md` and Product requirements 3 in `CLAUDE.md`

## Files to create
- `classes/serializers.py`
- `classes/urls.py`
- `classes/migrations/0002_subject.py` (generated by `makemigrations`)
- `classes/migrations/0004_level_subject_levels.py`, `0005_seed_levels.py` and `0006_remove_subject_level.py` (see Models and database changes)

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
- Levels are rows of the `Level` model linked by a `ManyToManyField`, never an array column, free text or a `TextChoices` on `Subject`
- The four levels are created by the data migration, never by a fixture, a signal or application code, and the level names are not copied into the serializer
- The data migration uses `apps.get_model`, never an import of the real models
- `levels` is read-only in the API and returned as a list of `{"code", "name"}` objects
- Any queryset that serializes subjects prefetches `levels`
- The subject queryset is not filtered by user
- Do not add fields the spec does not list (no description, no active flag, no currency field: prices are USD by definition)
- The non-negative price rule is enforced twice: a `MinValueValidator` on each price field and a `CheckConstraint` per price
- Use `Decimal("0")`, not a float, in the validator
- Do not change `COERCE_DECIMAL_TO_STRING`; prices stay JSON numbers
- Register on a `SimpleRouter` in `classes/urls.py` and mount it at the root of `config/urls.py`; do not add a `/api/` or app prefix
- Generate schema migrations with `makemigrations`; only the data migration is written by hand
- Do not write tests during implementation

## Tests
Covered by `classes/tests/test_subjects.py`, written and run with `/test-feature subjects`, not as part of implementation. It must cover:
- `GET /subjects/`: 200 for an anonymous request and for an authenticated student; returns every subject; an empty list when there are none; subjects ordered by name; the body is a plain list (not paginated)
- `GET /subjects/{id}/`: 200 for an anonymous request and for an authenticated student; 404 for an id that does not exist
- Response shape: exactly `id`, `name`, `levels`, `price_40_min`, `price_60_min`; `levels` is a list of objects with exactly `code` and `name`; a subject with one level returns a one-item list and a subject with several returns all of them, in the order of Requirements 10; each of the four levels returns its code and matching name; both prices returned as decimals and compared as `Decimal`; a subject whose two prices differ returns each in the right field
- Read-only: `POST /subjects/` and `PUT` / `PATCH` / `DELETE /subjects/{id}/` return 405, anonymous and authenticated, and create, change or delete nothing
- Model rules: a duplicate name raises `IntegrityError`; a negative price fails `full_clean()` and, saved without validation, raises `IntegrityError`; a price of 0 is accepted
- Levels: the four levels of Requirements 10 exist in the test database with their codes and names, without the test creating them (the data migration ran); a duplicate level code raises `IntegrityError`; two subjects can share a level
- Query count: `GET /subjects/` runs the same number of queries for one subject as for several

Tests fetch the seeded levels (`Level.objects.get(code="o_level")`) rather than creating levels with those codes, which would break the unique constraint. The rule that the admin form requires at least one level is a form rule and is not covered by the API tests.

## Definition of done
- [ ] `uv run python manage.py makemigrations --check` reports no missing migrations
- [ ] Each route returns the expected status for an anonymous request (`GET /subjects/` and `GET /subjects/{id}/` return 200; `POST /subjects/` and `PUT` / `PATCH` / `DELETE /subjects/{id}/` return 405)
- [ ] The feature's routes are marked Implemented in `CLAUDE.md`
- [ ] `uv run python manage.py migrate` applies the `classes` migrations cleanly, on an empty database and on one that already holds subjects
- [ ] After migrating, the four levels exist, and every subject that had a level before has it among its levels (an "O/A Level" subject has O Level and A Level)
- [ ] A subject created in the Django admin appears in `GET /subjects/` with `id`, `name`, `levels`, `price_40_min` and `price_60_min`, the levels as a list of `code` and `name` objects and the prices as JSON numbers
- [ ] `GET /subjects/` lists subjects in name order
- [ ] `GET /subjects/{id}/` returns that subject, and 404 for an unknown id
- [ ] `GET /subjects/` with a valid `JWT` token returns the same body as the anonymous request
- [ ] In the Django admin, Subject has a list page showing name, levels and both prices, can be searched by name and filtered by level; its form lets an admin pick several levels and refuses to save with none; Level has its own list page
- [ ] The admin rejects a negative price and a duplicate name with a form error, and accepts a price of 0
- [ ] `GET /` returns 404 (no API root view was added)
- [ ] `uv run pytest classes/tests/test_subjects.py` passes (after `/test-feature subjects`)
