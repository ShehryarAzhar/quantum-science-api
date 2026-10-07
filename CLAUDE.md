# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Backend API for a Science Tutor web application. This repo is backend only: a separate Next.js + TypeScript frontend consumes the API, so there are no templates or server-rendered pages here.

## Stack

Django 6.1 + Django REST Framework API on Python 3.14, backed by MySQL. Dependencies are managed with `uv` (`pyproject.toml` / `uv.lock`); there is no `requirements.txt`.

## Product requirements

None of the features below are built yet (see Implemented vs Stub Routes).

1. **Subjects** — each subject has two USD prices: one for a 40-minute class and one for a 60-minute class. Store prices in `DecimalField`, never `FloatField`. The API is read-only for subjects (list and retrieve); admins create and edit them in the Django admin site, so use `ReadOnlyModelViewSet` and register the model in `classes/admin.py`.
2. **Weekly class scheduling** — a user books a weekly recurring class by choosing subject, day of the week, time, and a duration of 40 or 60 minutes.
   - A user may book several classes of the same subject in one week.
   - Two classes cannot be booked in the same timeslot. This is enforced across all users, not per student: once any student holds a weekday + hour slot, nobody else can book it.
   - Classes start only on the full hour (4:00, 5:00, ...); reject any other time.
   - Reject the booking if an upcoming trial lesson (any student's) occupies that weekday and hour. A trial lesson whose date has passed no longer blocks the slot.
3. **Trial lessons** — a user books a trial lesson by choosing a subject and a specific date and time. A trial lesson lasts 60 minutes, is free, and must start on the full hour like weekly classes.
   - Each student can book only one trial lesson; reject a second booking on the server and back it with a database uniqueness constraint on the user.
   - A trial lesson can be marked completed, but only in the Django admin; the completed flag is read-only in the API.
   - While the trial lesson is not completed and its date and time have not passed, the student can edit or delete it. Deleting it frees the student to book another.
   - Once it is marked completed or its date and time have passed, it is locked: the student cannot edit or delete it through the API, and because it still counts as their one trial lesson, they cannot create another. It stays readable.
   - Reject the booking if any student's weekly class occupies that time (same weekday and hour as the chosen date and time).
   - Reject the booking if any student's trial lesson is already booked at that time.
4. **My schedule** — returns the logged-in user's schedule together with their total cost per week. Trial lessons are free and add nothing to it. The weekly cost is the sum of the prices of all the user's weekly classes, each priced by its own duration (the subject's 40-minute price or its 60-minute price).

## API conventions

- The API serves students only. Everything teacher- or admin-side (managing subjects, viewing and editing all students' classes and trial lessons, managing users) is done in the Django admin site, so register every model in `admin.py` and do not build teacher-facing endpoints.
- Scope every booking queryset to `request.user`; a student must never see or modify another student's classes or trial lessons. Timeslot clash checks are the exception: they must look at every user's bookings.
- Prefer `ModelViewSet` registered on a DRF router. When an endpoint does not map onto a model's CRUD (e.g. my schedule, which aggregates and totals), use whatever fits best (`APIView`, a generic view, or a viewset `@action`).
- Enforce booking rules (full hour, no timeslot clash) on the server in serializers/models, backed by a database constraint where possible; do not rely on the frontend.

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

Tests run through pytest with `pytest-django` (`pytest.ini` sets `DJANGO_SETTINGS_MODULE=config.settings`). Each app keeps its tests in its own `tests/` package: `<app>/tests/__init__.py` plus `test_*.py` modules (e.g. `core/tests/test_users.py`). `pytest.ini` does not set `python_files`, so only `test_*.py` / `*_test.py` files are collected.

The `tests.py` stub that `startapp` generates is not collected and clashes with a `tests/` package of the same name — delete it when creating the app's `tests/` folder.

## Architecture

- `config/` — the Django project (settings, root URLconf, WSGI/ASGI). There is a single settings module; no per-environment split.
- `core/` — custom user model and auth customisation.
- `classes/` — domain app for subjects, weekly classes, trial lessons and the schedule; currently an empty scaffold.

### Auth

Authentication is entirely delegated to Djoser + SimpleJWT; there are no hand-written auth views.

- `AUTH_USER_MODEL = "core.User"`: an `AbstractUser` subclass whose only change is making `email` unique. Always reference the user via `settings.AUTH_USER_MODEL` / `get_user_model()`.
- `config/urls.py` mounts both `djoser.urls` and `djoser.urls.jwt` under `auth/`, giving `auth/users/`, `auth/users/me/`, `auth/jwt/create/`, `auth/jwt/refresh/`, `auth/jwt/verify/`, etc.
- The `Authorization` header prefix is `JWT`, not `Bearer` (`SIMPLE_JWT["AUTH_HEADER_TYPES"]`).
- Djoser serializers are overridden through the `DJOSER["SERIALIZERS"]` setting. `core.serializers.UserCreateSerializer` extends the registration payload with `first_name` / `last_name`. To change other Djoser payloads (e.g. `current_user`), subclass the Djoser serializer in `core/serializers.py` and register it in that setting rather than writing a new view.
- `core.admin.UserAdmin` extends the stock `UserAdmin` add form with email and name fields, since email is required to be unique.

`REST_FRAMEWORK` sets only the default authentication class (JWT). No default permission class is set, so DRF's `AllowAny` default applies — new views must declare their own `permission_classes`.

Email uses the console backend, so Djoser emails (activation, password reset) print to the dev server's stdout.

## Implemented vs Stub Routes

Keep this section current: whenever a route is added, removed, renamed, or goes from Stub to Implemented, update the tables in the same change.

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

Read-only by design; subjects are managed in the Django admin.

| Method | Path | Status |
| --- | --- | --- |
| GET | `/subjects/` | Stub |
| GET | `/subjects/{id}/` | Stub |

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
