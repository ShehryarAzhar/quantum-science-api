# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack

Django 6.1 + Django REST Framework API on Python 3.14, backed by MySQL. Dependencies are managed with `uv` (`pyproject.toml` / `uv.lock`); there is no `requirements.txt`.

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
- `classes/` — domain app, currently an empty scaffold.

### Auth

Authentication is entirely delegated to Djoser + SimpleJWT; there are no hand-written auth views.

- `AUTH_USER_MODEL = "core.User"`: an `AbstractUser` subclass whose only change is making `email` unique. Always reference the user via `settings.AUTH_USER_MODEL` / `get_user_model()`.
- `config/urls.py` mounts both `djoser.urls` and `djoser.urls.jwt` under `auth/`, giving `auth/users/`, `auth/users/me/`, `auth/jwt/create/`, `auth/jwt/refresh/`, `auth/jwt/verify/`, etc.
- The `Authorization` header prefix is `JWT`, not `Bearer` (`SIMPLE_JWT["AUTH_HEADER_TYPES"]`).
- Djoser serializers are overridden through the `DJOSER["SERIALIZERS"]` setting. `core.serializers.UserCreateSerializer` extends the registration payload with `first_name` / `last_name`. To change other Djoser payloads (e.g. `current_user`), subclass the Djoser serializer in `core/serializers.py` and register it in that setting rather than writing a new view.
- `core.admin.UserAdmin` extends the stock `UserAdmin` add form with email and name fields, since email is required to be unique.

`REST_FRAMEWORK` sets only the default authentication class (JWT). No default permission class is set, so DRF's `AllowAny` default applies — new views must declare their own `permission_classes`.

Email uses the console backend, so Djoser emails (activation, password reset) print to the dev server's stdout.
