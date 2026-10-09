# Beneficiary staffing handoff, 2026-10-08

**Release policy updated on 2026-10-09:** the owner chose to end legacy specialist access at
deployment. Migration 0017 now preserves frozen snapshots with `expires_on = captured_on`,
so unresolved imported teams receive no compatibility access. Confirm their lead/helper pair
before specialist work. The 90-day policy and pending-decision statements below describe the
preceding review history and are superseded by this decision and
[the integrated release handoff](INTEGRATED_RELEASE_HANDOFF.md).

Local implementation only, on the existing `codex/center-beneficiary-codes` working tree.
The preceding contact fields, nullable enrollment identifiers, enrollment dates, automatic
beneficiary codes, aliases, and center counters are preserved. All work remains uncommitted.
No deployment, SSH, push, production data access, or production migration is authorized or performed.
All verification uses synthetic data and disposable databases.

## Operational source of truth

`BeneficiaryStaffingPeriod` stores a beneficiary, one required lead, one optional distinct helper,
inclusive `valid_from`, exclusive nullable `valid_to`, the confirming manager/coordinator, and
migration provenance. One complete row represents both roles, so separate row formsets cannot
create missing leads, extra helpers, or different teams per service. Periods never overlap.
Current staffing is derived from these periods; no mutable lead/helper copies live on enrollments.

Creation requires Lead specialist / მთავარი სპეციალისტი and optionally Helper specialist /
დამხმარე სპეციალისტი. A separate beneficiary staffing page replaces the complete pair through
`replace_beneficiary_staffing`. Enrollment create, update, and re-enrollment carry no staffing
inputs. Person updates do not require a pair, preserving unrelated edits on unresolved imports.
The detail page shows current names and roles and the bilingual review flag. Managers see dated
person-level history and untouched enrollment evidence. Historical enrollment forms are read-only.

The service locks the beneficiary, checks the acting manager's center scope and current eligible
choices, closes the covering period prospectively, creates the complete replacement, and bounds
it at the next already scheduled period. It rejects a second replacement with the same start date.
A transaction failure rolls back both closure and insertion. The model also locks and validates
ordinary ORM saves. Bulk writes and history deletion are refused. The database requires a lead,
distinct people, ordered dates, eligible appointment identities, and authorized confirmation.
The PostgreSQL insert/update guard also locks the beneficiary. PostgreSQL uses a GiST exclusion constraint to reject overlapping periods even for concurrent
writers that bypass forms. SQLite has equivalent overlap and appointment triggers for development.
The configured Django time zone is embedded in PostgreSQL date guards when installed.

New appointments cannot start before today. Existing rows' person, people, roles, start date,
confirmer, and provenance cannot be rewritten; only prospective shortening is supported. A
replacement cannot displace recorded responsibility on today's date. If a period already starts
today, or existing casework uses the replacement date, choose a later effective date. This date
model deliberately avoids rewriting responsibility earlier in the same day. Casework model saves
share the beneficiary lock with staffing saves. Forms carry the actor and selected center into
that locked write, including deferred `commit=False` saves. Authorization rechecks a freshly
loaded account, current responsibility, the original record's change scope, and fresh dated
enrollment state after acquiring the lock. Goals, progress measurements, reviews, assessment
responsibility links, attachment uploads, and attachment deletes use the same lock. Enrollment
transfers and lifecycle changes acquire the person lock before enrollment locks. Visit,
assessment, plan, and schedule rows retain
their original authors, dates, enrollment UUIDs, and event-time centers.

## Legacy review and the bridge deadline

Migration only confirms a current pair when every ongoing service has one eligible current lead,
at most one eligible distinct helper, identical dated teams, unambiguous role identities, and
one current active-center placement. Future appointments, unknown assignment dates, incomplete
intervals, joint leads, unequal teams or dates, missing assignments, and inactive profiles require
review. Exited cases receive neither invented current pairs nor compatibility grants.

`EnrollmentSpecialistAssignment` and original beneficiary assignments remain historical evidence.
Source workbooks, document data, restricted evidence, joint Primary roles, and source flags are
unchanged. New imports may create evidence, but it never independently grants current access.
Synthetic demo data explicitly confirms a pair through the same manager service.

`LegacyStaffingGrant` is an immutable migration snapshot of assignments that already granted
legitimate current access on the release date. It retains the original enrollment, specialist,
center, original placement, assignment interval, capture date, and expiry exactly 90 days later. Captured assignment
ends and subsequent interval shortening can end access earlier. Current eligibility and placement
still apply, with center identity and both placement boundaries bound to the captured placement.
Returning to the original center after a transfer creates a new placement and cannot revive
the old grant. Unresolved joint roles retain their original Primary/Secondary labels in the
workspace; they are not displayed as confirmed leads/helpers. The snapshot cannot grant access
to future/unknown assignments, added services, new
centers, or newly written source rows. Normal ORM writes and database insert/update triggers block
creating or extending grants. Historical test fixtures deliberately use migration models with the
snapshot insertion guard briefly disabled, then restored; this helper is test-only.

**Pending owner decision before deployment:** the exact compatibility-access length is currently
90 calendar days from the migration's local capture date. `captured_on` is inclusive and
`expires_on = captured_on + timedelta(days=90)` is exclusive, so access is denied on the expiry
date itself. The company requirements did not choose this duration. The owner must explicitly
accept 90 days or request a separately reviewed policy change before deployment. These audit
repairs leave the migration, captured grants, and deadline unchanged. This pending release
decision does not block the local repairs or proceeding with the complete Chat 4 prompt.

Managers resolve review cases from the beneficiary page's staffing action. They must explicitly
choose the lead and optional helper, confirm active-center eligibility, and choose today or a
future date that preserves recorded responsibility. Name order never selects a lead. Confirming a
joint case does not change or demote either original source assignment; the manager's new pair
applies only from its effective date. During any delay before a future confirmation, existing
bridge scope remains bounded by its original deadline.

The data-quality report and in-app reminders show the review issue and bridge deadline to existing
manager/coordinator roles. Unassigned cases remain readable to those roles and permit unrelated
person/enrollment edits. No externally delivered reminders are sent.

The bridge ends automatically at the earliest applicable boundary: captured assignment end,
original placement end or center change, loss of current eligibility, start of the first confirmed
period, or the 90-day deadline. Once any confirmed period has started, its expiry or a later gap
never revives legacy access. Confirm all ongoing cases before their bridge deadline. Preserve
frozen snapshots as audit evidence when the compatibility branch is retired in a separately
reviewed release; do not extend or regenerate snapshots to postpone review.

## Permission behavior

Lead and helper have equal ordinary casework rights. Person-wide responsibility covers only
this person's services with active selected-center membership and appropriate placement. Later
services inherit confirmed responsibility without separate assignment forms. Transfers do not
change the pair or confer membership in the destination. Exits retain staffing history but block
routine specialist access when the exit date becomes effective. Future exits do not prematurely
remove access before that boundary. Suspension retains readable scope but blocks completed work
through the existing dated lifecycle rules.

Current responsibility permits approved continuity reads, including earlier authorized casework
and event files. Creating or changing a dated record requires both the acting specialist's dated
responsibility/placement and an eligible recorded specialist on that business date. Earlier
untouched enrollment evidence validates past responsibility before the first confirmed period;
current and future work before a scheduled confirmation requires captured bridge scope. Evidence
never independently grants routine access. Responsible assessment links and goal responsibility
use the same rule. Historical inactive identities remain stored, but cannot be newly selected.

Neither role obtains manager, coordinator, staffing-management, CSV-export, restricted contact,
guardian, personal-ID, or beneficiary-document rights. Historical assignment rows remain restricted.
Forged staffing POSTs from specialists are denied. Forged extra enrollment assignment rows cannot
create another team. Files still use their existing parent adapters, which delegate to the updated
continuity/change selectors. There is no enabled Django admin, and model/ORM/database protections
prevent an alternative independently editable current staffing system.

## Migrations and rollback

Apply the preserved contact migration `0014` and enrollment migration `0015`, followed by:

1. `0016_beneficiary_staffing_periods`: additive schema for periods and frozen grants.
2. `0017_backfill_staffing_review`: snapshot already legitimate scope and conservatively confirm
   only unambiguous current teams. It changes no original rows.
3. `0018_staffing_database_guards`: PostgreSQL `btree_gist`, exclusion constraint, and appointment,
   history and frozen-snapshot triggers; SQLite development triggers. Schema/data steps are separate.

The expected Django content types and default permissions for the two new models are added by
normal `post_migrate`. No user, group membership, existing permission grant, role, center, source,
beneficiary counter, or historical relationship is modified.

Before any staffing writes, reversal removes only derived snapshots and untouched backfills,
then the added schema. Original rows reconcile exactly through forward, reverse, and replay.
After any explicit confirmation or backfill change, reverse preflight fails before removing the
installed database guards. It leaves the schema and history in place and fabricates no assignments.
Database updates stamp backfill changes so guard-bypassing closures cannot evade that preflight.
Do not force reversal or delete staffing history to make an older release run. After new writes,
retain the schema and review application compatibility, or use a separately authorized verified
pre-release backup with an explicit plan for preserving intervening writes. The extension remains
installed on reversal to avoid removing an extension potentially shared by other constraints.

## Verification and next chat

Final exact results are recorded below after the complete runs. Tests cover creation without a
lead, optional/helper duplication, extra lead/helper rows, forged inputs, center and deactivation
scope, future/expired periods, two services and later enrollment, reassignment, transfers, exits,
continuity versus business-date edits, historical authorship, restricted fields/files, PostgreSQL
service and raw-writer races, and migration fixtures for unique, joint, conflicting, unknown,
unassigned, exited, inactive, and unique-helper cases. Migration fixtures compare every original
row across all historical models, including relationship tables and restricted evidence.

For the next chat: read this handoff, the earlier enrollment handoff, `AGENTS.md`, permission matrix,
and Git status. Preserve all uncommitted work. No production release is authorized by this request.
Any release planning must account for the real migration-date 90-day bridge deadline, manager
resolution of ambiguous cases, the `btree_gist` prerequisite, guarded rollback after new writes,
and the preserved `0015` rollback rule for nullable legacy enrollment identifiers. No supplied
source files or production exports were copied into this repository or a developer database.

The following intake chat should implement the complete company health, social support, consent,
and initial care specification supplied for Chat 4. The original staffing chat received trailing
Chat 4 text that stopped at "English rendering:". Use the complete original
`04-bilingual-beneficiary-intake.md` prompt instead of that partial text. Health and social support access must use the
confirmed current lead/helper responsibility together with authorized enrollment placement and
active account/staff/center membership. Consent and signatures remain manager/coordinator-only.
Preserve all existing restricted contact, guardian, identity, address, source, and file controls.
No intake sections or intake permission expansion were implemented in this staffing task.

### Original Chat 3 results, before audit repairs

- Complete SQLite suite: **396 passed, 6 PostgreSQL-only skips in 116.25 seconds**.
- Complete disposable PostgreSQL 16 suite: **402 passed, no skips, in 200.72 seconds**.
  It includes all **48** assignment/staffing/migration tests, service and raw-writer races,
  the shared casework/staffing lock race, deferred saves, actor deactivation, attachment upload
  and delete races, return-transfer bridge denial, and full original-row reconciliation.
- Focused PostgreSQL assignment/staffing/migration run before the final two attachment cases:
  **46 passed in 38.52 seconds**. The final complete run includes those two added cases.
- Final focused SQLite run: **44 passed, 4 PostgreSQL-only skips in 22.04 seconds**.
- Ruff lint passed; Ruff formatting check reported **138 files already formatted**.
- Django system checks and deployment checks with `--fail-level WARNING` passed with no issues.
- `makemigrations --check --dry-run` reported no changes. Fresh migrations and `migrate --check`
  passed on both a temporary SQLite database and a separate empty synthetic PostgreSQL database.
- Synthetic demo seeding and its idempotent rerun produced three people and three staffing pairs
  on a separate temporary SQLite database. That database was removed after verification.
- Georgian catalog compilation and `msgfmt --check --check-format` passed; `git diff --check`
  passed. All added tracked lines and untracked files were checked for em dashes and passed.
- UI verification uses English/Georgian server-rendered test-client pages and form/permission
  tests. An interactive browser accessibility/layout session was not performed in this chat.
- SQLite cannot verify PostgreSQL locking or the PostgreSQL raw-delete history guard. The
  concurrent write and raw-delete cases passed on PostgreSQL. Staffing dates have day precision:
  existing same-day responsibility is preserved by requiring a later replacement date where
  necessary. The compatibility deadline is 90 days from the actual migration run and must be
  communicated to managers before any separately authorized production release. Production
  migration timing, extension permissions, and real-case reconciliation were not tested.
- The disposable PostgreSQL container and temporary verification databases were removed after
  verification. The pre-existing developer database was not migrated or seeded.
- Existing contact and enrollment work and automatic beneficiary codes remain preserved and
  uncommitted. No deployment, SSH, push, or production access occurred.

## Audited Chat 3 repairs, 2026-10-08

Both audited defects are fixed locally. The checkout is ready for the **complete Chat 4 intake
prompt**. Intake and signing are still unimplemented. The separate owner decision on the exact
90-day compatibility deadline remains required before deployment and does not block Chat 4.

Changed files in this repair:

- `apps/casework/forms.py`: `BeneficiaryStaffingForm.add_service_error` maps model `valid_from`
  and `valid_to` errors to `effective_date`, keeps real form-field errors on their fields, and
  safely attaches unknown keys and plain errors to non-field errors. It preserves the original
  translated validation messages, error objects, and submitted values.
- `apps/casework/views.py`: both staffing update and beneficiary creation use that adapter after
  leaving the failed transaction. Historical responsibility checks and the service are unchanged.
- `apps/casework/staffing.py`: responsibility rows batch effective pairs, effective placements,
  eligible center memberships, and legacy assignments authorized by the existing frozen-grant
  and historical-continuity SQL predicate. Row construction performs no database queries.
  Lists and QuerySets remain supported. Authorization data is freshly loaded on every call,
  including calls that reuse prefetched enrollment instances. No persistent access cache is added.
- `tests/test_staffing_regressions.py`: 23 maintained regression cases for bilingual endpoint
  errors, valid replacements, full creation rollback including beneficiary counters, closure
  rollback after insertion failure, query bounds, selected workspace enrollment, caseload filters,
  lead/helper permissions, deactivation, transfer and return boundaries, expiry, historical
  continuity, uncaptured evidence, and denial of revived legacy access after confirmed staffing.
- This handoff: repair evidence and the pending owner policy decision.

The two date-error endpoints now return HTTP 200 with an error on the submitted effective date.
Staffing periods, original assignments, and visits remain unchanged after rejection, and no
successful staffing audit event is created. A next-day replacement still succeeds and creates
exactly one success event. Tests also force a failure after a valid closure and after a complete
beneficiary creation to verify that the surrounding transactions roll back all writes.
The closure regression advances the test business date after creating a confirmed period,
then records a visit on that date; it does not disable database guards.

### Query measurements

Every cell below is **one beneficiary / ten beneficiaries**, measured outside fixture creation,
login, and session setup. Before counts were reproduced before editing application code.
After counts match on SQLite and PostgreSQL. The manager measurements use freshly loaded users
so both dataset sizes include the same role lookup cost.

| Team | Manager assignment selector, before to after | Responsibility rows from list, before to after | Workspace builder, before to after | Filtered caseload HTTP page, before to after |
|---|---|---|---|---|
| Confirmed lead | 12/39 to 12/12 | 3/30 to 3/3 | 3/30 to 3/3 | 20/47 to 20/20 |
| Confirmed lead and helper | 14/59 to 12/12 | 5/50 to 3/3 | 5/50 to 3/3 | 22/67 to 20/20 |
| Unresolved joint legacy team | 15/69 to 13/13 | 6/60 to 4/4 | 6/60 to 4/4 | 23/77 to 21/21 |

The workspace-builder measurements use scoped empty visit, assessment, and plan QuerySets to
isolate staffing queries. A separate rendered beneficiary workspace test verifies lead/helper
identities, selected enrollment, restricted scope, and denial of another center's enrollment.
Caseload tests cover specialist, service, status, name, and employee-number filters. Specialist
assignment-selector measurements are also bounded: confirmed lead **15/15**, confirmed helper
**15/15**, and unresolved legacy team member **16/16**. Returned identities, roles, confirmation
state, enrollment scope, and both specialists' ordinary permissions are asserted.

The exact external audit fixture also passes: **11/38 before, 11/11 after** for its confirmed
lead selector, and the same-day staffing response changes from HTTP 500 to HTTP 200. Its cached
manager role explains the one-query difference from the maintained fresh-user measurements.

### Final repair verification

- New maintained regressions on SQLite: **23 passed in 13.03 seconds**.
- Complete SQLite suite: **419 passed, 6 PostgreSQL-only skips in 132.44 seconds**.
- Complete disposable PostgreSQL 16 suite: **425 passed, no skips in 230.21 seconds**.
  This includes all **71** staffing, assignment authorization, staffing migration, and new
  regression cases, plus beneficiary-code locking and advisory-lock checks. Service races,
  raw-writer races, shared casework locks, history guards, and migration reconciliation passed.
- Original external audit reproductions: **2 passed in 4.99 seconds**, including 11/11 queries.
- Ruff lint passed; Ruff format check reported **139 files already formatted**.
- Django system checks passed with no issues. Deployment checks with `--fail-level WARNING`
  passed using synthetic local configuration only.
- `makemigrations --check --dry-run` reported no changes. Fresh full migration application and
  `migrate --check` passed on a temporary SQLite database and on the separate empty synthetic
  PostgreSQL database, apart from the test database used by pytest.
- `git diff --check` passed. Repair files contain no em dashes. Hashes captured before work
  confirm that every other pre-existing changed file is preserved, including all migrations
  and the unchanged 90-day backfill policy. Only the four listed existing files were edited,
  and the maintained regression test file was added. All work remains uncommitted on
  `codex/center-beneficiary-codes`.
- Verification uses test-client HTML responses. Interactive browser layout and accessibility
  checks remain part of the final intake/signature integration review.
- Temporary verification databases and the dedicated disposable PostgreSQL container were
  removed after verification. No deployment, push, SSH, production access, or Chat 4 implementation
  occurred. No real beneficiary data was used.
