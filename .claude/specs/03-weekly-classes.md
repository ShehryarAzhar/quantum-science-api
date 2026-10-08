# Spec: Weekly Class Scheduling

## Overview
A weekly class is a recurring booking: a student picks a subject, a day of the week, a start time and a duration of 40 or 60 minutes, and that class then happens every week. This feature adds the `WeeklyClass` model, the student-facing CRUD API at `/classes/` and its admin page, and enforces the two booking rules that do not depend on trial lessons: a class starts on the full hour, and a weekday + hour timeslot can be held by only one class across all students. It is built third because it needs the Student profile (feature 1) to own a class and the Subject (feature 2) to book it in, and because trial lessons and the schedule both build on it: trial lessons must check weekly classes for clashes, and the schedule totals the weekly cost of a student's classes.

## Depends on
- `.claude/specs/01-users.md` — the `Student` profile that owns a weekly class, and JWT authentication.
- `.claude/specs/02-subjects.md` — the `Subject` a weekly class is booked in.

Both are implemented.

## Requirements
1. A student books a weekly recurring class by choosing a subject, a level, a day of the week, a time and a duration.
2. The duration is 40 or 60 minutes. Any other value is rejected.
3. A student may book several classes of the same subject in one week. There is no limit on classes per subject or per student.
4. Two classes cannot be booked in the same timeslot. A timeslot is a weekday plus an hour. The rule is enforced across all users, not per student: once any student holds a slot, nobody else, and not that student again, can book it.
5. A class starts only on the full hour (4:00, 5:00, ...). Any other time is rejected. Because of this, a 40-minute class occupies its whole weekday + hour slot just like a 60-minute class; duration plays no part in the clash check.
6. A student only ever sees and modifies their own weekly classes. The clash check is the exception: it looks at every student's classes.
7. The booking rules are enforced on the server and backed by database constraints.

Decisions the user made on points `CLAUDE.md` leaves open:

8. **Owner** — a weekly class belongs to a `Student`, not directly to the user. Deleting the student (or their account) deletes their weekly classes and frees the timeslots.
9. **Users without a Student** — a logged-in user with no Student profile (a superuser, a user created in the admin) gets 403 on every `/classes/` route.
10. **Deleting a subject** — a subject that still has weekly classes cannot be deleted (`PROTECT`). An admin must remove or move its classes first.
11. **Day of the week** — the API uses a text code, `monday` to `sunday`, as `day`, and returns the label (`Monday`) as the read-only `day_display`.
12. **Subject in requests and responses** — a request sends `subject` as the subject's id. A response returns `subject` as a nested object with the subject's `id`, `name` and `levels`, from a serializer written for weekly classes only. `levels` is the same list as on `/subjects/`: one object with `code` and `name` per level of the subject (see `.claude/specs/02-subjects.md`). It carries no prices; those come from the public `/subjects/` routes.

The level of a weekly class, added after the feature was first built (a subject can be taught at several levels, so the class has to say which one):

17. **Level** — a weekly class has exactly one level: the level the student wants to study the subject at. It is required.
18. **Level belongs to the subject** — the level must be one of the chosen subject's levels. Otherwise the request is rejected with a validation error on `level`. This holds on every write: `POST`, `PUT` and `PATCH`. A `PATCH` that changes only the subject checks the class's current level against the new subject; a `PATCH` that changes only the level checks it against the class's current subject.
19. **Level in requests and responses** — a request sends `level` as the level's code (`"a_level"`), the codes `/subjects/` returns. A response returns `level` as an object with `code` and `name`, the same shape as an item of a subject's `levels`.
20. **Deleting a level** — a level used by a weekly class cannot be deleted (`PROTECT`).
21. **Removing a level from a subject** (user decision) — in the Django admin, a level cannot be removed from a subject while weekly classes of that subject use it. The subject form shows an error and nothing is saved; the admin moves or deletes those classes first.
22. **Classes booked before levels existed** (user decision) — they get their subject's first level, in `Level` order; a subject with one level gives that level. An admin can change it afterwards.

Choices of this spec that are not product rules:

13. Any full hour of the day, 00:00 to 23:00, is bookable; `CLAUDE.md` sets no teaching hours.
14. `time` is a wall-clock time with no timezone attached and is stored and returned as given.
15. A student can edit a weekly class (`PUT` / `PATCH`): subject, level, day, time and duration can all change, under the same rules as a new booking. A class does not clash with itself.
16. `GET /classes/` is ordered Monday to Sunday, then by time.

## Deferred rules
Deferred to a later spec:
- **Trial lesson clash** (Product requirements 3: reject the booking if an upcoming trial lesson, any student's, occupies that weekday and hour; a past trial lesson no longer blocks) — there is no trial lesson model yet. `.claude/specs/04-trial-lessons.md` must add this check to the weekly class serializer, for both create and update, along with the decision of which timezone a trial lesson's date and time are read in when compared to a weekly class's `day` and `time`.
- **Weekly cost** (Product requirements 5) — pricing each class by its own duration and totalling them belongs to `.claude/specs/05-schedule.md`. This feature stores `duration` and the subject but returns no price.

Picked up from an earlier spec:
- `.claude/specs/02-subjects.md` deferred the foreign key from a weekly class to its subject and its `on_delete`. It is decided here: `PROTECT` (Requirements 10).

## Routes
- `GET /classes/` — list the logged-in student's weekly classes — authenticated student
- `POST /classes/` — book a weekly class — authenticated student
- `GET /classes/{id}/` — retrieve one of the student's own weekly classes — authenticated student
- `PUT /classes/{id}/` — replace one of the student's own weekly classes — authenticated student
- `PATCH /classes/{id}/` — partially update one of the student's own weekly classes — authenticated student
- `DELETE /classes/{id}/` — delete one of the student's own weekly classes; frees the timeslot — authenticated student

On every route: an anonymous request returns 401, an authenticated user without a Student returns 403. On the `{id}` routes, an id that does not exist or belongs to another student returns 404 (never 403, so the existence of another student's class is not revealed).

## Models and database changes
All in `classes/models.py`.

`DayOfWeek` (new, module-level `models.TextChoices`):

| Member | Code | Label |
| --- | --- | --- |
| `MONDAY` | `monday` | Monday |
| `TUESDAY` | `tuesday` | Tuesday |
| `WEDNESDAY` | `wednesday` | Wednesday |
| `THURSDAY` | `thursday` | Thursday |
| `FRIDAY` | `friday` | Friday |
| `SATURDAY` | `saturday` | Saturday |
| `SUNDAY` | `sunday` | Sunday |

Members are declared Monday first, so that `DayOfWeek.values` is in week order (and index `n` matches Python's `date.weekday()`, which the trial lesson spec will need).

`ClassDuration` (new, module-level `models.IntegerChoices`): `FORTY = 40, "40 minutes"` and `SIXTY = 60, "60 minutes"`.

`validate_full_hour` (new, module-level validator function): raises `ValidationError("Classes start on the full hour.")` unless the time's minute, second and microsecond are all zero. Module-level so the trial lesson feature can reuse it.

`WeeklyClass` (new):
- `student` — `ForeignKey(Student, on_delete=models.CASCADE, related_name="weekly_classes")`.
- `subject` — `ForeignKey(Subject, on_delete=models.PROTECT, related_name="weekly_classes")`.
- `level` — `ForeignKey(Level, on_delete=models.PROTECT, related_name="weekly_classes")`, required.
- `day` — `CharField(max_length=9, choices=DayOfWeek.choices)`, required, no default.
- `time` — `TimeField(validators=[validate_full_hour])`, required.
- `duration` — `PositiveSmallIntegerField(choices=ClassDuration.choices)`, required, no default.
- `Day = DayOfWeek` and `Duration = ClassDuration` class attributes.
- `Meta.constraints`:
  - `UniqueConstraint(fields=["day", "time"], name="weekly_class_unique_timeslot", violation_error_message=TIMESLOT_TAKEN_MESSAGE)` — `TIMESLOT_TAKEN_MESSAGE` is the module constant `"This timeslot is already booked."`, shared with the serializer, so the admin form shows the same message. One class per weekday + hour across all students. It does not include `student`.
  - `CheckConstraint(condition=Q(day__in=DayOfWeek.values), name="weekly_class_day_valid")`
  - `CheckConstraint(condition=Q(duration__in=ClassDuration.values), name="weekly_class_duration_valid")`
  - `CheckConstraint(condition=Q(time__in=[datetime.time(hour) for hour in range(24)]), name="weekly_class_time_full_hour")` — the full-hour rule in the database.
- No `Meta.ordering`: text day codes do not sort in week order, so ordering is applied in the viewset's queryset (see Views and URLs).
- `clean()` — when both the subject and the level are set and the level is not one of the subject's levels, raises `ValidationError` on `level`. This is what the admin form for a weekly class runs. The rule itself lives in one module-level function, `level_not_in_subject_error(subject, level)`, which returns the message (`LEVEL_NOT_IN_SUBJECT_MESSAGE`, `"{subject} is not taught at {level}."`) or `None`; `clean()` and the serializer both call it.
- `__str__` returns something readable for the admin, e.g. `"<subject> — Monday 16:00 (<student>)"`.

"The level is one of the subject's levels" has no database constraint: it depends on the rows of the subject–level many-to-many table, which a `CheckConstraint` cannot see. It is enforced in `WeeklyClass.clean()` (admin), in the serializer (API) and in the subject admin form (Requirements 21).

There is no foreign key to the user: the owner is reached through `student.user`.

`Student`, `Subject` and `core.User` are unchanged.

The migration is generated with `uv run python manage.py makemigrations classes` (expected `classes/migrations/0003_weeklyclass.py`, depending on `0002_subject`). It is not written by hand. If MySQL rejects one of the generated check constraints, stop and ask; do not drop the constraint.

The level was added in three migrations, the same pattern as the subject levels:
- `classes/migrations/0007_weeklyclass_level.py` — adds `level` as a nullable column. Generated.
- `classes/migrations/0008_fill_weekly_class_levels.py` — data migration, written by hand. Gives every weekly class without a level its subject's first level in `Level` order (Requirements 22). If a class's subject has no levels it stops with an error naming the classes, instead of guessing. Unapplying it does nothing.
- `classes/migrations/0009_weeklyclass_level_required.py` — makes `level` required. Generated.

## Serializers and validation
`classes.serializers.WeeklyClassSubjectSerializer` (`ModelSerializer` on `Subject`, in the existing `classes/serializers.py`):
- Fields: `id`, `name`, `levels`. `levels` is declared as in `SubjectSerializer`: `LevelSerializer(many=True, read_only=True)`, each item an object with `code` and `name`.
- No prices. It is used only for output, nested in a weekly class; `SubjectSerializer` and the `/subjects/` routes are unchanged.

`classes.serializers.WeeklyClassSerializer` (`ModelSerializer`, in the existing `classes/serializers.py`):
- Fields: `id`, `subject`, `level`, `day`, `day_display`, `time`, `duration`.
- `id` is read-only.
- `level` — on input, a declared `SlugRelatedField(slug_field="code", queryset=Level.objects.all())`, so the request body sends the code (`"level": "a_level"`). On output, `to_representation()` replaces it with `LevelSerializer(instance.level).data` (the serializer `/subjects/` uses for a subject's levels):

  ```json
  "level": {"code": "a_level", "name": "A Level"}
  ```
- `subject` — on input, a `PrimaryKeyRelatedField` over all subjects (the `ModelSerializer` default), so the request body sends the id (`"subject": 3`). On output, `to_representation()` replaces it with `WeeklyClassSubjectSerializer(instance.subject).data`, so every response (list, retrieve, and the body returned by create and update) carries the nested object:

  ```json
  "subject": {"id": 3, "name": "Physics", "levels": [{"code": "o_level", "name": "O Level"}, {"code": "a_level", "name": "A Level"}]}
  ```
- `day` — the stored code. `day_display` is a declared read-only `CharField(source="get_day_display")`.
- `time` — DRF's default `TimeField`; returned as `"HH:MM:SS"` (e.g. `"16:00:00"`), and accepts `"16:00"` or `"16:00:00"` as input.
- `duration` — the integer 40 or 60.
- `student` is not a serializer field. It is never read from the request body and never returned; the viewset sets it from `request.user` on create, and it cannot change on update.

Validation rules:

| Rule | Enforced in | Error |
| --- | --- | --- |
| `subject`, `level`, `day`, `time`, `duration` are all required | serializer (model fields have no default) | 400 `{"<field>": ["This field is required."]}` |
| Subject exists | `PrimaryKeyRelatedField` | 400 under `subject` |
| Level code exists | `SlugRelatedField` | 400 under `level` |
| Level is one of the subject's levels | serializer `validate()`; `WeeklyClass.clean()` for the admin; no database constraint is possible | 400 `{"level": ["Physics is not taught at A Level."]}` |
| Day is one of the seven codes | model `choices` on the serializer field; `weekly_class_day_valid` in the database | 400 under `day` |
| Duration is 40 or 60 | model `choices` on the serializer field; `weekly_class_duration_valid` in the database | 400 under `duration` |
| Time is on the full hour | `validate_full_hour` on the model field, which the serializer field inherits; `weekly_class_time_full_hour` in the database | 400 `{"time": ["Classes start on the full hour."]}` |
| Timeslot (day + time) is free across all students | a `UniqueTogetherValidator` in `Meta.validators`; `weekly_class_unique_timeslot` in the database | 400 `{"non_field_errors": ["This timeslot is already booked."]}` |

The timeslot validator is declared explicitly — `UniqueTogetherValidator(queryset=WeeklyClass.objects.all(), fields=["day", "time"], message="This timeslot is already booked.")` — rather than left to the one DRF derives from the `UniqueConstraint`, to fix the message. Its queryset is every student's classes, never the request user's only. On update it excludes the instance being edited, so a class does not clash with itself, and on `PATCH` it fills a missing `day` or `time` from the instance.

The clash error is the same whoever holds the slot and says nothing about who that is.

Two requests can pass validation at the same moment and collide on the unique constraint. That must come back as the same 400, not a 500: the save runs in `transaction.atomic()` and an `IntegrityError` that names the `weekly_class_unique_timeslot` constraint is turned into the timeslot `ValidationError`. Any other `IntegrityError` (e.g. the subject deleted between validation and insert) is re-raised, not reported as a clash.

The level check is in `validate()`: it takes `subject` and `level` from the request and, for whichever a `PATCH` did not send, from the instance being edited, then checks that the level is among that subject's levels (one `EXISTS` query). So it runs on `POST`, `PUT` and every `PATCH`, and the error is always reported on `level`, including when the request changed only the subject. The message names the subject and the level, e.g. `"Physics is not taught at A Level."`.

The trial lesson clash check is not implemented here (see Deferred rules).

## Views and URLs
`classes.permissions.IsStudent` (new file `classes/permissions.py`, a `BasePermission`): `has_permission` returns whether `request.user` has a Student (`hasattr(request.user, "student")`). Message: `"Only students can use this resource."`, worded neutrally because trial lessons and the schedule reuse the class. Kept separate from `IsAuthenticated` so the later booking features can reuse it.

`classes.views.WeeklyClassViewSet`:
- Base class: `rest_framework.viewsets.ModelViewSet`.
- `permission_classes = [IsAuthenticated, IsStudent]`, in that order, so an anonymous request gets 401 and a user without a Student gets 403.
- `serializer_class = WeeklyClassSerializer`.
- `get_queryset()` returns `WeeklyClass.objects.filter(student=self.request.user.student).select_related("subject", "level").prefetch_related("subject__levels").in_week_order()`. The filter uses the Student that `IsStudent` already loaded, so it costs no extra query and no join. `select_related("subject", "level")` is there because the nested subject and the nested level would otherwise each cost one query per class, and `prefetch_related("subject__levels")` because its levels would too. `in_week_order()` is a method of `WeeklyClassQuerySet` in `classes/models.py` (the model's manager): it orders Monday to Sunday then by `time` with a `Case`/`When` expression over `DayOfWeek.values`, since the codes do not sort in week order; it lives on the queryset so the schedule feature can reuse it. There is no class-level `queryset`. This scoping is what makes another student's class a 404 on retrieve, update and delete.
- `perform_create()` saves with `student=self.request.user.student`.
- No pagination: none is configured, so `GET /classes/` returns a plain JSON array.

`classes/urls.py`: `router.register("classes", WeeklyClassViewSet, basename="weekly-class")` on the existing `SimpleRouter`. The `basename` is required because the viewset has no `queryset` attribute.

`config/urls.py` is unchanged: it already mounts `classes.urls` at the root, giving `/classes/` and `/classes/{id}/`.

## Admin
`classes/admin.py` registers `WeeklyClass` (`WeeklyClassAdmin`) alongside `StudentAdmin` and `SubjectAdmin`:
- `list_display`: student, subject, level, day, time, duration.
- `list_filter`: day, duration, subject, level.
- `search_fields`: the student's username and email, the subject's name.
- `autocomplete_fields`: student and subject (both admins already define `search_fields`). The level is a plain dropdown.
- `list_select_related`: student's user, subject and level.

`SubjectAdmin` uses a `SubjectAdminForm` (`ModelForm`, in `classes/admin.py`) whose `clean_levels()` enforces Requirements 21: when an existing subject is saved without a level that weekly classes of that subject still use, the form fails with one error per such level, e.g. "A Level is used by 2 weekly classes of this subject and cannot be removed." Removing a level no class uses, and creating a subject, are unaffected.

`StudentAdmin` gains a `get_queryset()` that adds `select_related("user")`: the student autocomplete on the weekly class form renders each Student through its user, and `list_select_related` does not reach the autocomplete endpoint.

The admin form runs the model's validation, so the full-hour rule, the day and duration choices, the unique timeslot and a level that is not one of the subject's all show as form errors there.

Admin-only: viewing, creating, editing and deleting any student's weekly classes, and moving a class to another student. Deleting a subject that still has weekly classes, or a level that weekly classes use, is blocked in the admin by `PROTECT`.

## Files to change
- `classes/models.py` — add `DayOfWeek`, `ClassDuration`, `validate_full_hour`, `WeeklyClass`
- `classes/serializers.py` — add `WeeklyClassSubjectSerializer` and `WeeklyClassSerializer`
- `classes/views.py` — add `WeeklyClassViewSet`
- `classes/urls.py` — register the viewset
- `classes/admin.py` — register `WeeklyClass`
- `CLAUDE.md`:
  - "Implemented vs Stub Routes" > Weekly classes: all six routes go from Stub to Implemented
  - Product requirements: the "Only requirements 1 and 2 are built so far" line, and requirement 3 gains the decisions above (owned by a Student, 403 without one, day codes and `day_display`, subject sent as an id and returned nested, subject protected from deletion, editable)
  - Architecture: `classes/` no longer has "only `Student` and `Subject`"; mention `WeeklyClass` and `classes/permissions.py`
- `.claude/agents/` and `.claude/commands/` — every file that carries its own copy of the weekly class rules gets the same decisions, in the same change
- For the level of a weekly class: `classes/models.py`, `classes/serializers.py`, `classes/views.py`, `classes/admin.py`, Product requirements 3 in `CLAUDE.md`, the Admin section of `.claude/specs/02-subjects.md`, and `.claude/agents/quantum-test-writer.md` and `.claude/agents/quantum-security-reviewer.md`

## Files to create
- `classes/permissions.py`
- `classes/migrations/0003_weeklyclass.py` (generated by `makemigrations`)
- `classes/migrations/0007_weeklyclass_level.py`, `0008_fill_weekly_class_levels.py` and `0009_weeklyclass_level_required.py` (see Models and database changes)

`classes/tests/test_weekly_classes.py` is created later by `/test-feature weekly-classes`, not during implementation.

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
- The owner is never taken from the request body: `student` is not a serializer field and is set from `request.user.student` in `perform_create()`
- Never assume `request.user.student` exists outside code guarded by `IsStudent`
- Scope with `get_queryset()`, not with an object-level permission, so another student's class is a 404
- The unique timeslot constraint is on `day` + `time` only; do not add `student` or `duration` to it
- The clash check's queryset is all weekly classes; do not reuse the user-scoped queryset for it
- The full-hour rule lives in one validator on the model field plus the check constraint; do not duplicate it in a serializer `validate_time`
- Day and duration are `TextChoices` / `IntegerChoices` on the model, each backed by a `CheckConstraint`; `day_display` comes from `get_day_display`
- A clash that slips past validation returns 400, never 500
- Do not implement the trial lesson clash check and do not create a trial lesson model; that is spec 04
- The nested subject comes from `WeeklyClassSubjectSerializer`, never from `SubjectSerializer`; do not change `SubjectSerializer` or the `/subjects/` response
- The request body takes `subject` as an id; do not accept a nested subject object on input and do not add a separate `subject_id` field
- The request body takes `level` as a level code; do not accept a level id or a nested level object on input. The response's `level` comes from `LevelSerializer`
- The level check runs on `POST`, `PUT` and `PATCH`, uses the stored subject or level for whichever a `PATCH` omits, and always reports its error on `level`
- The level-and-subject rule is the shared `level_not_in_subject_error()` in `classes/models.py`; `WeeklyClass.clean()` and the serializer call it, and neither repeats the query or the message
- Any queryset that serializes weekly classes uses `select_related("subject", "level")` and prefetches `subject__levels`
- `level` is `PROTECT`, never `CASCADE` or `SET_NULL`, and never nullable in the final model
- The data migration that fills old classes never invents a level for a subject that has none
- Do not add price or cost fields to the weekly class response, including inside the nested subject; that is spec 05
- Do not add fields the spec does not list (no start date, no end date, no status, no notes)
- Do not restrict bookable hours beyond the full-hour rule
- Generate the migration with `makemigrations`; do not write it by hand
- Do not write tests during implementation

## Tests
Covered by `classes/tests/test_weekly_classes.py`, written and run with `/test-feature weekly-classes`, not as part of implementation. A test student is `baker.make(get_user_model())` plus `baker.make(Student, user=user)`. It must cover:
- Access: every route returns 401 for an anonymous request and 403 for an authenticated user without a Student
- Subject shape: in the responses of create, list, retrieve and update, `subject` is an object with exactly `id`, `name` and `levels`, matching the booked subject, with no price fields; `levels` is a list with one `{"code", "name"}` object per level of the subject, and a subject with two levels returns both; a request sends `subject` as an id, and a nested object sent as `subject` returns 400
- Level shape: in the responses of create, list, retrieve and update, `level` is an object with exactly `code` and `name`, matching the booked level; a request sends `level` as a code
- Level belongs to the subject, on create and `PUT`: a level that is one of the subject's is accepted, for a subject with one level and for a subject with several; a level the subject does not have returns 400 with the error under `level` and creates or changes nothing
- Level on `PATCH`: changing only the level to another of the current subject's levels returns 200; changing only the level to one the current subject lacks returns 400 under `level`; changing only the subject to one that has the current level returns 200; changing only the subject to one that lacks the current level returns 400 under `level`; changing subject and level together to a matching pair returns 200; a `PATCH` of another field (e.g. `duration`) still returns 200
- `POST /classes/`: 201 with exactly `id`, `subject`, `level`, `day`, `day_display`, `time`, `duration`; the class is stored against the logged-in student with the chosen level; a `student` or `user` value in the body is ignored; both durations accepted; each of the seven day codes accepted with the matching `day_display`
- Required fields: each of `subject`, `level`, `day`, `time`, `duration` missing returns 400
- Invalid values: unknown subject id, unknown level code, unknown day code, a duration other than 40 or 60 each return 400 and create nothing
- Full hour: `16:00` accepted; `16:30`, `16:00:01` and `16:15` return 400 under `time`; midnight (`00:00`) and `23:00` accepted
- Clash: the same day and time as the student's own class returns 400; the same day and time as another student's class returns 400; a 40-minute class blocks the slot for a 60-minute one and the reverse; the same time on another day and another hour on the same day are both accepted
- Same subject: a student can book the same subject several times in one week in different slots
- `GET /classes/`: only the logged-in student's classes; an empty list when there are none; ordered Monday to Sunday then by time; a plain list (not paginated)
- Query count: `GET /classes/` runs the same number of queries for a student with one class as for a student with several classes in different subjects (`django_assert_num_queries` or `CaptureQueriesContext`); no query per class
- `GET /classes/{id}/`: 200 for the student's own class; 404 for another student's class and for an unknown id
- `PUT` / `PATCH /classes/{id}/`: subject, day, time and duration can change; a non-full-hour time returns 400; moving into a slot held by anyone else returns 400; saving a class without changing its slot, or changing only its duration or subject, succeeds; another student's class returns 404 and is unchanged
- `DELETE /classes/{id}/`: 204 and the class is gone; the slot can then be booked by another student; another student's class returns 404 and is kept
- Cascades: deleting a student's account deletes their weekly classes; deleting a subject that has a weekly class raises `ProtectedError`; deleting a level that a weekly class uses raises `ProtectedError`
- Model rules: saved without validation, a duplicate day + time, an unknown day, a duration other than 40 or 60 and a non-full-hour time each raise `IntegrityError`; `full_clean()` rejects a non-full-hour time, and rejects a level that is not one of the subject's with the error under `level`
- Subject admin form (`classes.admin.SubjectAdminForm`, a form rule, so tested on the form and not through the API): saving a subject without a level its weekly classes use is invalid with an error on `levels`; removing a level no class uses is valid; a level used only by another subject's classes does not block

Every weekly class a test builds needs a level that is one of its subject's levels; fetch the seeded levels with `Level.objects.get(code=...)` and give test subjects their levels explicitly.

Not covered here: the trial lesson clash (spec 04) and the weekly cost (spec 05).

## Definition of done
- [ ] `uv run python manage.py makemigrations --check` reports no missing migrations
- [ ] Each route returns the expected status for an anonymous request (all six `/classes/` routes return 401)
- [ ] The feature's routes are marked Implemented in `CLAUDE.md`
- [ ] `uv run python manage.py migrate` applies `classes.0003` cleanly on MySQL, including the three check constraints and the unique constraint
- [ ] `uv run python manage.py migrate` applies `classes.0007` to `0009`, and every weekly class that existed before has a level that is one of its subject's
- [ ] A registered student can `POST /classes/` with `subject`, `level`, `day`, `time` and `duration` and gets 201 with `id`, `subject`, `level`, `day`, `day_display`, `time` and `duration`, where `subject` was sent as an id and comes back as `{"id", "name", "levels"}` with no prices, and `level` was sent as a code and comes back as `{"code", "name"}`
- [ ] `POST /classes/` with a level the subject does not have returns 400 under `level`
- [ ] `PATCH /classes/{id}/` changing only `subject` to one without the class's level returns 400 under `level`, and so does changing only `level` to one the subject lacks
- [ ] In the Django admin, removing a level from a subject whose weekly classes use it is refused with an error, and deleting a level that weekly classes use is refused
- [ ] In the Django admin, the Weekly class list shows the level and can be filtered by it, and its form rejects a level the subject does not have
- [ ] `POST /classes/` with `time` `16:30` returns 400 under `time`
- [ ] `POST /classes/` with a duration of 45 returns 400 under `duration`
- [ ] A second student booking the same `day` and `time` gets 400 with `"This timeslot is already booked."`, and so does the first student booking it again
- [ ] A student can book the same subject twice in different slots
- [ ] `GET /classes/` returns only the logged-in student's classes, Monday first
- [ ] `GET`, `PATCH` and `DELETE /classes/{id}/` on another student's class return 404
- [ ] `PATCH /classes/{id}/` changing only `duration` returns 200; changing `day` / `time` to a taken slot returns 400
- [ ] `DELETE /classes/{id}/` returns 204 and the slot becomes bookable again
- [ ] A superuser's token gets 403 on `GET /classes/`
- [ ] In the Django admin, Weekly class has a list page showing student, subject, day, time and duration, and its form rejects a non-full-hour time and a taken timeslot
- [ ] In the Django admin, deleting a subject that has a weekly class is refused
- [ ] `uv run pytest classes/tests/test_weekly_classes.py` passes (after `/test-feature weekly-classes`)
