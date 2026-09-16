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
