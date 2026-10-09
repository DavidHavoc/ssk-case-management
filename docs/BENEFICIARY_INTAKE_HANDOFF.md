# Beneficiary intake handoff, 2026-10-09

Implemented locally on the existing `codex/center-beneficiary-codes` working tree. All preceding
contact, enrollment identifier/date, and beneficiary staffing work is preserved. No deployment,
SSH, push, production data access, or production migration occurred. Fixtures and browser
preview records are synthetic.

## Persisted boundary

`0019_beneficiary_intake` adds `BeneficiaryIntake` and `BeneficiaryIntakeRevision`. The intake is
an optional one-to-one beneficiary record with UUID and created/updated timestamps inherited
from `ValidatedModel`. Existing beneficiaries receive no new record and no fabricated values.
The application also avoids creating a record for an entirely blank first submission.

| Group | Persisted fields |
|---|---|
| Health narrative | `health_condition` |
| General condition | `general_conditions` |
| Health problems | `health_problems`, `health_problems_other` |
| Functional condition | `functional_conditions` |
| Cognitive condition | `cognitive_conditions`, `cognitive_other` |
| Allergies | `allergies`, `allergies_description` |
| Medications | `current_medications` |
| Treating doctor | `treating_doctor_name`, `treating_doctor_contact` |
| Other services | `other_services`, `other_services_details` |
| Living situation | `living_situation`, `living_situation_notes` |
| Consent decisions | `service_consent`, `care_sharing_consent`, `confidentiality_consent`, `media_consent` |
| Initial care | `initial_care_services` |

All five checklist groups use JSON lists validated against explicit stable choices in
`apps/casework/intake_schema.py`. Choices can overlap, including general, functional, and
cognitive conditions. There are no clinical exclusivity assumptions. JSON type, member type,
invalid codes, and duplicate members are rejected by model validation. Forms use multi-select
checkboxes with the same codes. Scalar choice fields use ordinary Django choice validation.

Yes/no codes are `yes`, `no`, and the empty string for unanswered. Media codes are `agree`,
`decline`, and unanswered. Living situation codes are `alone`, `family`, `other`, and unanswered.
Doctor fields are text up to 240 characters; the contact accepts telephone, email, or both.
Other narratives and notes are multiline. Free text, including spacing and line breaks, remains
exactly as entered.

An Other health/cognitive selection requires its associated narrative. Allergies Yes and other
services Yes require descriptions. Living situation Other requires living situation notes;
notes remain optional for other arrangements. Deselecting Other health/cognitive or changing
Yes to No/unanswered clears the now-inapplicable description. Prior content is retained in
restricted revision evidence. Living notes are independent notes and remain usable for all
arrangements, separate from the existing family/marital status.

## Authorization and atomicity

Managers and authorized active center coordinators can read/update all intake groups through
an authorized beneficiary/enrollment. Confirmed current lead/helper specialists can read/update
health and social support, subject to active user/profile, center membership, current responsibility,
and an authorized current enrollment placement. Specialists retain existing care-planning scope
for the initial checklist. Consent decisions and beneficiary documents remain manager/coordinator
only. The legacy staffing bridge grants no new health/social/consent access.

The plain intake form constructs only authorized fields and loads initial values with a column
projection. Specialist detail responses contain no consent decisions/declaration, restricted
contacts, guardian identity, person IDs, addresses, or restricted imported source values. The
narrow `/beneficiaries/<uuid>/intake/` editor permits these updates without posting person fields.
The general creation/editing flow also includes authorized intake sections before Supporting
document. Existing clients omitting the entire intake subform preserve it; `intake-present`
identifies an explicit blank submission so clearing every selection works.

The write service locks and reloads the persisted beneficiary, then reloads account/role/center
and checks capabilities again. It merges authorized values into the freshly loaded current
record. Reassignment, deactivation, or transfer between form validation and save cannot preserve
old authority. Intake saves share the same person lock as staffing, lifecycle, and casework.
Creation validates all subforms before saving person, enrollment, staffing, intake, revision,
audit, and optional attachment in the existing atomic upload transaction. Person editing saves
all bound classification/intake forms in one transaction. Invalid sections rerender entered
values and errors. A late file-save failure rolls back rows and removes the stored upload.

`BeneficiaryIntakeRevision` stores restricted before/after values, the staff actor, and timestamps,
following the existing ServiceVisitCorrection evidence pattern. Ordinary model mutation/deletion
of a revision is refused. This is application-level evidence, not a cryptographic or database-level
immutability guarantee. No new public history endpoint or generalized questionnaire engine was
added. Existing sensitive-read/update audit events are reused with empty safe metadata; health
narratives, consent content, and contacts are never added to audit metadata.

No new data is included in general search, list snippets, dashboards, ordinary CSV, timelines,
or operational reports. Imported restricted evidence, coded diagnoses, assessment instruments,
service catalogs, versioned IndividualPlan rows, goals, schedules, visits, and billing remain
independent and are not synthesized from this checklist.

## English and Georgian

All new headings, labels, choices, help text, validation messages, and empty states have Georgian
translations and compiled gettext output. Django's built-in invalid-choice and length errors use
its Georgian catalog. Scalar labels bypass automatic capitalization so the company's Georgian
wording and casing are retained. Allergies uses contextual Yes translation `კი`; other services
uses `დიახ`. Stored codes do not vary by display language.

The two spelling corrections are `ოჯახთან ერთან` to `ოჯახთან ერთად`, and
`საკვებით მომსახურეობა` to `საკვებით მომსახურება`. The duplicate health narrative headings
were consolidated into `ჯანმრთელობის მდგომარეობა / ძირითადი პრობლემა`; its help text retains
main condition/problem addressed. The complete supplied Georgian media declaration is retained,
including its third bullet. No replacement legal terms or statement of verified compliance was
introduced. Existing staffing translations removed by gettext extraction were restored and
regression-tested.

## Changed files for this intake task

- `apps/casework/models.py`, `forms.py`, `views.py`, `urls.py`.
- `apps/casework/intake.py`, `intake_schema.py`, and migration `0019_beneficiary_intake.py`.
- `apps/core/authorization.py`, `forms.py`.
- `templates/casework/beneficiary_form.html`, `beneficiary_detail.html`, `intake_form.html`.
- `templates/casework/includes/intake_fields.html`, `intake_detail.html`, `media_declaration.html`.
- `static/css/app.css`, Georgian `django.po` and `django.mo`.
- `tests/test_beneficiary_intake.py`.
- `docs/PERMISSION_MATRIX.md`, `DATA_MODEL.md`, and this handoff.

Earlier changed files outside this list remain untouched. Baseline hashes were captured before
implementation and compared after completion. All work remains uncommitted.

## Verification

- Complete SQLite suite: **493 passed, 7 PostgreSQL-only skips in 184.68 seconds**.
- Complete disposable PostgreSQL 16 suite: **500 passed, no skips in 302.67 seconds**.
  This includes all 75 intake cases, shared intake/staffing lock serialization, persisted-person
  scope, deactivation/transfer/reassignment rechecks, and schema forward/reverse tests.
- The strengthened actual HTML report and CSV export privacy test was run after its test-only
  refinement: **1 passed in 3.90 seconds on SQLite**, **1 passed in 6.70 seconds on PostgreSQL**.
  Synthetic visits, assessments, and plans exercise the existing reporting sources.
- Create/edit/detail/clear round trips passed for managers and coordinators in both languages.
  Lead/helper projections, forged POSTs, expired/unassigned/inactive memberships, cross-center
  denial, legacy bridge limits, conditional descriptions, invalid codes in both languages,
  malformed JSON, explicit No versus unanswered, and exact free-text preservation passed.
- Invalid intake/enrollment/attachment sections and forced failure after a file write left no
  beneficiary, enrollment, staffing, intake, revision, or uploaded-file partial result.
  Imported source evidence and formal plan snapshots were unchanged.
- Ruff lint passed; format check reported **143 files already formatted**. `git diff --check`
  passed. New source/handoff files contain no em dashes. All **52** preceding changed/untracked
  files outside this task's explicitly touched existing files match their baseline hashes.
- Django system checks and deployment checks with `--fail-level WARNING` passed using synthetic
  local configuration. `makemigrations --check --dry-run` reported no changes. Fresh full
  migrations and `migrate --check` passed on separate temporary SQLite and PostgreSQL databases.
- `msgfmt --check` passed, and recompilation matched the delivered `.mo` byte for byte. Tests
  verified every new label and checklist option in Georgian, contextual allergy Yes, and the
  existing Future staffing translation. English/Georgian stable-code saves passed.
- In-app browser checks used a disposable synthetic account/database. English and Georgian
  forms fit **320, 768, 1024, and 1440 pixels** without document overflow. Checkbox groups use
  one column at narrow widths and two on desktop. Space toggled the checkbox, Tab reached the
  next option, and focus had a visible solid outline. Conditional error links resolved to their
  fields; entered text survived the error response. A corrected submission redirected to the
  authorized detail with the saved values. Browser console error inspection returned no errors.
- Creation UI showed health, social, consent, and initial care before Supporting document.
  All new single choices started unanswered, with zero selected checkboxes. The supplied media
  text, full consent questions, and Georgian labels wrapped at mobile widths. The existing
  sticky save/cancel action remained usable. Four synthetic screenshots were saved in the
  task visualization directory. Formal screen-reader and automated axe audits were not run.

Temporary preview/database cleanup completed after these checks. No production checks or
signature execution are implied by this local verification.

## Handoff for consent signing

The four consent columns are independently staff-recorded answers. Unanswered is never consent,
No/decline never blocks unrelated intake saving, and media agreement is never inferred from a
service answer. Revision actors identify recording staff, not a beneficiary signer. No signature,
signer identity, execution date, document template/version, or signed evidence has been invented.

The next chat should implement the narrow signature workflow and versioned signed evidence.
Use the established manager/coordinator consent capability and scoped beneficiary/enrollment;
do not expose signed consent documents to specialists as a consequence of health/social access.
Bind an executed signature to the exact declaration/version, decisions, signer capacity, and
execution event chosen for that workflow. Keep historical executed evidence separate from these
editable current reported answers. The owner has reserved this workflow for the next chat.
