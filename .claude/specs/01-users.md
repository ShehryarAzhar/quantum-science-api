# Spec: Users and Student Profile

## Overview
Every user who registers through the API is a student, and a student needs a profile that the rest of the domain can hang off: a class cannot exist without a student. This feature adds a `Student` profile (one-to-one with the user, holding a required phone number) that is created automatically when a user registers through Djoser, exposes the phone number and the user's names on the current user endpoint, and fixes account deletion for a JWT-only project. Authentication itself stays entirely delegated to Djoser + SimpleJWT. It is built first because weekly classes, trial lessons and the schedule all belong to a student.

## Depends on
No dependencies.

## Requirements
1. Authentication is delegated to Djoser + SimpleJWT, mounted under `auth/`. There are no hand-written auth views.
2. The user model is `core.User`, an `AbstractUser` subclass whose only change is a unique `email`.
3. The `Authorization` header prefix is `JWT`, not `Bearer`.
4. `Student` is the profile of a registered student. It has a one-to-one relation to the user and a required `phone_number`. Deleting the user deletes the Student.
5. `Student` lives in the `classes` app, not `core`, because a class cannot exist without a student.
6. A phone number is an optional leading `+` followed by 7 to 15 digits. Nothing else is allowed: a number with leading or trailing whitespace or a newline (e.g. `"1234567\n"`, `" 1234567"`) is rejected with 400, not stripped and accepted. It is not unique: two students may share a number.
7. Registration (`POST /auth/users/`) takes `username`, `email`, `password`, `first_name`, `last_name` and a required `phone_number`.
8. `phone_number` is write-only on registration: it is not returned in the registration response. The password is not returned either.
9. Registering creates a Student for the new user with the given phone number. The Student is created by a `post_save` signal on the user model, not by the serializer or a view.
10. A registration with a missing or invalid phone number is rejected with 400 and no user is created.
11. User creation and Student creation are atomic: if the Student cannot be created, the user is not created either.
12. Users created outside registration (`createsuperuser`, the Django admin, `create_user`) have no phone number. They get no Student and creating them must not raise. Code must never assume `user.student` exists.
13. `GET /auth/users/me/` returns `id`, `username`, `email`, `first_name`, `last_name` and `phone_number`. `phone_number` is `null` for a user without a Student.
14. `PUT` / `PATCH /auth/users/me/` can change `email`, `first_name` and `last_name`.
15. `username` and `phone_number` are read-only on `/auth/users/me/`. A value sent for either is ignored (the request still succeeds with 200) and the stored value does not change. Sending a `phone_number` for a user without a Student does not create one. The phone number is edited in the Django admin.
16. `DELETE /auth/users/me/` deletes the user and, with it, their Student, and returns 204. Other users' Students are untouched.
17. `/auth/users/me/` only ever returns and changes the logged-in user's own data.
18. `/auth/users/me/` requires authentication; an anonymous request returns 401.

## Deferred rules
No deferred rules.

## Routes
No new routes. The feature changes the payloads of routes Djoser already registers:
- `POST /auth/users/` — register; now requires `phone_number` and creates a Student — public
- `GET /auth/users/me/` — current user; now includes `first_name`, `last_name`, `phone_number` — authenticated student
- `PUT /auth/users/me/` — update current user; names editable — authenticated student
- `PATCH /auth/users/me/` — partial update of current user; names editable — authenticated student
- `DELETE /auth/users/me/` — delete own account and Student — authenticated student
- `POST /auth/jwt/create/` — obtain `access` and `refresh` tokens — public (unchanged)

## Models and database changes
`classes.Student` (new):
- `user` — `OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student")`. The one-to-one gives a database uniqueness constraint on the user.
- `phone_number` — `CharField(max_length=PHONE_NUMBER_MAX_LENGTH)` (20), required, validated by `phone_number_validator`, a `RegexValidator` for `^\+?[0-9]{7,15}\Z` (`\Z`, not `$`, so a trailing newline is rejected). `PHONE_NUMBER_MAX_LENGTH` is defined in `classes/constants.py` and the validator in `classes/validators.py`. Not unique.
- `__str__` returns the user's username.

`core.User` is unchanged.

The migration is generated with `uv run python manage.py makemigrations classes` (`classes/migrations/0001_initial.py`, depending on the swappable user model).

## Serializers and validation
`core.serializers.UserCreateSerializer` (extends Djoser's `UserCreateSerializer`, registered as `DJOSER["SERIALIZERS"]["user_create"]`):
- Fields: `id`, `username`, `first_name`, `last_name`, `email`, `password`, `phone_number`.
- `phone_number` is a declared `CharField`: required, write-only, `max_length=PHONE_NUMBER_MAX_LENGTH`, `trim_whitespace=False` (so surrounding whitespace reaches the validator and is rejected, not stripped), validated by `phone_number_validator`. A missing value returns 400 `{"phone_number": ["This field is required."]}`; an invalid one returns 400 with the validator's message under `phone_number`.
- `validate()` removes `phone_number` from the attrs before calling Djoser's `validate()` (which builds `User(**attrs)` to validate the password and would fail on an unknown field), then puts it back.
- `perform_create()` does not call `create_user()`, because that saves in the same call that builds the user. Inside `transaction.atomic()` it builds the user, normalises username and email, hashes the password, sets `is_active = False` when Djoser's `SEND_ACTIVATION_EMAIL` is on, attaches the phone number as `user._phone_number` (the attribute name is the `PHONE_NUMBER_ATTR` constant in `core/signals.py`, shared with the signal), and saves.
- Email uniqueness and password strength are enforced by the model and Djoser as before; both return 400.

`core.serializers.CurrentUserSerializer` (extends Djoser's `UserSerializer`, registered as `DJOSER["SERIALIZERS"]["current_user"]`):
- Fields: Djoser's (`email`, `id`, `username`) plus `first_name`, `last_name`, `phone_number`.
- `username` is read-only (Djoser's `read_only_fields`).
- `phone_number` is a `SerializerMethodField`, so it is read-only: it returns `user.student.phone_number`, or `None` when the user has no Student.

`core.signals.create_student` (`post_save` receiver for `settings.AUTH_USER_MODEL`, connected by importing `core.signals` in `CoreConfig.ready()`):
- Does nothing unless the user was just created, and nothing for raw saves (fixtures).
- Creates a Student only when the instance carries a non-empty `_phone_number`.
- Runs inside the serializer's transaction, so a failure rolls the user back.

## Views and URLs
No views are written. `config/urls.py` already mounts `djoser.urls` and `djoser.urls.jwt` under `auth/`. Djoser's `UserViewSet` supplies the permissions (registration is public, `/auth/users/me/` requires authentication).

`config/settings.py`, `DJOSER`:
- `"TOKEN_MODEL": None` — the project is JWT-only and `rest_framework.authtoken` is not installed; without this, `DELETE /auth/users/me/` crashes when Djoser tries to delete a DRF token.
- `"SERIALIZERS"`: `user_create` and `current_user` point at the two serializers above.

## Admin
- `classes/admin.py` registers `Student` (`StudentAdmin`): list shows user and phone number, searchable by username, email and phone number, with an autocomplete user field.
- `core/admin.py`: `UserAdmin` shows the Student as a stacked inline (`StudentInline`, `can_delete = False`). An admin can add or edit a user's phone number there; left blank on a new user, no Student is created.
- Admin-only: creating a Student for a user who did not register through the API, and changing a phone number.

## Files to change
- `classes/models.py`
- `classes/admin.py`
- `core/apps.py`
- `core/serializers.py`
- `core/admin.py`
- `config/settings.py`
- `CLAUDE.md` (Product requirements 1, Architecture, Architecture > Auth, Testing; the route tables are unchanged because no route is added)
- `.claude/agents/quantum-quality-reviewer.md`, `.claude/agents/quantum-security-reviewer.md`, `.claude/agents/quantum-test-writer.md`
- `.claude/commands/test-feature.md`, `.claude/commands/code-review-feature.md`

## Files to create
- `core/signals.py`
- `classes/migrations/0001_initial.py`

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
- Do not write auth views. Change Djoser payloads only by subclassing the Djoser serializer in `core/serializers.py` and registering it in `DJOSER["SERIALIZERS"]`
- The Student is created by the `post_save` signal, with the handler in `core/signals.py` and the connection made in `CoreConfig.ready()`
- The signal must not fail for a user without a phone number
- User and Student creation happen in one transaction
- `phone_number` is never writable through `/auth/users/me/`

## Tests
Covered by `core/tests/test_users.py`, written and run with `/test-feature users`, not as part of implementation. It must cover:
- Registration: 201 with the expected fields; user and Student created; `phone_number` and `password` not in the response
- Phone number validation: valid shapes accepted (7 digits, 15 digits, with `+`); missing and invalid values, including a number with surrounding whitespace or a trailing newline, return 400 and create nothing
- Atomicity: when Student creation fails, no user is left behind
- Duplicate email, missing required fields and a weak password return 400
- Users created with `baker.make`, `create_user` and `create_superuser` get no Student and raise nothing
- `GET /auth/users/me/`: 401 when anonymous; returns names and `phone_number`; `phone_number` is `null` without a Student; only the logged-in user's data
- `PUT` / `PATCH /auth/users/me/`: 401 when anonymous; names and email update; `username` and `phone_number` do not change; no Student is created for a user without one
- `DELETE /auth/users/me/`: 401 when anonymous; 204 and the Student is deleted; other Students are kept
- `POST /auth/jwt/create/`: tokens for valid credentials, 401 for a wrong password, 400 for missing credentials
- Header prefix: `JWT <token>` authenticates; `Bearer <token>` and an invalid token return 401

## Definition of done
- [ ] `uv run python manage.py makemigrations --check` reports no missing migrations
- [ ] Each route returns the expected status for an anonymous request (`POST /auth/users/` and `POST /auth/jwt/create/` are public; every method on `/auth/users/me/` returns 401)
- [ ] The feature's routes are marked Implemented in `CLAUDE.md`
- [ ] `POST /auth/users/` with a valid `phone_number` returns 201 without `phone_number` in the body, and a Student row exists for the new user
- [ ] `POST /auth/users/` without `phone_number`, or with an invalid one, returns 400 and creates no user
- [ ] Forcing Student creation to fail during registration leaves no user row
- [ ] `uv run python manage.py createsuperuser` succeeds and creates no Student
- [ ] `GET /auth/users/me/` returns `first_name`, `last_name` and `phone_number` (`null` for the superuser)
- [ ] `PATCH /auth/users/me/` changes `first_name` / `last_name` and leaves `username` and `phone_number` unchanged
- [ ] `DELETE /auth/users/me/` returns 204 and removes the user's Student
- [ ] In the Django admin, the User page shows the Student inline and Student has its own list page
- [ ] `uv run pytest core/tests/test_users.py` passes
