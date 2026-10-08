# Spec: Trial Lessons

## Overview
A trial lesson is a single free 60-minute lesson a student books before committing to weekly classes: they pick a subject, the level they want to study it at, and one specific date and time. This feature adds the `TrialLesson` model, the student-facing CRUD API at `/trial-lessons/` and its admin page. It enforces one trial lesson per student, the full-hour rule, the lock that closes a lesson once it is completed or its time has passed, and the timeslot rules in both directions: a trial lesson cannot be booked where a weekly class or another trial lesson already is, and, picking up the rule spec 03 deferred, a weekly class cannot be booked where an upcoming trial lesson is. It is built fourth because it needs the Student (feature 1), the Subject and its levels (feature 2) and the weekly classes it must not clash with (feature 3), and because the schedule (feature 5) returns it alongside the student's weekly classes.

## Depends on
- `.claude/specs/01-users.md` — the `Student` profile that owns a trial lesson, and JWT authentication.
- `.claude/specs/02-subjects.md` — the `Subject` a trial lesson is booked in and the `Level` rows it is booked at.
- `.claude/specs/03-weekly-classes.md` — the `WeeklyClass` model the clash checks read, plus `DayOfWeek`, `validate_full_hour`, `level_not_in_subject_error`, `IsStudent`, `LevelSerializer` and `WeeklyClassSubjectSerializer`, all reused here.

All three are implemented.

## Requirements
1. A student books a trial lesson by choosing a subject, a level and a specific date and time.
2. A trial lesson lasts 60 minutes and is free. Neither is stored or returned: there is no duration field and no price field.
3. A trial lesson starts only on the full hour, like a weekly class. Any other time is rejected.
4. Each student can book only one trial lesson. A second booking is rejected on the server, and the rule is backed by a database uniqueness constraint.
5. A trial lesson can be marked completed, but only in the Django admin. The completed flag is read-only in the API: a value sent for it is ignored.
6. While the trial lesson is not completed and its date and time have not passed, the student can edit it or delete it. Deleting it frees the student to book another.
7. Once it is marked completed or its date and time have passed, it is locked: the student cannot edit or delete it through the API. Because it still counts as their one trial lesson, they cannot create another. It stays readable.
8. A booking is rejected if any student's weekly class occupies that time: the same weekday and hour as the chosen date and time. This includes the booking student's own weekly classes.
9. A booking is rejected if any student's trial lesson is already booked at that date and time.
10. A student only ever sees and modifies their own trial lesson. The clash checks are the exception: they look at every student's bookings.
11. The booking rules are enforced on the server and backed by database constraints where one is possible.

The level of a trial lesson (user decision: a trial lesson shows a level just like a weekly class; `CLAUDE.md` does not list it yet, see Files to change):

12. **Level** — a trial lesson has exactly one level: the level the student wants to study the subject at. It is required.
13. **Level belongs to the subject** — the level must be one of the chosen subject's levels. Otherwise the request is rejected with a validation error on `level`. This holds on every write: `POST`, `PUT` and `PATCH`. A `PATCH` that changes only the subject checks the lesson's current level against the new subject; a `PATCH` that changes only the level checks it against the lesson's current subject.
14. **Level in requests and responses** — a request sends `level` as the level's code (`"a_level"`). A response returns `level` as an object with `code` and `name`, the same shape as on a weekly class.
15. **Deleting a level** — a level used by a trial lesson cannot be deleted (`PROTECT`).
16. **Removing a level from a subject** — in the Django admin, a level cannot be removed from a subject while trial lessons of that subject use it, the same rule weekly classes already have.

Decisions the user made on points `CLAUDE.md` leaves open:

17. **Timezone** — every date and time in the API is UTC. The server stores, compares and returns UTC; the frontend converts to and from the student's local time. This also settles the question spec 03 deferred: a weekly class's `day` and `time` are UTC, and a trial lesson's weekday and hour are taken from its UTC date and time when the two are compared.
18. **One field for date and time** — a trial lesson's date and time are one field, `starts_at`, an ISO 8601 date-time (`"2026-10-13T02:00:00Z"`). They are not two separate fields, because a date and a time only convert between timezones correctly together (22:00 Monday in New York is 02:00 Tuesday UTC).
19. **Locked reply** — editing or deleting a locked trial lesson returns 403 with `{"detail": "This trial lesson can no longer be changed."}`.
20. **Booking in the past** — a booking whose `starts_at` has already passed is rejected with 400 on `starts_at`. The same applies when an edit moves a lesson into the past.

Choices of this spec that follow the weekly class feature:

21. **Owner** — a trial lesson belongs to a `Student`, not directly to the user, through a one-to-one relation. `CLAUDE.md` asks for a uniqueness constraint "on the user"; a Student is itself one-to-one with the user, so one trial lesson per Student is one per user. Deleting the student (or their account) deletes their trial lesson.
22. **Users without a Student** — a logged-in user with no Student profile gets 403 on every `/trial-lessons/` route.
23. **Deleting a subject** — a subject that still has a trial lesson cannot be deleted (`PROTECT`). This is the decision `.claude/specs/02-subjects.md` deferred to this spec.
24. **Subject in requests and responses** — a request sends `subject` as the subject's id. A response returns it as a nested object with `id`, `name` and `levels`, and no prices, exactly as on a weekly class.

Choices of this spec that are not product rules:

25. **"Passed"** — a trial lesson's date and time have passed once `starts_at` is at or before the current moment. It locks when it starts, not when its 60 minutes end. The same test decides "upcoming" for the weekly class rule (Deferred rules): a trial lesson blocks a weekly slot only while `starts_at` is in the future.
26. A completed trial lesson whose `starts_at` is still in the future is locked for its student but still occupies its time: it blocks other trial lessons and the weekly slot until it has passed.
27. A second booking returns 400 with `{"non_field_errors": ["You have already booked a trial lesson."]}`, whether the existing lesson is open or locked.
28. Any full hour of the day is bookable; `CLAUDE.md` sets no teaching hours.
29. `GET /trial-lessons/` returns a plain list holding the student's trial lesson, or an empty list. It is a list, not a single object, because the route is a standard `ModelViewSet` route.
30. The lock is tested before the request body is validated: a locked lesson answers 403 even when the body is invalid.

## Deferred rules
Deferred to a later spec:
- **My schedule** (Product requirements 5) — returning the trial lesson with the student's weekly classes, and counting it as free in the weekly cost, belongs to `.claude/specs/05-schedule.md`.

Picked up from earlier specs:
- **Trial lesson clash on weekly classes** (`.claude/specs/03-weekly-classes.md`, Deferred rules; Product requirements 3) — a weekly class booking is rejected if an upcoming trial lesson, any student's, occupies that weekday and hour; a trial lesson that has passed no longer blocks the slot. Implemented here in the weekly class serializer, for create, `PUT` and `PATCH`, and in `WeeklyClass.clean()` for the admin.
- **Timezone for comparing a trial lesson with a weekly class** (`.claude/specs/03-weekly-classes.md`, Deferred rules) — decided: UTC (Requirements 17).
- **`on_delete` from a trial lesson to its subject** (`.claude/specs/02-subjects.md`, Deferred rules) — decided: `PROTECT` (Requirements 23).

## Routes
- `GET /trial-lessons/` — list the logged-in student's trial lesson (zero or one item) — authenticated student
- `POST /trial-lessons/` — book the trial lesson — authenticated student
- `GET /trial-lessons/{id}/` — retrieve the student's own trial lesson, open or locked — authenticated student
- `PUT /trial-lessons/{id}/` — replace the student's own trial lesson; 403 when locked — authenticated student
- `PATCH /trial-lessons/{id}/` — partially update the student's own trial lesson; 403 when locked — authenticated student
- `DELETE /trial-lessons/{id}/` — delete the student's own trial lesson; 403 when locked; frees the time and lets the student book again — authenticated student

On every route: an anonymous request returns 401, an authenticated user without a Student returns 403. On the `{id}` routes, an id that does not exist or belongs to another student returns 404 (never 403, so the existence of another student's trial lesson is not revealed); this holds whether or not that lesson is locked.

## Models and database changes
All in `classes/models.py`.

New module constants: `TRIAL_LESSON_TIMESLOT_CONSTRAINT_NAME = "trial_lesson_unique_starts_at"`, `TRIAL_LESSON_ALREADY_BOOKED_MESSAGE = "You have already booked a trial lesson."`, `TRIAL_LESSON_LOCKED_MESSAGE = "This trial lesson can no longer be changed."` and `STARTS_AT_IN_PAST_MESSAGE = "A trial lesson cannot be booked in the past."`. `TIMESLOT_TAKEN_MESSAGE` (`"This timeslot is already booked."`) is reused for every clash.

`validate_full_hour` (changed): it must also accept a `datetime`. For an aware `datetime` it converts the value to UTC before testing minute, second and microsecond, so the full hour is always judged in UTC. Its behaviour for a `time` is unchanged.

`TrialLesson` (new):
- `student` — `OneToOneField(Student, on_delete=models.CASCADE, related_name="trial_lesson")`. The one-to-one is the database uniqueness constraint behind "one trial lesson per student".
- `subject` — `ForeignKey(Subject, on_delete=models.PROTECT, related_name="trial_lessons")`.
- `level` — `ForeignKey(Level, on_delete=models.PROTECT, related_name="trial_lessons")`, required.
- `starts_at` — `DateTimeField(validators=[validate_full_hour])`, required. Stored in UTC (`USE_TZ = True`, `TIME_ZONE = "UTC"`).
- `completed` — `BooleanField(default=False)`.
- `Meta.constraints`:
  - `UniqueConstraint(fields=["starts_at"], name="trial_lesson_unique_starts_at", violation_error_message=TIMESLOT_TAKEN_MESSAGE)` — one trial lesson per date and time across all students. It does not include `student`.
  - `CheckConstraint(condition=Q(starts_at__minute=0, starts_at__second=0), name="trial_lesson_starts_at_full_hour")` — the full-hour rule in the database. Microseconds are covered by the validator only; there is no lookup for them.
- `Meta.ordering = ["starts_at"]`.
- `is_locked` (property) — `True` when `completed` is set or `starts_at` is at or before `timezone.now()`.
- `clean()`:
  - when subject and level are both set, calls `level_not_in_subject_error(subject, level)` and raises on `level`, as `WeeklyClass.clean()` does;
  - when `starts_at` is in the future and a weekly class holds its weekday and hour, raises `TIMESLOT_TAKEN_MESSAGE` on `starts_at`. It does not run for a lesson that has passed, so an admin can still open and save an old lesson (e.g. to mark it completed) after a weekly class has taken the freed slot.
  - It does not reject a `starts_at` in the past: that rule is for student bookings only (see Serializers and validation), and an admin must be able to save a past lesson.
- `__str__` returns something readable for the admin, e.g. `"<subject> trial — 2026-10-13 02:00 (<student>)"`.

The two cross-model clash rules cannot be database constraints, because each compares rows of two tables. Each lives in one place in `classes/rules.py`, called by both the model's `clean()` (admin) and the serializer (API), in the way `level_not_in_subject_error` is:
- **A weekly class at a trial lesson's time** — the weekday code is `DayOfWeek.values[starts_at.weekday()]` and the hour is `starts_at.time()`, both from the UTC value; the check is whether any `WeeklyClass` has that `day` and `time`.
- **An upcoming trial lesson at a weekly class's slot** — whether any `TrialLesson` with `starts_at` in the future falls on that `day` and `time`, compared in UTC.

`WeeklyClass` (changed): `clean()` also raises `TIMESLOT_TAKEN_MESSAGE` (as a non-field error) when an upcoming trial lesson occupies the class's `day` and `time`. No field or constraint of `WeeklyClass` changes.

`Student`, `Level`, `Subject` and `core.User` are unchanged.

The migration is generated with `uv run python manage.py makemigrations classes` (expected `classes/migrations/0010_triallesson.py`, depending on `0009_weeklyclass_level_required`). It is not written by hand. If MySQL or Django rejects the generated full-hour check constraint, stop and ask; do not drop the constraint.

## Serializers and validation
`classes.serializers.TrialLessonSerializer` (`ModelSerializer`, in the existing `classes/serializers.py`):
- Fields: `id`, `subject`, `level`, `starts_at`, `completed`.
- `id` and `completed` are read-only. A `completed` value in a request body is ignored.
- `subject` — on input, a `PrimaryKeyRelatedField` over all subjects (the `ModelSerializer` default): the request sends the id. On output, `to_representation()` replaces it with `WeeklyClassSubjectSerializer(instance.subject).data`: `{"id", "name", "levels"}`, no prices.
- `level` — on input, a declared `SlugRelatedField(slug_field="code", queryset=Level.objects.all())`: the request sends the code. On output, `to_representation()` replaces it with `LevelSerializer(instance.level).data`: `{"code", "name"}`.
- `starts_at` — DRF's `DateTimeField`. Returned in UTC as `"2026-10-13T02:00:00Z"`. An input with an offset is converted to UTC; an input without an offset is read as UTC. The full-hour rule is applied to the UTC value.
- `student` is not a serializer field. It is never read from the request body and never returned; the viewset sets it from `request.user` on create, and it cannot change on update.
- There is no duration and no price field.

A response looks like:

```json
{
  "id": 1,
  "subject": {"id": 3, "name": "Physics", "levels": [{"code": "o_level", "name": "O Level"}, {"code": "a_level", "name": "A Level"}]},
  "level": {"code": "a_level", "name": "A Level"},
  "starts_at": "2026-10-13T02:00:00Z",
  "completed": false
}
```

Validation rules:

| Rule | Enforced in | Error |
| --- | --- | --- |
| `subject`, `level`, `starts_at` are all required | serializer (model fields have no default) | 400 `{"<field>": ["This field is required."]}` |
| Subject exists | `PrimaryKeyRelatedField` | 400 under `subject` |
| Level code exists | `SlugRelatedField` | 400 under `level` |
| Level is one of the subject's levels | serializer `validate()` through `level_not_in_subject_error`; `TrialLesson.clean()` for the admin; no database constraint is possible | 400 `{"level": ["Physics is not taught at A Level."]}` |
| `starts_at` is on the full hour | `validate_full_hour` on the model field, which the serializer field inherits; `trial_lesson_starts_at_full_hour` in the database | 400 `{"starts_at": ["Classes start on the full hour."]}` |
| `starts_at` is in the future | serializer `validate_starts_at`; not in the model (see Models and database changes) | 400 `{"starts_at": ["A trial lesson cannot be booked in the past."]}` |
| No other trial lesson at that date and time, any student's | a `UniqueValidator` on `starts_at` with `TIMESLOT_TAKEN_MESSAGE`; `trial_lesson_unique_starts_at` in the database | 400 `{"starts_at": ["This timeslot is already booked."]}` |
| No weekly class on that weekday and hour, any student's | serializer `validate_starts_at`; `TrialLesson.clean()` for the admin; no database constraint is possible | 400 `{"starts_at": ["This timeslot is already booked."]}` |
| The student has no trial lesson yet (create only) | serializer `validate()`; the one-to-one on `student` in the database | 400 `{"non_field_errors": ["You have already booked a trial lesson."]}` |
| The lesson is not locked (update and delete) | object-level permission on the viewset (see Views and URLs) | 403 `{"detail": "This trial lesson can no longer be changed."}` |

All timeslot errors on a trial lesson are reported on `starts_at`, the one field that decides the slot. They are the same whoever holds the slot and say nothing about who that is.

On update the uniqueness check excludes the lesson being edited, so a lesson does not clash with itself, and a `PATCH` that does not send `starts_at` does not re-run the future and weekly class checks on it. The level check runs on `POST`, `PUT` and every `PATCH`, taking whichever of subject and level the request omitted from the instance, and always reports on `level`.

Two requests can pass validation at the same moment and collide on a unique constraint. That must come back as the matching 400, not a 500: the save runs in `transaction.atomic()`; an `IntegrityError` that names `trial_lesson_unique_starts_at` becomes the timeslot error on `starts_at`, one that names `trial_lesson_starts_at_full_hour` becomes the full-hour error on `starts_at` (a backstop behind the validator), one on the student's unique key becomes the already-booked error, and any other `IntegrityError` is re-raised.

The `level` field, the nested `subject` and `level` in `to_representation()` and the level check are shared with `WeeklyClassSerializer` through `classes.serializers.SubjectLevelMixin`, which both serializers inherit (added after code review); neither serializer repeats them.

`classes.serializers.WeeklyClassSerializer` (changed, picking up the deferred rule): `validate()` also rejects the booking when an upcoming trial lesson, any student's, occupies the class's `day` and `time`, with 400 `{"non_field_errors": ["This timeslot is already booked."]}`, the same error as its existing clash. It runs on `POST`, `PUT` and `PATCH`; for whichever of `day` and `time` a `PATCH` omits it uses the stored value. A trial lesson that has passed does not block. Nothing else about the weekly class serializer or its response changes.

## Views and URLs
`classes.permissions.IsTrialLessonOpen` (new, in the existing `classes/permissions.py`, a `BasePermission`): `has_object_permission` returns `True` for safe methods and otherwise `not obj.is_locked`. Message: `TRIAL_LESSON_LOCKED_MESSAGE`. Because DRF checks object permissions inside `get_object()`, a locked lesson answers 403 before the body is validated, and another student's lesson is still a 404 because the scoped queryset misses it first.

`classes.views.TrialLessonViewSet`:
- Base class: `rest_framework.viewsets.ModelViewSet`.
- `permission_classes = [IsAuthenticated, IsStudent, IsTrialLessonOpen]`, in that order, so an anonymous request gets 401 and a user without a Student gets 403.
- `serializer_class = TrialLessonSerializer`.
- `get_queryset()` returns `TrialLesson.objects.filter(student=self.request.user.student).select_related("subject", "level").prefetch_related("subject__levels")`. There is no class-level `queryset`.
- `perform_create()` saves with `student=self.request.user.student`. The serializer reads the same student from its context for the already-booked check.
- No pagination: `GET /trial-lessons/` returns a plain JSON array.

`classes/urls.py`: `router.register("trial-lessons", TrialLessonViewSet, basename="trial-lesson")` on the existing `SimpleRouter`.

`config/urls.py` is unchanged: it already mounts `classes.urls` at the root.

## Admin
`classes/admin.py` registers `TrialLesson` (`TrialLessonAdmin`):
- `list_display`: student, subject, level, starts_at, completed. `starts_at` is shown and entered in Asia/Karachi ("Starts at (PKT)") and stored in UTC; Django converts it because the admin runs in that timezone (added after this feature was built; see Architecture > Admin timezone in `CLAUDE.md`).
- `list_filter`: completed, starts_at, subject, level.
- No `date_hierarchy`: outside UTC it needs MySQL's timezone tables, which are not loaded. The `starts_at` date filter replaces it.
- `search_fields`: the student's username and email, the subject's name.
- `autocomplete_fields`: student and subject. The level is a plain dropdown.
- `list_select_related`: student's user, subject and level.

`SubjectAdminForm.clean_levels()` (changed) also counts trial lessons: a level cannot be removed from a subject while weekly classes or trial lessons of that subject use it, with one error per level and kind of booking, e.g. "A Level is used by 1 trial lesson of this subject and cannot be removed."

The admin form runs the model's validation, so a non-full-hour time, a taken date and time, a second trial lesson for a student, a level the subject does not have and a clash with a weekly class all show as form errors. The weekly class admin form now also refuses a slot held by an upcoming trial lesson.

Admin-only: marking a trial lesson completed (and un-marking it), viewing and editing any student's trial lesson, editing or deleting a locked one, saving one with a past `starts_at`, and moving one to another student. Deleting a subject or a level that a trial lesson uses is blocked in the admin by `PROTECT`.

## Files to change
- `classes/models.py` — add `TrialLesson`, its constants and the two clash helpers; extend `validate_full_hour` to datetimes; add the trial lesson check to `WeeklyClass.clean()`
- `classes/serializers.py` — add `TrialLessonSerializer`; add the trial lesson check to `WeeklyClassSerializer.validate()`
- `classes/permissions.py` — add `IsTrialLessonOpen`
- `classes/views.py` — add `TrialLessonViewSet`
- `classes/urls.py` — register the viewset
- `classes/admin.py` — register `TrialLesson`; extend `SubjectAdminForm.clean_levels()`
- `CLAUDE.md`:
  - "Implemented vs Stub Routes" > Trial lessons: all six routes go from Stub to Implemented
  - Product requirements: the "Only requirements 1, 2 and 3 are built so far" line; requirement 4 gains the level rules (Requirements 12 to 16) and the decisions above (UTC, the single `starts_at` field, 403 when locked, no booking in the past, owned by a Student with 403 without one, subject and level protected from deletion, subject and level shapes); requirement 3 drops "Not built yet" from the trial lesson rule, says `day` and `time` are UTC, and extends the two level-deletion rules to trial lessons
  - API conventions: state that every date and time in the API is UTC
  - Architecture: `classes/` lists `TrialLesson` and `IsTrialLessonOpen`
- `.claude/agents/quantum-test-writer.md`, `.claude/agents/quantum-security-reviewer.md` and `.claude/agents/quantum-test-runner.md` — their copies of the trial lesson and weekly class rules gain the level, the `starts_at` field and the 403 lock, in the same change. Any other command or agent file that turns out to carry these rules gets the same update
- `.claude/specs/03-weekly-classes.md` — its Deferred rules entry for the trial lesson clash is marked as picked up by this spec, and its timezone note (Requirements 14) says UTC
- `.claude/specs/02-subjects.md` — its Admin section mentions that `SubjectAdminForm` and `PROTECT` now cover trial lessons too

## Files to create
- `classes/migrations/0010_triallesson.py` (generated by `makemigrations`)

`classes/tests/test_trial_lessons.py` is created later by `/test-feature trial-lessons`, not during implementation.

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
- Scope with `get_queryset()` so another student's trial lesson is a 404; the object-level permission is only for the lock
- `completed` is read-only in the serializer; nothing in the API can set or clear it
- The lock is `TrialLesson.is_locked`, defined once; the permission and anything else that needs it ask the model
- A locked lesson returns 403 on `PUT`, `PATCH` and `DELETE`, and stays readable with `GET`
- A locked lesson still counts as the student's one trial lesson; do not exclude locked lessons from the already-booked check
- One trial lesson per student is a `OneToOneField`, never only a serializer check
- Date and time are the single `starts_at` `DateTimeField`; do not add separate date, time, weekday or timezone fields
- Compare times with `django.utils.timezone.now()`, never a naive `datetime.now()`; take the weekday and hour of a trial lesson from its UTC value
- Do not change `TIME_ZONE` or `USE_TZ`
- The past-booking rule is in the serializer only; `TrialLesson.clean()` must not reject a past `starts_at`
- The clash checks' querysets are all weekly classes and all trial lessons; do not reuse a user-scoped queryset for them
- Each cross-model clash rule is one function in `classes/rules.py`, called by the model's `clean()` and by the serializer; neither repeats the query or the message
- Only an upcoming trial lesson blocks a weekly class slot; a passed one does not, whether or not it is completed
- The full-hour rule stays the one `validate_full_hour` validator plus a check constraint; do not write a second validator or a serializer `validate` for it
- The level-and-subject rule is the existing `level_not_in_subject_error()`; do not rewrite it for trial lessons
- The nested subject comes from `WeeklyClassSubjectSerializer` and the nested level from `LevelSerializer`; do not change `SubjectSerializer` or the `/subjects/` response
- The request body takes `subject` as an id and `level` as a level code; do not accept nested objects on input
- `subject` and `level` are `PROTECT`, never `CASCADE` or `SET_NULL`
- A clash or a second booking that slips past validation returns 400, never 500
- Do not add fields the spec does not list (no duration, no price, no notes, no status, no `is_locked` in the response)
- Do not change the weekly class response or its existing rules; only add the trial lesson check
- Do not build the schedule route; that is spec 05
- Generate the migration with `makemigrations`; do not write it by hand
- Do not write tests during implementation

## Tests
Covered by `classes/tests/test_trial_lessons.py`, written and run with `/test-feature trial-lessons`, not as part of implementation. A test student is `baker.make(get_user_model())` plus `baker.make(Student, user=user)`. Times are built relative to `timezone.now()`, rounded to a full hour, never hard-coded dates; a past or completed lesson is created directly with `baker.make`, since the API refuses to book one. It must cover:
- Access: every route returns 401 for an anonymous request and 403 for an authenticated user without a Student
- `POST /trial-lessons/`: 201 with exactly `id`, `subject`, `level`, `starts_at`, `completed`; `completed` is `false`; the lesson is stored against the logged-in student; a `student` or `user` value in the body is ignored; `completed: true` in the body is ignored
- Shapes: `subject` is an object with exactly `id`, `name` and `levels` and no prices; `level` is an object with exactly `code` and `name`; `starts_at` comes back in UTC; an input with a non-UTC offset is stored as the same moment in UTC
- Required fields: each of `subject`, `level`, `starts_at` missing returns 400
- Invalid values: an unknown subject id, an unknown level code and a malformed date-time each return 400 and create nothing
- Level belongs to the subject: accepted when it is one of the subject's; 400 under `level` when it is not, on create and `PUT`; on `PATCH`, changing only the level or only the subject is checked against the stored other one
- Full hour: a full-hour `starts_at` is accepted; `:30`, `:15` and a non-zero second each return 400 under `starts_at`
- Past: a `starts_at` in the past returns 400 under `starts_at` and creates nothing
- One per student: a second `POST` returns 400 under `non_field_errors` while the first lesson is open, when it is completed and when it has passed; another student can still book their own
- Trial lesson clash: the same `starts_at` as another student's trial lesson returns 400 under `starts_at`; a different hour or a different date is accepted
- Weekly class clash: a `starts_at` on the weekday and hour of another student's weekly class returns 400 under `starts_at`; so does the student's own weekly class; a 40-minute weekly class blocks as well; a weekly class on another weekday or another hour does not block
- `GET /trial-lessons/`: only the logged-in student's lesson; an empty list when there is none; a plain list
- `GET /trial-lessons/{id}/`: 200 for the student's own lesson, including a completed one and a passed one; 404 for another student's lesson and for an unknown id
- `PUT` / `PATCH /trial-lessons/{id}/` on an open lesson: subject, level and `starts_at` can change; saving without changing `starts_at` succeeds (no clash with itself); a non-full-hour, past or taken `starts_at` returns 400; `completed` in the body does not change it; another student's lesson returns 404 and is unchanged
- Locked: `PUT`, `PATCH` and `DELETE` on a completed lesson, and on a passed lesson, return 403 with the locked message and change nothing; a locked lesson with an invalid body still returns 403
- `DELETE /trial-lessons/{id}/` on an open lesson: 204 and the lesson is gone; the student can then book another; the date and time can be booked by another student; another student's lesson returns 404 and is kept
- Weekly classes (the rule picked up from spec 03, added to this file): `POST /classes/` on the weekday and hour of an upcoming trial lesson returns 400 under `non_field_errors`, for another student's trial lesson and for the student's own; a trial lesson that has passed does not block; `PUT` / `PATCH /classes/{id}/` moving a class onto an upcoming trial lesson's slot returns 400
- Cascades: deleting a student's account deletes their trial lesson; deleting a subject or a level that a trial lesson uses raises `ProtectedError`
- Model rules: saved without validation, a second trial lesson for one student, a duplicate `starts_at` and a non-full-hour `starts_at` each raise `IntegrityError`; `full_clean()` rejects a non-full-hour `starts_at`, a level that is not one of the subject's, and an upcoming `starts_at` on a weekly class's slot; `full_clean()` accepts a past `starts_at`
- Subject admin form (`classes.admin.SubjectAdminForm`, tested on the form): saving a subject without a level its trial lesson uses is invalid with an error on `levels`; a level used only by another subject's trial lesson does not block

Every trial lesson a test builds needs a level that is one of its subject's levels; fetch the seeded levels with `Level.objects.get(code=...)` and give test subjects their levels explicitly.

Not covered here: the schedule and the weekly cost (spec 05).

## Definition of done
- [ ] `uv run python manage.py makemigrations --check` reports no missing migrations
- [ ] Each route returns the expected status for an anonymous request (all six `/trial-lessons/` routes return 401)
- [ ] The feature's routes are marked Implemented in `CLAUDE.md`
- [ ] `uv run python manage.py migrate` applies `classes.0010` cleanly on MySQL, including the unique constraint and the full-hour check constraint
- [ ] A registered student can `POST /trial-lessons/` with `subject`, `level` and `starts_at` and gets 201 with `id`, `subject`, `level`, `starts_at` and `completed`, where `subject` comes back as `{"id", "name", "levels"}`, `level` as `{"code", "name"}` and `starts_at` in UTC
- [ ] `POST /trial-lessons/` with a level the subject does not have returns 400 under `level`
- [ ] `POST /trial-lessons/` with a `starts_at` at half past the hour, or in the past, returns 400 under `starts_at`
- [ ] A second `POST /trial-lessons/` by the same student returns 400 with `"You have already booked a trial lesson."`
- [ ] `POST /trial-lessons/` at another student's trial lesson time, or on the weekday and hour of any weekly class, returns 400 with `"This timeslot is already booked."`
- [ ] `POST /classes/` on the weekday and hour of an upcoming trial lesson returns 400; after that trial lesson has passed the same booking succeeds
- [ ] `PATCH /trial-lessons/{id}/` changes an open lesson's subject, level or `starts_at`; sending `completed` changes nothing
- [ ] After an admin marks the lesson completed, `PATCH` and `DELETE /trial-lessons/{id}/` return 403 with `"This trial lesson can no longer be changed."`, `GET` still returns it, and a new `POST` returns 400
- [ ] `DELETE /trial-lessons/{id}/` on an open lesson returns 204 and the student can book again
- [ ] `GET`, `PATCH` and `DELETE /trial-lessons/{id}/` on another student's lesson return 404
- [ ] `GET /trial-lessons/` returns a list with the student's lesson, or an empty list
- [ ] A superuser's token gets 403 on `GET /trial-lessons/`
- [ ] In the Django admin, Trial lesson has a list page showing student, subject, level, start and completed, can be filtered by completed, and its form can mark a lesson completed and rejects a non-full-hour time, a taken time and a level the subject does not have
- [ ] In the Django admin, deleting a subject or a level that a trial lesson uses is refused, and removing a level from a subject whose trial lesson uses it is refused with an error
- [ ] `uv run pytest classes/tests/test_trial_lessons.py` passes (after `/test-feature trial-lessons`)
