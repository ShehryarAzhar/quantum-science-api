---
description: Writes and runs tests for a specific Science Tutor API feature. Pass the feature name as argument e.g. /test-feature trial-lessons
argument-hint: subjects | weekly-classes | trial-lessons | schedule | users
allowed-tools: Bash(uv run pytest:*)
---

Run the full testing pipeline for the feature specified
in $ARGUMENTS.

If no argument is provided, stop immediately and say:
"Please provide a feature name. Usage: /test-feature
<feature> e.g. /test-feature trial-lessons. Features:
subjects, weekly-classes, trial-lessons, schedule, users"

Look the feature up in this table:

| Feature | Spec file | Spec in `CLAUDE.md` | Routes | App | Test file |
| --- | --- | --- | --- | --- | --- |
| `subjects` | `.claude/specs/01-subjects.md` | Product requirements 1 (Subjects) | `/subjects/` | `classes` | `classes/tests/test_subjects.py` |
| `weekly-classes` | `.claude/specs/02-weekly-classes.md` | Product requirements 2 (Weekly class scheduling) | `/classes/` | `classes` | `classes/tests/test_weekly_classes.py` |
| `trial-lessons` | `.claude/specs/03-trial-lessons.md` | Product requirements 3 (Trial lessons) | `/trial-lessons/` | `classes` | `classes/tests/test_trial_lessons.py` |
| `schedule` | `.claude/specs/04-schedule.md` | Product requirements 4 (My schedule) | `/schedule/` | `classes` | `classes/tests/test_schedule.py` |
| `users` | none | Architecture > Auth | `/auth/users/`, `/auth/users/me/`, `/auth/jwt/create/` | `core` | `core/tests/test_users.py` |

If $ARGUMENTS is not one of these features, stop
immediately and say:
"Unknown feature '$ARGUMENTS'. Features: subjects,
weekly-classes, trial-lessons, schedule, users"

If the feature's routes are still marked Stub in the
"Implemented vs Stub Routes" section of `CLAUDE.md`,
stop immediately and say:
"The $ARGUMENTS routes are still marked Stub in
CLAUDE.md. Implement the feature (and update the route
tables) before testing it."

In the steps below, `<app>`, `<spec file>` and
`<test file>` mean the values from the feature's row in
the table.

Spec files are written by `/create-spec`. If the
feature's spec file is "none" or does not exist, tell
both subagents that there is no spec file and that the
feature's section of `CLAUDE.md` is the whole spec, and
say so in the final summary.

---

## Step 1: Write Tests

Invoke the **quantum-test-writer** subagent with the
following context:

- Feature under test: $ARGUMENTS
- Spec to base tests on: `<spec file>`, together with
  the feature's section of `CLAUDE.md`, its "API
  conventions" section and the feature's route table
- Deferred rules: skip any rule `<spec file>` defers to
  a later spec, and check the other files in
  `.claude/specs/` for rules they deferred to this
  feature
- Source files to read for structure only:
  - `<app>/models.py`
  - `<app>/serializers.py`
  - `<app>/views.py`
  - `<app>/urls.py` and `config/urls.py`
- Output test file to create: `<test file>`. If it
  already exists, extend or correct it instead of
  starting over
- Shared fixtures: the root `conftest.py` (create it if
  it does not exist)
- Instruction: Write tests based on what the spec says
  the feature SHOULD do. Do NOT derive test logic from
  reading the implementation. Cover auth guards,
  ownership scoping, validation errors, happy paths,
  DB side effects, and every booking rule the spec
  lists for this feature.

Wait for quantum-test-writer to fully complete and
confirm the test file has been written and its tests
are collected before proceeding to Step 2.

---

## Step 2: Run Tests

Once quantum-test-writer has finished, invoke the
**quantum-test-runner** subagent with the following
context:

- Test file to execute: `<test file>`
- Spec for context: `<spec file>`, together with the
  feature's section of `CLAUDE.md`
- Source files to analyze against when diagnosing
  failures:
  - `<app>/models.py`
  - `<app>/serializers.py`
  - `<app>/views.py`
- Run command:
  `uv run pytest <test file> -v`
- Instruction: Run ONLY the specified test file. Do
  NOT run the full test suite. Analyze any failures by
  cross-referencing the test code, the spec, and the
  source files. Classify each failure as an
  implementation bug, a test bug, or an environment
  problem. A failing test for a rule `<spec file>`
  defers to a later spec is a test bug.

---

## Handoff Rules

- Do NOT start Step 2 until Step 1 is fully complete
- Do NOT attempt to fix any code, test or
  implementation, regardless of what the test results
  show
- Do NOT run any tests beyond `<test file>`
- If quantum-test-writer reports it could not write
  the test file, or asks a question about ambiguous
  behavior, stop and report that — do NOT proceed to
  Step 2
- If quantum-test-runner reports an environment
  problem (MySQL unreachable, missing migrations),
  report it as such — do NOT give a pass or fail
  verdict

---

## Final Output

After both subagents complete, produce a combined
summary:

### Testing Pipeline Report — $ARGUMENTS

**Step 1 — Tests Written**
- List each test written with a one-line description
  of which spec requirement it validates

**Step 2 — Test Results**
- Mirror the quantum-test-runner's structured report

**Verdict**
One of:
- ✅ Ready for code review — all tests pass
- ❌ Needs fixes — list the failing tests, their root
  causes, and whether each is an implementation bug or
  a test bug
- ⚠️ Could not run — the environment problem that
  blocked the run
