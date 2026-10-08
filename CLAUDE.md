# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Backend API for a Science Tutor web application. This repo is backend only: a separate Next.js + TypeScript frontend consumes the API, so there are no templates or server-rendered pages here.

## Stack

Django 6.1 + Django REST Framework API on Python 3.14, backed by MySQL. Dependencies are managed with `uv` (`pyproject.toml` / `uv.lock`); there is no `requirements.txt`.

## Product requirements

Only requirements 1 and 2 are built so far (see Implemented vs Stub Routes). The numbering 1–5 matches the spec numbers (requirement 2 is `.claude/specs/02-subjects.md`) and is referenced by the slash commands ("Product requirements 4"), so keep it stable.

1. **Users and student profile** — a user registers with username, email, password, first and last name and a phone number, and logs in with a JWT. Auth is delegated to Djoser + SimpleJWT; Architecture > Auth describes how it is built.
   - Email is unique.
   - The phone number is required at registration: an optional `+` followed by 7 to 15 digits. Surrounding whitespace is rejected, not stripped. It is not unique.
   - Registering creates the user's Student profile, which holds the phone number. The user and the Student are created together or not at all.
   - Users created outside registration (`createsuperuser`, the Django admin) have no phone number and no Student.
   - A student can read their own details, including the phone number, at `/auth/users/me/`, and edit their email, first name and last name there. Username and phone number cannot be changed through the API; the phone number is edited in the Django admin.
   - A student can delete their own account, which deletes their Student.
2. **Subjects** — each subject has two USD prices: one for a 40-minute class and one for a 60-minute class. Store prices in `DecimalField`, never `FloatField`. The API is read-only for subjects (list and retrieve); admins create and edit them in the Django admin site, so use `ReadOnlyModelViewSet` and register the model in `classes/admin.py`.
   - The subject routes are public: anyone can list and retrieve subjects without logging in.
   - A subject has a name, a level and the two prices, nothing else.
   - The level is the level the tutor teaches the subject at. Each subject has exactly one, chosen from four fixed values: `all_grades` (All Grades (1-O Level)), `o_level` (O Level), `o_a_level` (O/A Level) and `university` (University Level). The API returns the code as `level` and the label as `level_display`.
   - The name is unique.
   - A price is zero or more: a negative price is rejected, a free subject (0.00) is allowed. The two prices are independent; neither has to be lower than the other.
3. **Weekly class scheduling** — a user books a weekly recurring class by choosing subject, day of the week, time, and a duration of 40 or 60 minutes.
   - A user may book several classes of the same subject in one week.
   - Two classes cannot be booked in the same timeslot. This is enforced across all users, not per student: once any student holds a weekday + hour slot, nobody else can book it.
   - Classes start only on the full hour (4:00, 5:00, ...); reject any other time.
   - Reject the booking if an upcoming trial lesson (any student's) occupies that weekday and hour. A trial lesson whose date has passed no longer blocks the slot.
4. **Trial lessons** — a user books a trial lesson by choosing a subject and a specific date and time. A trial lesson lasts 60 minutes, is free, and must start on the full hour like weekly classes.
   - Each student can book only one trial lesson; reject a second booking on the server and back it with a database uniqueness constraint on the user.
   - A trial lesson can be marked completed, but only in the Django admin; the completed flag is read-only in the API.
   - While the trial lesson is not completed and its date and time have not passed, the student can edit or delete it. Deleting it frees the student to book another.
   - Once it is marked completed or its date and time have passed, it is locked: the student cannot edit or delete it through the API, and because it still counts as their one trial lesson, they cannot create another. It stays readable.
   - Reject the booking if any student's weekly class occupies that time (same weekday and hour as the chosen date and time).
   - Reject the booking if any student's trial lesson is already booked at that time.
5. **My schedule** — returns the logged-in user's schedule together with their total cost per week. Trial lessons are free and add nothing to it. The weekly cost is the sum of the prices of all the user's weekly classes, each priced by its own duration (the subject's 40-minute price or its 60-minute price).

## API conventions

- The API serves students only. Everything teacher- or admin-side (managing subjects, viewing and editing all students' classes and trial lessons, managing users) is done in the Django admin site, so register every model in `admin.py` and do not build teacher-facing endpoints.
- Scope every booking queryset to `request.user`; a student must never see or modify another student's classes or trial lessons. Timeslot clash checks are the exception: they must look at every user's bookings.
- Prefer `ModelViewSet` registered on a DRF router. When an endpoint does not map onto a model's CRUD (e.g. my schedule, which aggregates and totals), use whatever fits best (`APIView`, a generic view, or a viewset `@action`).
- Enforce booking rules (full hour, no timeslot clash) on the server in serializers/models, backed by a database constraint where possible; do not rely on the frontend.

## Feature workflow

Each feature goes through the same four steps, driven by the slash commands in `.claude/commands/`:

1. `/create-spec <feature>` — needs a clean working tree. It branches `feature/<feature>` off an up-to-date `main` and writes the feature's spec file. Build features in the order of the table below: later specs pick up rules that earlier ones deferred.
2. Implement from the spec, in Plan Mode. Do not write tests during implementation. Update the route tables in the same change.
3. `/test-feature <feature>` — `quantum-test-writer` writes the test file from the spec, then `quantum-test-runner` runs only that file.
4. `/code-review-feature <feature>` — `quantum-security-reviewer` and `quantum-quality-reviewer` review the branch's changes in parallel. Apply the action plan only after the user approves it, then re-run `/test-feature`.

| Feature | Requirement | Spec file | Routes | Test file |
| --- | --- | --- | --- | --- |
| `users` | 1 | `.claude/specs/01-users.md` | `/auth/...` | `core/tests/test_users.py` |
| `subjects` | 2 | `.claude/specs/02-subjects.md` | `/subjects/` | `classes/tests/test_subjects.py` |
| `weekly-classes` | 3 | `.claude/specs/03-weekly-classes.md` | `/classes/` | `classes/tests/test_weekly_classes.py` |
| `trial-lessons` | 4 | `.claude/specs/04-trial-lessons.md` | `/trial-lessons/` | `classes/tests/test_trial_lessons.py` |
| `schedule` | 5 | `.claude/specs/05-schedule.md` | `/schedule/` | `classes/tests/test_schedule.py` |

- The test runner and both reviewers are read-only and never fix anything. An implementation bug is fixed in the main session; a test bug goes back to `quantum-test-writer`. Never weaken, skip or delete a test to make it pass.
- `/test-feature` and `/code-review-feature` refuse to run while the feature's routes are still marked Stub.

### Specs

- `.claude/specs/<NN>-<feature>.md`, written by `/create-spec`, is the detailed contract for one feature and records the decisions the user made on ambiguous behaviour.
- This file is the source a spec is written from. If a spec and this file contradict each other, stop and ask; do not pick one.
- A spec's "Deferred rules" section lists rules that wait for a later feature (e.g. the trial lesson clash check on weekly classes before trial lessons exist). A deferred rule is not a bug or a missing test until the spec that picks it up is implemented.
- The `users` spec, `.claude/specs/01-users.md`, was written by hand after the feature was built, not by `/create-spec`.

## Commands

```bash
uv sync                                  # install deps (including dev group) into .venv
uv run python manage.py runserver        # dev server
uv run python manage.py makemigrations   # after model changes
uv run python manage.py migrate
uv run python manage.py createsuperuser

uv run pytest                            # all tests
uv run pytest <app>/tests/               # one app
uv run pytest <app>/tests/test_<name>.py # one file
uv run pytest <app>/tests/test_<name>.py::test_name   # one test
uv run pytest -k "expression"            # by name match
```

No linter or formatter is configured.

## Environment

Settings load `.env` from the repo root via `python-dotenv`. Copy `.env.example` to `.env` and set `DB_NAME`, `DB_HOST`, `DB_USER`, `DB_PASSWORD`. A running MySQL server is required for the dev server, migrations, and any test that touches the database (pytest-django creates a `test_<DB_NAME>` database, so the MySQL user needs permission to create databases).

## Testing

Tests run through pytest with `pytest-django` and `model-bakery` (`pytest.ini` sets `DJANGO_SETTINGS_MODULE=config.settings`). Each app keeps its tests in its own `tests/` package: `<app>/tests/__init__.py` plus `test_*.py` modules (e.g. `core/tests/test_users.py`). `pytest.ini` does not set `python_files`, so only `test_*.py` / `*_test.py` files are collected.

The `tests.py` stub that `startapp` generates is not collected and clashes with a `tests/` package of the same name — delete it when creating the app's `tests/` folder.

Tests are normally written by `quantum-test-writer` through `/test-feature`. Tests written by hand follow the same conventions:

- Write tests from the spec, not from the implementation; read the source only for field names and paths.
- Shared fixtures (`api_client`, `authenticate`) live in a `conftest.py` at the repo root so both apps can use them.
- Build setup data with `model_bakery` (`baker.make(...)`), and authenticate with `force_authenticate` rather than the JWT flow.
- `baker.make(get_user_model())` does not create a Student (only registration does); when a test needs one, add `baker.make(Student, user=user)`.
- One class per action, marked `@pytest.mark.django_db` (e.g. `TestCreateWeeklyClass`), with tests named `test_if_<condition>_returns_<status>`.
- Use `rest_framework.status` constants, never bare numbers, and compare money as `Decimal`.

## Architecture

- `config/` — the Django project (settings, root URLconf, WSGI/ASGI). There is a single settings module; no per-environment split.
- `core/` — custom user model, auth customisation and the registration signal that creates a user's `Student` profile.
- `classes/` — domain app for the `Student` profile, subjects, weekly classes, trial lessons and the schedule; only `Student` and `Subject` exist so far. Its viewsets are registered on the `SimpleRouter` in `classes/urls.py`, which `config/urls.py` mounts at the root (no app prefix); later features register on the same router.
- `.claude/` — Claude Code slash commands (`commands/`), subagents (`agents/`) and feature specs (`specs/`, created by `/create-spec`). See Claude Code tooling.

### Auth

Authentication is entirely delegated to Djoser + SimpleJWT; there are no hand-written auth views.

- `AUTH_USER_MODEL = "core.User"`: an `AbstractUser` subclass whose only change is making `email` unique. Always reference the user via `settings.AUTH_USER_MODEL` / `get_user_model()`.
- `config/urls.py` mounts both `djoser.urls` and `djoser.urls.jwt` under `auth/`, giving `auth/users/`, `auth/users/me/`, `auth/jwt/create/`, `auth/jwt/refresh/`, `auth/jwt/verify/`, etc.
- The `Authorization` header prefix is `JWT`, not `Bearer` (`SIMPLE_JWT["AUTH_HEADER_TYPES"]`).
- `DJOSER["TOKEN_MODEL"]` is `None` because the project is JWT-only and `rest_framework.authtoken` is not installed; without it Djoser's `DELETE /auth/users/me/` crashes trying to delete a DRF token.
- Djoser serializers are overridden through the `DJOSER["SERIALIZERS"]` setting. `core.serializers.UserCreateSerializer` extends the registration payload with `first_name` / `last_name` and a required, write-only `phone_number`. `core.serializers.CurrentUserSerializer` adds `first_name` / `last_name` (editable with `PUT`/`PATCH`) and a read-only `phone_number` to `/auth/users/me/`; `username` stays read-only there. To change other Djoser payloads, subclass the Djoser serializer in `core/serializers.py` and register it in that setting rather than writing a new view.
- `core.admin.UserAdmin` extends the stock `UserAdmin` add form with email and name fields, since email is required to be unique, and shows the user's `Student` inline.

#### Student profile

- `classes.Student` is the profile of a registered student: a one-to-one to `settings.AUTH_USER_MODEL` (`related_name="student"`, deleted with the user) plus a required `phone_number` (optional `+`, 7–15 digits, not unique). It lives in `classes`, not `core`, because a class cannot exist without a student. It is registered in `classes/admin.py`.
- A Student is created by a `post_save` signal on the user model: the handler is `core.signals.create_student`, connected in `CoreConfig.ready()`. It creates a Student only for a newly created user that carries a `_phone_number` attribute (named by `core.signals.PHONE_NUMBER_ATTR`, which the serializer imports).
- Only registration sets that attribute. `UserCreateSerializer.validate()` takes `phone_number` out of the attrs while Djoser validates the password (Djoser builds `User(**attrs)`), and `perform_create()` builds the user itself instead of calling `create_user()`, attaches `_phone_number`, and saves inside `transaction.atomic()`. The signal runs inside that transaction, so if the Student cannot be created the user is not created either.
- Users created by `createsuperuser` or in the Django admin have no phone number and get no Student, so never assume `user.student` exists: `/auth/users/me/` returns `phone_number: null` for them. An admin can add a Student through the inline on the User page.
- `phone_number` cannot be changed through `/auth/users/me/`; it is edited in the Django admin.

`REST_FRAMEWORK` sets only the default authentication class (JWT). No default permission class is set, so DRF's `AllowAny` default applies — new views must declare their own `permission_classes`.

Email uses the console backend, so Djoser emails (activation, password reset) print to the dev server's stdout.

## Claude Code tooling

Commands (`.claude/commands/`):

- `/create-spec <feature>` — creates the feature branch and writes `.claude/specs/<NN>-<feature>.md`. Writes no application code.
- `/test-feature <feature>` — runs `quantum-test-writer`, then `quantum-test-runner`. Fixes nothing.
- `/code-review-feature <feature>` — runs both reviewers in parallel and merges their reports. Edits files only after the user approves the action plan.

Agents (`.claude/agents/`):

- `quantum-test-writer` — writes tests from the spec. It may only touch `<app>/tests/` and the root `conftest.py`, and keeps its own project memory under `.claude/agent-memory/`.
- `quantum-test-runner` — runs one test file and classifies each failure as an implementation bug, a test bug or an environment problem. Read-only.
- `quantum-security-reviewer` — reviews changed code for permissions, queryset scoping, serializer exposure and rule bypasses. Read-only.
- `quantum-quality-reviewer` — reviews changed code for project conventions, Django and DRF idioms and spec conformance. Read-only.

The command and agent files refer to this file by heading name and requirement number ("Product requirements 4", "API conventions", "Architecture > Auth", "Implemented vs Stub Routes") and carry their own copies of the booking rules and the feature table. When a product requirement, an API convention, a heading or a feature name changes here, update those files in the same change.

## Implemented vs Stub Routes

Keep this section current: whenever a route is added, removed, renamed, or goes from Stub to Implemented, update the tables in the same change. `/test-feature` and `/code-review-feature` read these tables and stop while a feature's routes are still marked Stub.

- **Implemented** — the route is registered in the URLconf and works.
- **Stub** — planned from the product requirements, no code yet. Stub paths are proposals and may change when built.

Only student-facing routes are listed. `admin/` (Django admin site) is not part of the API. Djoser also registers `GET /auth/users/` and `GET`/`PUT`/`PATCH`/`DELETE /auth/users/{id}/`; they are left out because managing other users is admin work, and students use `/auth/users/me/`.

### Auth (Djoser + SimpleJWT, mounted in `config/urls.py`)

| Method | Path | Status |
| --- | --- | --- |
| POST | `/auth/users/` | Implemented |
| GET | `/auth/users/me/` | Implemented |
| PUT | `/auth/users/me/` | Implemented |
| PATCH | `/auth/users/me/` | Implemented |
| DELETE | `/auth/users/me/` | Implemented |
| POST | `/auth/users/activation/` | Implemented |
| POST | `/auth/users/resend_activation/` | Implemented |
| POST | `/auth/users/set_password/` | Implemented |
| POST | `/auth/users/reset_password/` | Implemented |
| POST | `/auth/users/reset_password_confirm/` | Implemented |
| POST | `/auth/users/set_username/` | Implemented |
| POST | `/auth/users/reset_username/` | Implemented |
| POST | `/auth/users/reset_username_confirm/` | Implemented |
| POST | `/auth/jwt/create/` | Implemented |
| POST | `/auth/jwt/refresh/` | Implemented |
| POST | `/auth/jwt/verify/` | Implemented |

### Subjects

Read-only by design; subjects are managed in the Django admin. Both routes are public.

| Method | Path | Status |
| --- | --- | --- |
| GET | `/subjects/` | Implemented |
| GET | `/subjects/{id}/` | Implemented |

### Weekly classes

| Method | Path | Status |
| --- | --- | --- |
| GET | `/classes/` | Stub |
| POST | `/classes/` | Stub |
| GET | `/classes/{id}/` | Stub |
| PUT | `/classes/{id}/` | Stub |
| PATCH | `/classes/{id}/` | Stub |
| DELETE | `/classes/{id}/` | Stub |

### Trial lessons

| Method | Path | Status |
| --- | --- | --- |
| GET | `/trial-lessons/` | Stub |
| POST | `/trial-lessons/` | Stub |
| GET | `/trial-lessons/{id}/` | Stub |
| PUT | `/trial-lessons/{id}/` | Stub |
| PATCH | `/trial-lessons/{id}/` | Stub |
| DELETE | `/trial-lessons/{id}/` | Stub |

### My schedule

| Method | Path | Status |
| --- | --- | --- |
| GET | `/schedule/` | Stub |
