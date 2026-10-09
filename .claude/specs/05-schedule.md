# Spec: My Schedule

## Overview
My schedule is the one read-only route that shows a student everything they have booked and what it costs: their weekly classes, their trial lesson, and the total they pay per week. This feature adds `GET /schedule/`, which returns the logged-in student's weekly classes (each with its own price), their trial lesson, and `weekly_cost`, the sum of the class prices. It stores nothing new: it reads the `WeeklyClass` and `TrialLesson` rows the earlier features created and the two prices on `Subject`. It is built last because it needs all four earlier features: the Student (feature 1), the subject prices (feature 2), the weekly classes it totals (feature 3) and the trial lesson it shows (feature 4).

## Depends on
- `.claude/specs/01-users.md` — the `Student` profile whose bookings are returned, and JWT authentication.
- `.claude/specs/02-subjects.md` — `Subject.price_40_min` and `Subject.price_60_min`, which price a weekly class.
- `.claude/specs/03-weekly-classes.md` — the `WeeklyClass` model, `WeeklyClassSerializer`, `WeeklyClassQuerySet.in_week_order()` and `IsStudent`, all reused here.
- `.claude/specs/04-trial-lessons.md` — the `TrialLesson` model and `TrialLessonSerializer`, reused here.

All four are implemented.

## Requirements
1. The schedule returns the logged-in user's schedule together with their total cost per week.
2. The weekly cost is the sum of the prices of all the user's weekly classes.
3. Each weekly class is priced by its own duration: a 40-minute class costs its subject's 40-minute price, a 60-minute class costs its subject's 60-minute price.
4. Trial lessons are free and add nothing to the weekly cost.
5. A student only ever sees their own weekly classes and trial lesson (API conventions: every booking queryset is scoped to `request.user`).

Decisions the user made on points `CLAUDE.md` leaves open:

6. **Layout** — the response has three separate parts: `weekly_classes` (a list), `trial_lesson` (one object, or `null` when the student has none) and `weekly_cost`. Weekly classes and the trial lesson are not mixed into one list.
7. **Price of each class** — every weekly class in the schedule also carries its own `price`, so the student can see what makes up the total. `weekly_cost` is the sum of those `price` values.
8. **A finished trial lesson** — the trial lesson is always shown, including when it is marked completed or its date and time have passed, with its `completed` flag. This matches `/trial-lessons/`, where a locked lesson stays readable.

Choices of this spec that follow the earlier features:

9. **Users without a Student** — a logged-in user with no Student profile gets 403 on `/schedule/`, as on `/classes/` and `/trial-lessons/`.
10. **Shapes** — a weekly class in the schedule has the same fields as on `/classes/` (`id`, `subject`, `level`, `day`, `day_display`, `time`, `duration`) plus `price`. The trial lesson has exactly the fields it has on `/trial-lessons/` (`id`, `subject`, `level`, `starts_at`, `completed`), and no price. The nested `subject` still carries no prices.
11. **Order** — `weekly_classes` is ordered Monday to Sunday, then by time, as on `GET /classes/`.
12. **Timezone** — every day, time and date-time is UTC, as everywhere in the API.

Choices of this spec that are not product rules:

13. A student with no weekly classes gets `weekly_classes: []` and `weekly_cost: 0.0`. A student with no bookings at all still gets 200.
14. Prices are read from the subject at the moment of the request; no price is stored on a weekly class. When an admin changes a subject's price, the schedule shows the new price and the new total from then on.
15. `price` and `weekly_cost` are returned as JSON numbers, not strings, like the prices on `/subjects/` (`COERCE_DECIMAL_TO_STRING` is `False`). They are rounded to two decimal places, but JSON does not keep trailing zeros: 30.00 is sent as `30.0`.
16. A free subject (price 0.00) gives a class with `price: 0.0`; it adds nothing to the total.
17. The route is read-only: only `GET`. Bookings are created, edited and deleted on `/classes/` and `/trial-lessons/`.

## Deferred rules
No rule of this feature is deferred.

Picked up from earlier specs:
- **Weekly cost** (`.claude/specs/03-weekly-classes.md`, Deferred rules; `.claude/specs/02-subjects.md`, Deferred rules) — pricing each weekly class by its own duration from the subject's two prices and totalling them. Implemented here (Requirements 2, 3, 7).
- **My schedule** (`.claude/specs/04-trial-lessons.md`, Deferred rules) — returning the trial lesson with the student's weekly classes, and counting it as free in the weekly cost. Implemented here (Requirements 4, 6, 8).

## Routes
- `GET /schedule/` — the logged-in student's weekly classes with their prices, their trial lesson and their total weekly cost — authenticated student

An anonymous request returns 401; an authenticated user without a Student returns 403. `POST`, `PUT`, `PATCH` and `DELETE` return 405 for a student.

## Models and database changes
No database changes: no new model, field or constraint, and no migration. `uv run python manage.py makemigrations --check` must still report nothing to generate.

One addition to `classes/models.py` that does not touch the schema:

`WeeklyClass.price` (new, read-only property) — returns `subject.price_40_min` when `duration` is `ClassDuration.FORTY` and `subject.price_60_min` when it is `ClassDuration.SIXTY`. It returns the `Decimal` stored on the subject, unchanged. This is the one place the "priced by its own duration" rule lives; the schedule's `price` and `weekly_cost` both come from it.

`Student`, `Level`, `Subject`, `TrialLesson` and `core.User` are unchanged.

## Serializers and validation
All in the existing `classes/serializers.py`. The route takes no input, so there is no validation.

`classes.serializers.ScheduleWeeklyClassSerializer` (subclass of `WeeklyClassSerializer`):
- Fields: those of `WeeklyClassSerializer` plus `price`: `id`, `subject`, `level`, `day`, `day_display`, `time`, `duration`, `price`.
- `price` — a declared read-only `DecimalField(max_digits=6, decimal_places=2)` reading `WeeklyClass.price`.
- Used only for output in the schedule. `WeeklyClassSerializer` and the `/classes/` responses are unchanged: they still carry no price.

`classes.serializers.ScheduleSerializer` (plain `serializers.Serializer`, output only):
- `weekly_classes` — `ScheduleWeeklyClassSerializer(many=True, read_only=True)`.
- `trial_lesson` — `TrialLessonSerializer(read_only=True, allow_null=True)`; `null` when the student has no trial lesson.
- `weekly_cost` — read-only `DecimalField(max_digits=10, decimal_places=2)`.

`TrialLessonSerializer` is reused as it is; the trial lesson has no price field.

A response looks like:

```json
{
  "weekly_classes": [
    {
      "id": 4,
      "subject": {"id": 3, "name": "Physics", "levels": [{"code": "o_level", "name": "O Level"}, {"code": "a_level", "name": "A Level"}]},
      "level": {"code": "a_level", "name": "A Level"},
      "day": "monday",
      "day_display": "Monday",
      "time": "16:00:00",
      "duration": 60,
      "price": 30.0
    },
    {
      "id": 7,
      "subject": {"id": 5, "name": "Maths", "levels": [{"code": "o_level", "name": "O Level"}]},
      "level": {"code": "o_level", "name": "O Level"},
      "day": "wednesday",
      "day_display": "Wednesday",
      "time": "10:00:00",
      "duration": 40,
      "price": 25.0
    }
  ],
  "trial_lesson": {
    "id": 1,
    "subject": {"id": 3, "name": "Physics", "levels": [{"code": "o_level", "name": "O Level"}, {"code": "a_level", "name": "A Level"}]},
    "level": {"code": "a_level", "name": "A Level"},
    "starts_at": "2026-10-13T02:00:00Z",
    "completed": false
  },
  "weekly_cost": 55.0
}
```

A student with nothing booked gets `{"weekly_classes": [], "trial_lesson": null, "weekly_cost": 0.0}`.

How the total is computed: `weekly_cost` is the sum of `WeeklyClass.price` over the same weekly classes the response lists, added as `Decimal` starting from `Decimal("0.00")`. It is never a `float`, and it is not a second query with its own copy of the pricing rule. The trial lesson is not part of the sum.

## Views and URLs
`classes.views.ScheduleView`:
- Base class: `rest_framework.views.APIView`. The route aggregates two models and a total and maps onto no model's CRUD, so it is not a `ModelViewSet` (API conventions).
- `permission_classes = [IsAuthenticated, IsStudent]`, in that order, so an anonymous request gets 401 and a user without a Student gets 403.
- Only `get()` is defined; every other method answers 405.
- `get()` reads `request.user.student` and loads:
  - the weekly classes: `WeeklyClass.objects.filter(student=student).select_related("subject", "level").prefetch_related("subject__levels").in_week_order()`, the same queryset as `WeeklyClassViewSet.get_queryset()`. `select_related("subject")` is also what makes `price` cost no query per class;
  - the trial lesson: `TrialLesson.objects.filter(student=student).select_related("subject", "level").prefetch_related("subject__levels").first()`, which is `None` when there is none. It is not filtered by `completed` or by `starts_at`.
- It evaluates the weekly classes once, sums their `price`, and returns `ScheduleSerializer` data with 200. The serializer is given the request in its context.
- The number of queries does not grow with the number of weekly classes.
- If `WeeklyClassViewSet` and `ScheduleView` would repeat the same scoped queryset, move it to one place they both use (e.g. a `for_student(student)` method on `WeeklyClassQuerySet` in `classes/querysets.py`) instead of copying it.

`classes/urls.py`: the view is not a viewset, so it is added beside the router's routes: `urlpatterns = [path("schedule/", ScheduleView.as_view(), name="schedule"), *router.urls]`.

`config/urls.py` is unchanged: it already mounts `classes.urls` at the root, giving `/schedule/`.

## Admin
No admin changes. The feature adds no model, and there is nothing admin-only: an admin already sees and edits every student's weekly classes and trial lessons, and sets the subject prices, on the existing admin pages. No per-student schedule or cost page is added to the admin.

## Files to change
- `classes/models.py` — add the `WeeklyClass.price` property
- `classes/serializers.py` — add `ScheduleWeeklyClassSerializer` and `ScheduleSerializer`
- `classes/views.py` — add `ScheduleView`
- `classes/urls.py` — add the `schedule/` path
- `classes/querysets.py` — only if the shared scoped queryset is moved here (see Views and URLs)
- `CLAUDE.md`:
  - "Implemented vs Stub Routes" > My schedule: `GET /schedule/` goes from Stub to Implemented
  - Product requirements: the "Only requirements 1, 2, 3 and 4 are built so far" line; requirement 5 gains the decisions above (the three parts `weekly_classes`, `trial_lesson`, `weekly_cost`; `price` on each class; a finished trial lesson is still shown; `null` and `0.00` when there is nothing; 403 without a Student; read-only; prices read live from the subject)
  - Architecture: `classes/` mentions `ScheduleView` and that it is a plain path beside the router in `classes/urls.py`
- `.claude/agents/nest-test-writer.md`, `.claude/agents/nest-security-reviewer.md` and `.claude/agents/nest-quality-reviewer.md` — their copies of the schedule rules gain the decisions above, in the same change. Any other command or agent file that turns out to carry these rules gets the same update
- `.claude/specs/03-weekly-classes.md` and `.claude/specs/04-trial-lessons.md` — their Deferred rules entries for the weekly cost and the schedule are marked as picked up by this spec

## Files to create
No new application files.

`classes/tests/test_schedule.py` is created later by `/test-feature schedule`, not during implementation.

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
- The schedule is an `APIView` with only `get()`; do not add a write method, and do not register it on the router
- The student is always `request.user.student`; do not accept a student, user or id in the path or the query string
- Never assume `request.user.student` exists outside code guarded by `IsStudent`
- Both querysets are filtered by the logged-in student; nothing in the response comes from another student's bookings
- The pricing rule is `WeeklyClass.price`, defined once; the serializer's `price` and the total both use it, and neither repeats the 40-or-60 choice
- All money arithmetic is `Decimal`: start the sum from `Decimal("0.00")`, never `0.0`, and never convert to `float`
- `weekly_cost` is the sum of the `price` values in the same response; the two can never disagree
- The trial lesson never adds to `weekly_cost` and has no price field
- Do not filter the trial lesson by `completed` or `starts_at`; a locked lesson is still shown
- `trial_lesson` is one object or `null`, never a list
- Do not store a price or a total on any model, and do not add a migration
- Do not change `WeeklyClassSerializer`, `TrialLessonSerializer`, `SubjectSerializer` or the responses of `/classes/`, `/trial-lessons/` and `/subjects/`; in particular `/classes/` still returns no price and the nested subject still has no prices
- Reuse `WeeklyClassSerializer`, `TrialLessonSerializer` and `in_week_order()`; do not rewrite the weekly class or trial lesson shapes or the week ordering
- Any queryset that serializes weekly classes or a trial lesson uses `select_related("subject", "level")` and prefetches `subject__levels`; the schedule runs no query per class
- Every day, time and date-time is returned in UTC as stored; do not convert to another timezone and do not change `TIME_ZONE` or `USE_TZ`
- Do not add fields the spec does not list (no currency field, no per-month cost, no class count, no "next class" date, no `is_locked`)
- No pagination and no filters on the route
- Do not write tests during implementation

## Tests
Covered by `classes/tests/test_schedule.py`, written and run with `/test-feature schedule`, not as part of implementation. A test student is `baker.make(get_user_model())` plus `baker.make(Student, user=user)`. Bookings are built with `baker.make`, each with a level that is one of its subject's levels (seeded levels fetched with `Level.objects.get(code=...)`), and each weekly class on its own day and time. Subjects are given explicit prices, with a 40-minute price different from the 60-minute one, so a test can tell which was used. Money is compared as `Decimal`. A trial lesson's `starts_at` is built relative to `timezone.now()`, rounded to a full hour. It must cover:
- Access: `GET /schedule/` returns 401 for an anonymous request and 403 for an authenticated user without a Student
- Read-only: `POST`, `PUT`, `PATCH` and `DELETE /schedule/` return 405 for a student and change nothing
- Top level: 200 with exactly `weekly_classes`, `trial_lesson` and `weekly_cost`
- Empty: a student with no bookings gets `weekly_classes` `[]`, `trial_lesson` `null` and `weekly_cost` zero
- Weekly class shape: each item has exactly `id`, `subject`, `level`, `day`, `day_display`, `time`, `duration`, `price`; `subject` is an object with exactly `id`, `name` and `levels` and no price fields; `level` is an object with exactly `code` and `name`
- Price by duration: a 40-minute class has the subject's 40-minute price; a 60-minute class has the subject's 60-minute price; two classes of the same subject with different durations each get their own price
- Total: `weekly_cost` is the sum of the classes' prices, for one class, for several classes of different subjects and durations, and for several classes of the same subject; it equals the sum of the `price` values in the response; the sum is exact (e.g. 0.10 + 0.20 is 0.30)
- Free subject: a class of a subject priced 0.00 has `price` zero and adds nothing to the total
- Trial lesson is free: a student with only a trial lesson has `weekly_cost` zero; adding a trial lesson to a student with classes does not change `weekly_cost`, including when the trial lesson's subject has prices
- Trial lesson shape: `trial_lesson` is one object with exactly `id`, `subject`, `level`, `starts_at`, `completed`, with no price, and `starts_at` in UTC
- Finished trial lesson: a completed trial lesson and one whose `starts_at` has passed are both still returned, with the right `completed` value
- Scoping: another student's weekly classes and trial lesson never appear and never add to the total; a student with no bookings sees an empty schedule while another student has bookings
- Order: `weekly_classes` is ordered Monday to Sunday, then by time
- Live prices: after a subject's price is changed, the next `GET /schedule/` shows the new `price` and the new `weekly_cost`
- Query count: `GET /schedule/` runs the same number of queries for a student with one class as for a student with several classes in different subjects
- Model rule: `WeeklyClass.price` returns the subject's 40-minute price for a 40-minute class and its 60-minute price for a 60-minute class, as a `Decimal`
- Unchanged routes: `GET /classes/` still returns no `price` on a weekly class

## Definition of done
- [ ] `uv run python manage.py makemigrations --check` reports no missing migrations
- [ ] Each route returns the expected status for an anonymous request (`GET /schedule/` returns 401)
- [ ] The feature's routes are marked Implemented in `CLAUDE.md`
- [ ] A registered student with no bookings gets 200 from `GET /schedule/` with `{"weekly_classes": [], "trial_lesson": null, "weekly_cost": 0.0}`
- [ ] A student with a 60-minute Physics class (60-minute price 30.00) and a 40-minute Maths class (40-minute price 25.00) gets both classes with `price` 30.0 and 25.0 and `weekly_cost` 55.0
- [ ] Each weekly class in the schedule has `id`, `subject`, `level`, `day`, `day_display`, `time`, `duration` and `price`, and its nested `subject` has no prices
- [ ] After the student books a trial lesson, `trial_lesson` is that lesson as one object and `weekly_cost` is unchanged
- [ ] After an admin marks the trial lesson completed, `GET /schedule/` still returns it with `completed` true
- [ ] After an admin changes a subject's price in the Django admin, `GET /schedule/` shows the new `price` and `weekly_cost`
- [ ] `weekly_classes` is ordered Monday first, then by time
- [ ] A second student's `GET /schedule/` shows none of the first student's bookings and none of their cost
- [ ] A superuser's token gets 403 on `GET /schedule/`
- [ ] `POST /schedule/` with a student's token returns 405
- [ ] `GET /classes/` still returns weekly classes without a `price`
- [ ] `uv run pytest classes/tests/test_schedule.py` passes (after `/test-feature schedule`)
