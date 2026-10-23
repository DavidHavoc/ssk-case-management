# Individual and early intervention plan overhaul

Implemented and deployed on 2026-10-23 after the owner explicitly authorized deployment
and a GitHub push. See `PLAN_OVERHAUL_DEPLOYMENT_2026-10-23.md` for the release evidence.

New plans use a selectable care-activity table in place of the measurable-goal editor.
The Individual and Early intervention choices currently share this flow. Their active
periods and version numbers are separate within an enrollment.

The owner confirmed retaining the existing date and status fields. New review choices
are monthly, quarterly, and every six months. The owner also supplied the four Technical
activities: assistive equipment checks and help with use, minor technical help at home,
help arranging a safe environment, and Other. The remaining activities follow the blank
Georgian DOCX template. At least one activity is required; Other needs a description.

Beneficiary choices start with the name, followed by code and enrollment information.
The picker also shows the latest authorized completed Barthel score available today,
including zero. If only a historical intake index is available, it is explicitly labeled
as a recorded intake value. Draft and future assessments do not supply picker scores.
Scores are fetched with the authorized enrollment query rather than a query per option.
Choosing a beneficiary loads an authorized Barthel preview and the assigned specialists.
The preview and plan review show the latest completed, non-superseded Barthel assessment
on or before the plan date, its score, dependency, care need, additional care needs, and
the existing five-band scale. Missing assessments remain explicitly unrecorded. The
separate historical intake index is labeled on the beneficiary page. The plan list and
beneficiary plan table include Barthel results and signature state.

Each care category has a bold row-group label and a dark outline around its activities.
The same grouping appears in plan review and newly generated printable or signed copies.
Existing stored signed documents remain unchanged.

Plans save as drafts. The beneficiary or representative must review and sign before
activation. The workflow reuses the consent signature validation and pad, private
attachment transaction handling, signer fields, expiring actor/center-bound review
tokens, and a signed paper PDF alternative. Plan or Barthel changes invalidate an
outstanding review. Failed storage rolls back records and cleans up written files.
Signed content and files are immutable; status transitions remain available separately.
The signed HTML, signature evidence, and frozen review remain authorized downloads.
Signed plans are also linked from the beneficiary workspace. A content correction needs
a new plan period and signature.

Existing plans retain their goals, reviews, assignments, dates, and stored review
frequencies. They are not converted into fabricated activity selections or signatures.
Implementation and browser checks used an isolated temporary SQLite database with synthetic
people. Deployment later preserved all existing production rows and private files, as
recorded in the deployment report.

Migrations 0026 and 0027 add the plan fields, per-kind constraints, signed plan evidence,
and database guards. Existing rows retain workflow version 1; the new form creates version
2. Rollback refuses to discard new plan evidence. SQLite table rebuilds temporarily suspend
and reinstall the existing database guards. PostgreSQL also has raw deletion guards.

Verification:

- Complete SQLite regression suite: 662 passed, 10 PostgreSQL-only checks skipped.
- Final plan-specific suite after status and snapshot refinements: all 23 passed.
  The combined plan, legacy-plan, and view regression run passed all 43 tests.
- Ruff lint and formatting, Django system and deployment checks, migration drift checks,
  translation compilation, JavaScript syntax, and Git whitespace checks passed.
- Browser verification covered English and Georgian creation, both plan kinds, live Barthel
  loading, the supplied Technical activity, saved tables, review, handwritten signing,
  activation, and signed-plan status controls.
- The actual candidate image passed all 675 tests on an isolated PostgreSQL database on
  the VPS. Both backup restores, migration application, rollback rehearsal, and original-row
  reconciliation passed before the production release.

The original DOCX remains in Downloads. No real beneficiary data was used in local tests.
