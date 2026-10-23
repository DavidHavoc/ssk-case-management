# Repository instructions

- Never use em dashes.
- Do not add real beneficiary data, credentials, or production exports to the repository.
- Keep authorization checks in server-side selectors, forms, and views.
- Run tests, Ruff, Django checks, and migration checks before handoff.

## Approved beneficiary import

On 2026-09-16 the owner confirmed that the hosted website is ready for real data and
explicitly requested updating this previously outdated staging record. This owner
confirmation supersedes the previous staging-only prohibition for the approved import.

- Import the supplied beneficiary workbook into `SSK-GOR-HC`,
  `სსკს- გორის შინმოვლის ცენტრი`.
- Model home care and food delivery as separate services for the same person.
- Import every person, preserve uncertain source values in restricted review information,
  and leave invalid or unclear operational fields unset.
- Link only uniquely matching existing active specialist accounts at that center.
- Keep source workbooks out of Git and developer databases. Use restricted temporary
  storage on the destination and remove transferred source files after verification.
- Do not run `seed_demo_data` on the hosted database.

## Current VPS status

Technical checks below were refreshed on 2026-09-16. Hosting readiness is owner-confirmed;
this is not a claim that every organizational or external control was independently audited.

- The IONOS VPS runs Ubuntu 24.04.4 LTS with 4 GB RAM and a 120 GB disk. It had approximately 112 GB free after deployment checks.
- From this desktop host, SSH works through the `ssk-production` host alias as the `sskadmin` user. Do not request, reveal, copy, or modify SSH private keys or passwords.
- The application is available at `https://0ufkrzj.cserverhost.cloud`. The provider hostname remains in use; an organization-controlled domain was not verified during this import task.
- Docker Engine and Compose are installed. The application runs from `/opt/ssk-case-management` with Nginx, Django and Gunicorn, and PostgreSQL 16. PostgreSQL and Gunicorn have no public host ports.
- The live application code was deployed from commit `bffba62497183813af2b29630d9ce8326b0637b4`. Import changes were committed on the local `codex/beneficiary-workbook-import` branch and delivered to the VPS through code-only Git bundles. No GitHub push was performed during this task. The VPS repository origin is `https://github.com/DavidHavoc/ssk-case-management.git`.
- Root SSH login, SSH password authentication, interactive authentication, and SSH forwarding are disabled. UFW allows SSH only from the administrator address used during deployment and allows public HTTP and HTTPS.
- The PostgreSQL database has one active superuser named `admin`, four active centers (`TEST`, `SSK-GOR-EIC`, `SSK-LAG-IEC`, and `SSK-GOR-HC`), 21 staff profiles, and 16 specialists, including five at `SSK-GOR-HC`.
- The approved workbook import completed on 2026-09-16. `SSK-GOR-HC` has 114 beneficiaries (98 active, 16 exited), 100 home-care enrollments, 28 food-delivery enrollments, and 132 specialist assignments, including jointly responsible specialists. All source values, normalized fields, services, specialist identities, statuses, and review flags were reconciled successfully. No visits or assessments were fabricated.
- Eighteen imported people have source review flags: six application numbers stored as dates, one future birth date, five personal IDs of unexpected length, and eight unknown exit dates. Counts overlap. Their original values are retained in the restricted source section, and uncertain operational fields are unset.
- `SSK-GOR-HC` now explicitly offers `HOME-CARE` and `FOOD-DELIVERY`. Their effective start dates cover the imported historical enrollments. Other centers and staff roles were not changed by the import.
- A System Manager can view, add, update, activate, and deactivate the active center's service offerings from the center detail page. New centers intentionally start without offerings, and services must be selected explicitly.
- The certificate-renewal service and timer passed a staging renewal test in September 2026. Current operational contact email configuration was not reverified.
- A restricted pre-import database backup and a restore rehearsal into an isolated temporary PostgreSQL container passed on 2026-09-16. The rollback image was retained. The full synthetic PostgreSQL suite passed 218 tests; after the jointly responsible specialist refinement, all 19 importer tests passed on PostgreSQL. Final local verification passed 219 tests with one PostgreSQL-only skip, Ruff, Django deployment checks, and migration checks. The public HTTPS health endpoint responded successfully after deployment.
- The owner's readiness confirmation is recorded above. Current encrypted off-host backups, retention, backup monitoring, external alerting, provider firewall, and organizational signoffs were not independently reverified during this task; the earlier September 4 statements about their absence must not be treated as current verified facts.
- SSH and Docker access as `sskadmin` were verified after the owner fixed repository access and added the account to the Docker group. Keep private configuration, backups, and source workbooks restricted when repairing application code file permissions.
- The temporary passwordless-sudo deployment rule was removed after deployment. Do not recreate it unless the user explicitly authorizes temporary remote administrator access.

## Approved early intervention PDF import

On 2026-09-26 the owner requested importing the supplied PDF into the existing Gori
early intervention center, confirmed the reporting period is September 2026 despite
the historical 2017 form heading, and confirmed all 43 listed children are currently active.

- `SSK-GOR-EIC`, `სსკ-ს გორის ადრეული ინტერვენციის ცენტრი`, now has 43 active beneficiaries
  and 43 `EARLY-INTERVENTION` enrollments. Its Early Intervention offering and current
  center placements begin on the confirmed snapshot date, 2026-09-26.
- Historical enrollment and first-service dates remain unset. No visits, assessments,
  schedules, coded diagnoses, or specialist assignments were inferred from monthly totals.
  Responsible specialists must be supplied separately before granting specialist access.
- Names, text personal IDs including leading zeros, birth dates, and available guardian
  names were reconciled. Representative IDs, the original heading, September 2026 period,
  and reported service counts are retained in the existing restricted source section.
- The source reports 257 services: 196 individual and 61 group. Location subtotals report
  176 at home and 65 at the center. Nine location-total discrepancies and one missing
  guardian entry are flagged. All 43 unknown historical start dates are also flagged.
- All imported fields, original source values, statuses, and review flags reconciled on
  the hosted database. The Georgian beneficiary detail page and public HTTPS health check
  passed. A checksum confirmed the existing home-care records were unchanged.
- The deployed application code is commit `b2b2abd3cf202eb1c95f84b7dea7bd58420664a7`, delivered
  through a code-only Git bundle. No GitHub push was performed.
- A restricted pre-import database backup restored successfully in an isolated temporary
  PostgreSQL container. The backup and previous running image were retained on the VPS.
- Local verification passed 237 tests with one PostgreSQL-only skip, Ruff, Django checks,
  and migration checks. The synthetic PostgreSQL run passed 236 tests; the two remaining
  deployment-file checks passed after their repository fixtures were added to the disposable
  test image. All seven deployment tests then passed. Production deployment checks passed,
  with no pending migrations. Temporary test containers and their database were removed.
- A repeated hosted import skipped all 43 records and created no duplicates. The transferred
  reviewed JSON and temporary local extraction files were removed after verification;
  the owner's original PDF remains in Downloads and was never added to Git or a developer database.

## Approved Lagodekhi early intervention DOCX import

On 2026-09-27 the owner requested importing the supplied Form N2.2.1 DOCX register into
the existing Lagodekhi center. The document explicitly covers June 2026, the owner confirmed
the year and all 19 people as currently active, and confirmed the adult birth date as supplied.

- `SSK-LAG-IEC`, `სსკ-ს ლაგოდეხის ადრეული ინტერვენციის ცენტრი`, now has 19 active
  beneficiaries and 19 `EARLY-INTERVENTION` enrollments. Its new Early Intervention offering,
  current placements, and active snapshot state begin on 2026-09-27.
- Names, personal IDs including leading zeros, valid birth dates, guardian names, and voucher
  numbers were reconciled. Whitespace is removed from operational IDs and voucher numbers only.
  Guardian IDs, the original heading, reporting period, service types, counts, locations,
  supervision entries, and original source values remain in restricted evidence.
- The source contains 38 service lines reporting 152 services. These remain reported evidence;
  no visits, assessments, plans, schedules, diagnoses, or specialist assignments were inferred.
  Historical enrollment and first-service dates remain unset for all 19 people. One confirmed
  adult birth date and one repeated individual-service type remain flagged for review.
  Responsible specialists must be supplied separately before granting specialist access.
- Every imported normalized field, source value, enrollment, placement, state event, and review
  flag reconciled. Aggregate checks verified all 1,872 original rows across 53 models unchanged,
  excluding only the administrator's login timestamp from authentication-page checks.
  This includes the existing Gori beneficiary records, centers, staff, and service catalog.
- A repeated hosted import skipped all 19 rows and created no duplicates. The Georgian detail
  page returned successfully, restricted source information was visible to an authorized manager,
  cross-center detail access was denied, anonymous access redirected to login, and public HTTPS
  health passed.
- Application code commit `c694ab1e433f29bc6b9e944453463a98ab70aea8` was deployed through a
  code-only Git bundle. No GitHub push was performed. The pre-import database and private-file
  backup and previous running image were retained on the VPS. The database backup restored
  successfully in an isolated temporary PostgreSQL container.
- Local verification passed 308 tests with one PostgreSQL-only skip, Ruff, Django checks,
  and migration checks. The complete synthetic PostgreSQL run passed all 309 tests with no
  skips. Production deployment checks passed, with no pending migrations.
- The owner explicitly authorized setting only the nine changed code, test, translation,
  and documentation files to mode 644 after restrictive release-file creation caused permission
  errors. Private configuration, backups, and source files stayed restricted. No sudo rule,
  SSH credential, account role, or firewall setting was changed.
- Temporary test databases, containers, and the test image were removed. Transferred reviewed
  JSON and temporary local extraction files were removed after verification. The original DOCX
  remains in Downloads and was never added to Git or a developer database.

## Approved center beneficiary code deployment

On 2026-10-08 the owner confirmed numbering existing beneficiaries in registration/import
order and explicitly approved deploying the automatic center sequences to the live website.

- Application code commit `80394a9048edeedbdca0388f132616290a0076a3` was deployed through a
  code-only Git bundle. No GitHub push was performed. Runtime dependencies were retained from
  the previous running image.
- All 176 beneficiaries were numbered within their original center: 114 at `SSK-GOR-HC`,
  43 at `SSK-GOR-EIC`, and 19 at `SSK-LAG-IEC`. The next codes are `SSK-GOR-HC_B115`,
  `SSK-GOR-EIC_B044`, and `SSK-LAG-IEC_B020`. Empty centers begin at `B001` when first used.
- New beneficiary codes are assigned automatically when saved. Each center has a persistent
  counter serialized by a center row lock. Deleted numbers are not reused, and codes remain
  stable through person edits, center code changes, and enrollment transfers.
- Existing codes remain preserved and searchable. Reconciliation verified all 2,288 original
  rows across 58 models, including automatic relationship tables, with only the requested
  beneficiary code changes. The new sequence model's Django content type and four permissions
  were the only expected additions to existing system tables. Case relationships, enrollment
  codes, imported evidence, staff roles, and account fields were preserved.
- Restricted database and private-file backups and the previous running image were retained
  on the VPS. A pre-release database backup restored all 176 beneficiaries successfully in an
  isolated temporary PostgreSQL container. A final backup was taken while web writes were stopped.
- The complete synthetic PostgreSQL suite passed 323 tests. Local verification passed 321
  tests with two PostgreSQL-only skips, Ruff, Django deployment checks, and migration checks.
  Schema and data migrations are separate so PostgreSQL rollback also passes verification.
- Hosted Georgian detail pages, previous-code searches, the automatic code field, anonymous
  redirects, cross-center denial, and public HTTPS health passed. The temporary verification
  session and isolated restore container were removed. No production test beneficiaries were created.
- Changed code, test, documentation, and translation files were made readable for deployment.
  Existing private configuration, backups, SSH credentials, sudo rules, and firewall settings
  were not changed. No source workbook or production export was transferred to this desktop.

## Approved integrated company release deployment

On 2026-10-09 the owner explicitly authorized deploying the completed company changes.
The complete release is live; details are recorded in
`docs/COMPANY_RELEASE_DEPLOYMENT_2026-10-09.md`.

- Application commit `32ffd19192baa815f92a4f7851ad60d20365f521` was delivered through a code-only
  Git bundle. No GitHub push occurred. Migrations 0014 through 0022 applied successfully.
- The complete local synthetic PostgreSQL suite passed all 593 tests. Candidate-image targeted
  regressions and all seven deployment tests passed after a missing disposable test fixture was
  supplied. Ruff, Django deployment checks, catalog checks, and migration checks passed.
- Restricted initial/final database and private-file backups remain under
  `/home/sskadmin/ssk-backups/company-20261009/`. Both restored successfully in isolation and
  reconciled all original rows. The previous image remains as `ssk-web:before-company-20261009`.
- All 2,340 original rows across 60 tables remained unchanged, including all 176 beneficiaries,
  imported evidence, codes/counters, enrollment histories, assignments, memberships and roles.
  No production intake, consent, signature, clinical record, or test beneficiary was fabricated.
- The owner's deployment-day legacy expiry policy is active. Migration 0017 confirmed 96 safe
  teams and preserved 108 expired source snapshots. All 64 ongoing unresolved cases are visible
  in manager review reports: two Gori home-care cases, 43 Gori early-intervention cases, and 19
  Lagodekhi early-intervention cases. Managers must confirm the lead/helper pair before specialist work.
- Public HTTPS verification passed 176 checks across both languages, authorization boundaries,
  consent review/printable pages and hashed static assets. Existing mandatory first-password
  changes remained enforced. Completed signing/download was verified with synthetic PostgreSQL
  data; production has no signed documents and no signature was fabricated for verification.
- Temporary restore/test resources and verification sessions were removed. Private-file modes,
  credentials and infrastructure configuration stayed unchanged. No production exports were
  copied to the desktop and `seed_demo_data` was not run on the hosted database.

## Production language-switching hotfix

On 2026-10-09 a reported production language-switching bug was repaired and deployed.

- Application hotfix commit `a8d0208ebff4cc121e04b1204e4ab11966606128` was delivered through a
  code-only Git bundle. No GitHub push occurred. The running image is `ssk-web:language-20261009`,
  also tagged `ssk-web:latest`. The preceding company image remains as
  `ssk-web:before-language-20261009`.
- Switching now translates Django's validated return URL using its language prefix when the
  browser language or cookie differs from the page. Language switching is also allowed during
  mandatory password change, while casework remains blocked until the password is changed.
- Local verification passed 603 tests with nine PostgreSQL-only skips, 55 targeted synthetic
  PostgreSQL tests, Ruff lint/format checks, Django deployment checks, and migration checks.
  There are no new migrations. Candidate and running images each passed 19 runtime checks.
- Both switching directions passed public HTTPS verification, including translated page content.
  English and Georgian health endpoints passed. All three changed runtime files match the commit.
- This code-only hotfix did not write account or case records. Existing recovery backups and
  private configuration remain unchanged. The temporary synthetic PostgreSQL container and its
  database were removed; the transferred code bundle was removed after verification.

## Beneficiary creation form deployment

On 2026-10-09 the owner confirmed hiding the beneficiary code during creation, showing it after
saving, and explicitly requested deployment.

- Application commit `a90a1f4ef9c9bd0afa245ee06bf32e5cfa4b4712` was delivered through a code-only
  Git bundle without a GitHub push. The running image is `ssk-web:beneficiary-form-20261009`,
  also tagged `ssk-web:latest`. The preceding image remains as
  `ssk-web:before-beneficiary-form-20261009`.
- The creation form omits the code field. Saving still assigns the existing automatic center
  sequence; detail pages show the code, and edit forms show it as a disabled field. Existing
  codes and sequence counters remained unchanged. There are no migrations.
- All 64 targeted synthetic PostgreSQL tests passed. The targeted SQLite run passed 32 tests
  with one PostgreSQL-only skip. Ruff lint/format, Django deployment checks, and migration
  checks passed. Candidate and running images each passed 22 bilingual form checks and 19
  language/password-gate checks. All 32 public HTTPS checks passed, including both languages,
  saved code display, cross-center denial, anonymous redirects, and health endpoints.
- A restricted pre-release database dump and its archive catalog were verified under
  `/home/sskadmin/ssk-private-releases/beneficiary-form-20261009/`. The prior recovery artifacts
  remain retained. The deployed form file matches the committed file; the web container is
  healthy with zero restarts.
- No production beneficiaries were created and no account or beneficiary records were changed
  by verification. Authenticated reads generated normal audit events. The temporary verification
  session, local synthetic PostgreSQL container/database, and transferred bundle were removed.
  Private configuration, credentials, sudo rules, and infrastructure settings stayed unchanged.

## Assessment enrollment dropdown deployment

On 2026-10-14 the owner requested names before codes when creating a new assessment and
explicitly authorized deployment. Details are recorded in
`docs/ASSESSMENT_ENROLLMENT_LABEL_DEPLOYMENT_2026-10-14.md`.

- Application commit `4ed1938ccd7a4e9350114db9b6dbd6fc24edd656` was delivered through a code-only
  Git bundle without a GitHub push. The running image is `ssk-web:assessment-label-20261014`,
  also tagged `ssk-web:latest`. The preceding image remains as
  `ssk-web:before-assessment-label-20261014`.
- Assessment enrollment choices show name, beneficiary code, service, status, and enrollment
  date in that order. Existing UUID selection, authorization, and localization are preserved.
  There are no migrations. The deployed form file matches the application commit.
- Local verification passed 603 tests with nine PostgreSQL-only skips, Ruff lint/format,
  Django system/deployment checks, and migration checks. The candidate passed all 80 targeted
  synthetic PostgreSQL tests. Candidate and running images each passed 26 bilingual assessment
  checks, 22 beneficiary-form checks, and 19 language/password-gate checks.
- The public verification suite passed 36 checks, including bilingual creation pages,
  preselection, cross-center denial, anonymous redirects, and health. Both health endpoints
  also passed from the desktop. The web container is healthy with zero restarts.
- Restricted database and private-file backups remain under
  `/home/sskadmin/ssk-private-releases/assessment-label-20261014/`. Checksums and the database
  archive catalog passed, and the database restored successfully in isolation. Beneficiaries,
  enrollments, counters, and the administrator login timestamp stayed unchanged during checks.
- No production case or account record was fabricated or edited. The temporary verification
  session, isolated restore/test database and volume, network, test image, and transferred
  bundle were removed. Private configuration, credentials, roles, sudo rules, and infrastructure
  settings stayed unchanged. No production export was copied to the desktop.

## Barthel assessment deployment

On 2026-10-14 the owner supplied the scale, confirmed five dependency/care-need bands and
required beneficiary or representative signing, then explicitly authorized deployment.
Details are recorded in `docs/BARTHEL_ASSESSMENT_DEPLOYMENT_2026-10-14.md`.

- Application commit `82ba0c7c4c1ac7cf0b38aacf0eeb9eed6a4eaea5` was delivered through a code-only
  Git bundle without a GitHub push. The running image is `ssk-web:barthel-20261014`, also tagged
  `ssk-web:latest`. The preceding image remains as `ssk-web:before-barthel-20261014`.
- Assessment creation shows named templates without version numbers and beneficiary age/code.
  The built-in Georgian Barthel scale has ten required multiple-choice activities and automatic
  score, functional dependency, and care-need results. Additional care needs are recorded
  separately; the score does not automatically set home-care visit frequency or intensity.
- New assessments require a beneficiary or representative signature before completion.
  Signed documents/evidence are private and immutable, with fresh signing for corrections.
  Existing assessments remain unchanged and unsigned. Migrations 0023 through 0025 applied
  successfully, with no pending migrations.
- Local and candidate-image synthetic PostgreSQL suites each passed all 652 tests. Local SQLite
  verification passed 642 tests with ten PostgreSQL-only skips. Ruff lint/format, Django
  system/deployment checks, migration checks, JavaScript syntax, and translation checks passed.
- Candidate and running images each passed 145 bilingual assessment checks, 1,140 enrollment
  option checks, 22 beneficiary-form checks, and 19 language/password-gate checks. All 161 public
  HTTPS checks and both desktop health checks passed. The web container is healthy with zero restarts.
- Restricted initial/final database and private-file backups remain under
  `/home/sskadmin/ssk-private-releases/barthel-20261014/`. Checksums and archive catalogs passed,
  and both databases restored successfully in isolation. Every original field of all 2,756 rows
  across 65 tables was preserved. Original private files and their permissions match the final backup.
- No production assessment, signature, beneficiary, account, or case record was fabricated or
  edited for verification. Authorized reads generated normal audit events, and the temporary
  verification session was removed. Isolated test/restore databases, volume, network, test image,
  source export, and transferred bundle were removed. Private configuration/TLS contents and modes
  were verified unchanged; credentials, roles, sudo rules, and infrastructure settings stayed unchanged.
- Recovery must preserve casework created after deployment. Migration reversals refuse to discard
  new assessment or signing evidence; do not restore the pre-release database over subsequent casework.

## Assessment schedule count removal

On 2026-10-14 the owner requested removing “Service schedule count” from the deployed assessment
flow. Details are recorded in `docs/ASSESSMENT_SCHEDULE_COUNT_REMOVAL_2026-10-14.md`.

- Commit `1f8f925d32bbb1aeb8341cda45cb0803927fa38d` is deployed as
  `ssk-web:schedule-removal-20261014`, also tagged `ssk-web:latest`. The previous image is retained
  as `ssk-web:before-schedule-removal-20261014`. No GitHub push occurred.
- The count is excluded from assessment forms and new review/printable documents. Stored values
  and existing signed evidence remain preserved. There are no migrations or static-asset changes.
- Local targeted tests passed 87 tests with one PostgreSQL-only skip; the candidate passed all
  88 targeted synthetic PostgreSQL tests. Ruff, Django checks, and migration checks passed.
  Candidate/live bilingual checks and all 161 public HTTPS checks passed, including field-removal
  assertions. Both desktop health checks passed; the web container is healthy with zero restarts.
- Restricted recovery artifacts remain under
  `/home/sskadmin/ssk-private-releases/schedule-removal-20261014/`. The database backup restored
  successfully in isolation. All 2,800 original rows across 66 tables and original private files
  were preserved. No production case record or signature was fabricated for verification.
- Temporary sessions, test/restore databases, container/volume, network, test image, source export,
  and bundle were removed. Private configuration/TLS contents and modes were verified unchanged.
  No production export was copied to the desktop; credentials, roles and infrastructure were unchanged.


## Plan overhaul deployment

On 2026-10-23 the owner requested separate Individual and Early intervention plan kinds,
using the same care-activity logic for now, and explicitly authorized deployment and a
GitHub push. Details are recorded in `docs/PLAN_OVERHAUL_DEPLOYMENT_2026-10-23.md`.

- Application commit `dc3480753470cac2e66e0d480f35bcce9ed30f18` is deployed as
  `ssk-web:plans-20261023`, also tagged `ssk-web:latest`. The previous image remains as
  `ssk-web:before-plans-20261023`. GitHub main and `codex/plan-overhaul-20261023` received
  the release through an atomic fast-forward push; the VPS received a code-only bundle.
- New plans use the supplied activity table with at least one selected row, including the
  owner's four Technical choices. Beneficiary choices show names first. Barthel results and
  the existing five-band scale appear in plan review and beneficiary pages, and scores appear
  in plan tables. Missing assessments remain unrecorded. Dates and statuses are retained;
  new review choices are monthly, quarterly, and every six months.
- New plans remain drafts until the beneficiary or representative signs through the existing
  consent signature controls or signed-paper PDF alternative. Signed content/files are private
  and immutable, with separate status transitions. Each plan kind has independent active
  periods and version numbers. Existing plans, goals, and history are preserved.
- Migrations 0026 and 0027 applied successfully. The complete candidate-image synthetic
  PostgreSQL suite passed all 675 tests without skips. Local SQLite verification passed
  662 tests with ten PostgreSQL-only skips, and the final targeted run passed all 43 tests.
  Ruff, Django system/deployment checks, migration checks, translations and JavaScript passed.
- Initial and final restricted database backups restored successfully in isolation. Migration
  application, reversal and reapplication were rehearsed on the isolated initial restore.
  All 2,810 original rows across 66 tables were preserved. Expected additions to original system
  tables were two migration rows, one content type, four permissions, and normal audit reads.
- Candidate/live runtime checks passed 234 bilingual plan checks and 760 enrollment options.
  Public HTTPS passed 262 plan checks and 760 options, plus 161 assessment checks and 1,140
  assessment options. Both desktop health checks passed. The web container is healthy with
  zero restarts, and all tracked runtime hashes match the application commit.
- Recovery artifacts remain under `/home/sskadmin/ssk-private-releases/plans-20261023/` with
  directory mode 700 and files mode 600. Backups, original private files, private configuration,
  Nginx configuration, and TLS contents/modes were verified. Credentials, roles, SSH, sudo and
  firewall settings were unchanged. No production casework or signature was fabricated for
  verification, and temporary verification sessions were deleted.
- Temporary test/restore databases, container/volume, network, test image, source export and
  bundle were removed. No production export or source document was copied to the desktop.
  Recovery must preserve subsequent plan/signing evidence; migrations refuse to discard it.
  Do not restore a pre-release database over later casework.

## Plan picker and category outline follow-up

On 2026-10-23 the owner's follow-up to the authorized plan release was deployed.
See `docs/PLAN_PICKER_DEPLOYMENT_2026-10-23.md` for verification and recovery details.

- Application commit `81cdaa9c921bceead079d8696e6e204cf877e9dd` runs as
  `ssk-web:plan-picker-20261023`, also tagged latest. The prior image remains as
  `ssk-web:before-plan-picker-20261023`. There are no migrations or dependency changes.
- Plan enrollment choices include the authorized completed Barthel score when available,
  with zero preserved and intake-only values explicitly labeled. Each care category has
  one bold row-group label and a dark outline in forms and new review/printable documents.
- Local verification passed 669 tests with ten PostgreSQL-only skips. The candidate passed
  all 121 focused PostgreSQL tests. Ruff, Django system/deployment and migration checks passed.
  Public checks passed 294 plan checks and 760 options, plus 161 assessment checks and 1,140
  options. The container is healthy with zero restarts, and runtime hashes match the commit.
- The restricted backup restored successfully in isolation and preserved all 2,884 original
  rows across 67 tables. Recovery artifacts remain under
  `/home/sskadmin/ssk-private-releases/plan-picker-20261023/`. Existing private files and
  configuration/TLS contents and modes were unchanged. No production casework was fabricated.
  Temporary verification sessions and test resources were removed. No production export was
  copied to the desktop. GitHub main and the release branch received an atomic fast-forward push.
