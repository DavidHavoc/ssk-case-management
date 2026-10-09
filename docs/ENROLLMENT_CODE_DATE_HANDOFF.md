# Enrollment code and date handoff, 2026-10-08

Local implementation only. No deployment, SSH, GitHub push, production data access, or
production migration occurred. Work remains uncommitted on `codex/center-beneficiary-codes`.
The preceding contact-field work and its migration `0014` are preserved.

The automatic beneficiary code is the only operational case code. Intake, additional service,
re-enrollment, import, and demo paths no longer require or generate `episode_code`. Existing
values stay in that unique column as read-only legacy identifiers with exact spelling and
authorized search. New enrollments store `NULL`. UI lists, choices, reports, and reminders use
the beneficiary code, service, status, and enrollment date. Routes and mutations use the exact
enrollment UUID; workspace list links and pagination retain that UUID filter.

Enrollment date / ჩარიცხვის თარიღი remains `ServiceEnrollment.start_date`. Unknown historical
dates stay unset; the legacy intake POST no longer substitutes today. First service date stays
separate and validated against enrollment date, including re-enrollment. Other start-date
concepts retain their labels. Enrollment update still does not edit lifecycle dates.

## Migration and rollback

Apply `0014` before `0015_retire_operational_enrollment_codes`. The new migration only makes
legacy codes nullable and non-editable, changes the enrollment date's label, and removes legacy
code ordering from schedules. It performs no forward data transformation and preserves primary
keys, all foreign keys, source evidence, state events, prior-enrollment links, person codes, and
center sequence counters. The original historical migrations remain unchanged.

Schema reversal is exact while every enrollment still has an old identifier. A reverse
preflight refuses to restore the old required column when uncoded enrollments exist. It does
not invent replacement identifiers, delete records, or modify data. After new writes, retain
the nullable schema for any application rollback and review compatibility, or use a separately
authorized, verified pre-release backup. Do not remove new records merely to enable reversal.

## Staffing chat handoff

Use `ServiceEnrollment.pk` for every enrollment-specific assignment, form choice, redirect,
and mutation. The beneficiary code is shared by multiple episodes. `create_enrollment` and
`reenroll_beneficiary` no longer accept `episode_code`; re-enrollment accepts and preserves
`first_service_date`. Existing assignments and their effective intervals remain intact.
Assignment dates keep their own semantics and must not be relabeled as enrollment dates.

Keep the prior restricted emergency-contact fields and authorization controls. Preserve the
center sequence system and legacy beneficiary-code aliases. New staffing work should build on
this working tree and depend on migration `0015` if it adds a casework migration. No production
release is authorized by this handoff.

CSV consumers must update headers: former second-code columns now contain enrollment date,
and the enrollment report has one beneficiary-code column. Restricted contact information is
still excluded from operational reports and CSVs.

## Verification

- SQLite complete suite: 367 passed, 2 PostgreSQL-only skips in 91.08 seconds.
- PostgreSQL complete suite: 369 passed, no skips, in 159.94 seconds.
- Focused PostgreSQL enrollment and migration run: 28 passed in 22.54 seconds before the final
  pagination and operational-page additions. The complete run includes all additions.
- Synthetic migration fixture compares every row across all historical models, including
  relationship tables, through forward migration, guarded refusal after uncoded writes,
  lossless schema reversal, and forward replay. It explicitly links visits, assessments,
  plans/goals, assignments, transferred placements, prior episodes, source identifiers,
  state events, and beneficiary counters.
- Ruff lint passed. Ruff format check: 134 files already formatted.
- Django system and deployment checks passed with no issues. `makemigrations --check --dry-run` reports no changes.
- Fresh disposable SQLite and PostgreSQL migrations applied successfully and `migrate --check`
  passed. The pre-existing developer SQLite database was not migrated by this task.
- Georgian catalog compiled; `msgfmt --check --check-format` passed. `git diff --check` passed.
- Browser verification used a separate temporary synthetic SQLite database. English and
  Georgian forms have no enrollment-code input. Two services display one beneficiary code
  with distinct enrollment links. Unknown dates and separately labeled legacy identifiers
  render correctly. Georgian form widths 320, 768, 1024, and 1440 have no document overflow.
  Keyboard Tab moves from enrollment date to first service date. No browser warnings/errors
  were reported for the verified form. Temporary preview and database resources were removed.

## Files changed by this enrollment task

Application:

- `apps/casework/forms.py`
- `apps/casework/models.py`
- `apps/casework/services.py`
- `apps/casework/views.py`
- `apps/casework/workbook_import.py`
- `apps/casework/management/commands/seed_demo_data.py`
- `apps/casework/migrations/0015_retire_operational_enrollment_codes.py` (new)
- `apps/core/authorization.py`
- `apps/core/forms.py`
- `apps/core/reminders.py`
- `apps/core/reporting.py`
- `apps/core/views.py`

Templates and localization:

- `templates/casework/assessment_list.html`
- `templates/casework/beneficiary_detail.html`
- `templates/casework/beneficiary_list.html`
- `templates/casework/enrollment_form.html`
- `templates/casework/plan_detail.html`
- `templates/casework/plan_list.html`
- `templates/casework/schedule_list.html`
- `templates/casework/visit_detail.html`
- `templates/casework/visit_list.html`
- `templates/core/reports.html`
- `templates/includes/pagination.html`
- `locale/ka/LC_MESSAGES/django.po`
- `locale/ka/LC_MESSAGES/django.mo`

Tests:

- `tests/factories.py`
- `tests/test_beneficiary_codes.py`
- `tests/test_beneficiary_contacts.py` (only removes the retired intake-code key from prior work)
- `tests/test_center_service_offerings.py`
- `tests/test_daily_workflow.py`
- `tests/test_deployment.py`
- `tests/test_early_intervention_docx_import.py`
- `tests/test_early_intervention_import.py`
- `tests/test_enrollment_foundation.py`
- `tests/test_enrollment_identifier_migration.py` (new)
- `tests/test_enrollment_identifiers.py` (new)
- `tests/test_georgian_form_labels.py`
- `tests/test_security.py`
- `tests/test_workbook_import.py`

Documentation:

- `docs/ACCEPTANCE_CRITERIA.md`
- `docs/BENEFICIARY_ENROLLMENT_FOUNDATION.md`
- `docs/DATA_MODEL.md`
- `docs/DOMAIN_DECISIONS.md`
- `docs/SSK_PRODUCT_REQUIREMENTS.md`
- `docs/VPS_OPERATIONS_RUNBOOK.md`
- `docs/ENROLLMENT_CODE_DATE_HANDOFF.md` (new)

Prior contact-only changes still present include `0014_beneficiary_emergency_contacts.py`,
`templates/casework/beneficiary_form.html`, `templates/includes/form_fields.html`,
`docs/PERMISSION_MATRIX.md`, and `docs/SECURITY_AND_PRIVACY.md`.
