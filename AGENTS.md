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
