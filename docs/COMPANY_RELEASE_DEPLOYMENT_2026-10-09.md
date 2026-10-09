# Company release deployment, 2026-10-09

The owner explicitly authorized this deployment. The complete integrated company release is
live at `https://0ufkrzj.cserverhost.cloud`.

The later language-switching hotfix below supersedes the running application revision and image
listed in the original release record. The company database migration and recovery records
remain applicable.

## Release identity

- Application commit: `32ffd19192baa815f92a4f7851ad60d20365f521`.
- Local release branch: `codex/company-release-20261009`.
- Previous VPS checkout: `b74d1b5e9b3d899d26ae5aebc7e7719eb2076ec6`.
- Running image: `ssk-web:company-20261009`, also tagged `ssk-web:latest`.
- Running image ID: `sha256:7cb51f143935e93c8778de38d868c5328382b1cda8ef1715af0e7edcb83f0574`.
- Retained previous image: `ssk-web:before-company-20261009`.
- Previous image ID: `sha256:02c954d08f3c9b7a0377133f40836d4562cdd6396a7473771f2e383e17c279bf`.

All 98 reviewed release files were committed and delivered through a code-only Git bundle using
`ssk-production`. No GitHub push occurred. The running container's 61 changed runtime files match
the release commit byte for byte. A trailing space in the bundled font license was removed before
the final commit; its full wording and the original font bytes are preserved.

The candidate retained the preceding image's runtime dependencies and added Pillow 12.3.0.
The running application uses Python 3.12.14 and Django 5.2.17. Static collection includes the
signing script, CSS, Georgian catalog, font, and full font license.

## Verification and migrations

- Fresh complete local synthetic PostgreSQL suite: 593 passed, no skips, in 359.69 seconds.
- Ruff lint and format checks passed; 152 Python files were formatted.
- Django checks, migration drift checks, catalog validation, and full release whitespace checks
  passed. The preceding integrated review also recorded 584 SQLite passes and nine PostgreSQL-only
  skips; its final logs were inspected.
- A separate empty synthetic PostgreSQL database passed forward migration through 0022, reversal
  to 0013, full replay, migration checks, and production-settings deployment checks.
- The actual candidate image passed 170 targeted PostgreSQL regressions. One deployment test
  initially lacked its Nginx fixture in the disposable test image. After adding that fixture,
  all seven deployment tests passed. The missing fixture did not affect the application image.
- An isolated VPS restore passed candidate forward migration, original-row reconciliation,
  reversal to 0013 with the old image, and complete replay. The final stopped-write backup also
  restored independently and reconciled exactly with the old image before live migration.
- Production migrations 0014 through 0022 all applied successfully. The running release passed
  `check --deploy --fail-level WARNING`, `makemigrations --check --dry-run`, and `migrate --check`.

Web and proxy writes were stopped for the final consistent backup, restoration rehearsal,
migrations, reconciliation, and internal smoke checks. Public access reopened after the new
container became healthy. A first HTTPS probe raced the proxy startup; its retry and all later
health probes succeeded. Deployment completed without rollback.

## Preserved records and authorization

All 2,340 original rows across 60 database tables reconciled unchanged against the final
stopped-write snapshot, including automatic relationship tables. Beneficiary codes and aliases,
enrollment IDs and dates, counters, imported source evidence, original assignments, histories,
staff memberships, roles, account fields, and prior audit/session rows are preserved.

The release added five model content types, 20 default permissions, and nine migration records.
Read-only deployment smoke checks also added normal audit events. Temporary verification sessions
were removed without updating account login timestamps. No intake, consent, signature, visit,
assessment, schedule, or plan was fabricated.

Final reconciliation after public checks preserved every original row and recorded 122 expected
new read/denial audit events. The web container was healthy with zero restarts and no HTTP server
failures. Unsolicited requests using the raw server IP were rejected by the existing host policy.

The 176 beneficiaries remain in their original centers: 114 at `SSK-GOR-HC`, 43 at `SSK-GOR-EIC`,
and 19 at `SSK-LAG-IEC`. Next beneficiary numbers remain 115, 44, and 20 respectively.

Migration 0017 confirmed 96 unambiguous person-wide teams and preserved 108 legacy evidence
snapshots with deployment-day expiry. No legacy snapshot grants current access. All 64 ongoing
unresolved cases appear in the manager data-quality report: two in Gori home care, 43 in Gori
early intervention, and 19 in Lagodekhi early intervention. Managers/coordinators must explicitly
confirm one lead and an optional helper before specialist work on those cases. Source roles,
joint assignments, unknown dates, and original review information remain unchanged.

The restored and live database each passed 155 internal read-only workflow checks. The public
HTTPS pass completed 176 checks, covering Georgian/English manager workflows, exact enrollment
selection, automatic code fields, intake/staffing/review/printable pages, reports/reminders,
cross-center and malformed-ID denials, anonymous redirects, CSRF refusal, missing-document denial,
and exact hashed JS/CSS/font delivery. Both language health and login endpoints also passed from
the desktop; HTTP redirects to HTTPS.

Three coordinator scopes and 15 specialist scopes were checked. Eighteen existing staff scopes
still require the mandatory first password change, and that gate remained enforced. Confirmed
specialist capabilities were verified through the live selectors. Specialist editing, completed
bilingual signing, original private HTML download, immutable PNG/snapshots, retry/concurrency,
and signed-document denials passed the synthetic PostgreSQL workflows. There are no production
signed documents to download, and no production signing record was created for testing.

The actual application user can read and write the private-storage directory. Its original
ownership and modes are preserved. The current private-file volume is empty; both backup archives
restored its directory metadata exactly. Physical finger/stylus input and printer output retain
the device-review limits recorded in the integrated handoff.

## Retained recovery artifacts and cleanup

Restricted backups remain on the VPS, outside Git:

- `/home/sskadmin/ssk-backups/company-20261009/initial/`
- `/home/sskadmin/ssk-backups/company-20261009/final/`

Each contains the database dump, private-media archive, checksum manifest, destination-only row
fingerprints, private-file inventory, and previous release/configuration records. Directories use
mode 700 and backup files use mode 600. Checksums and both restorations passed. The final directory
also retains `staffing-review.json` for restricted operational review. Verification/build logs and
the guarded rollback procedure remain under
`/home/sskadmin/ssk-private-releases/company-20261009/`.

The previous running image remains available. The pre-open rollback procedure preserves failed
state, restores database/private files together, reconciles original rows, and starts the previous
image. Its database restoration and old-image compatibility were rehearsed in isolation. The
script refuses to run after public access has reopened. Any later recovery must preserve and
reconcile post-release writes and follow the migration reversal limits in the integrated handoff.

Temporary VPS restore/test containers, restore private-media volume, isolated network, disposable
test image, local synthetic PostgreSQL container, verification sessions, and transferred bundle
were removed. Restricted backup archives and the previous image were retained. No production
export, source workbook, password, or private key was copied to the desktop. Private configuration,
Compose/Nginx configuration, SSH credentials, account roles, sudo rules, and firewall settings
were preserved. `seed_demo_data` was not run on the hosted database.

## Subsequent language-switching hotfix

The production language selector saved its cookie but could redirect to the old language's URL
when the page prefix differed from the cookie or browser preference. The mandatory password-change
middleware also prevented the selector from running for accounts awaiting their first change.

Hotfix commit `a8d0208ebff4cc121e04b1204e4ab11966606128` fixes the return URL after Django validates
the language and redirect destination, and permits the language endpoint through the password gate.
CSRF enforcement, safe redirect validation, and the casework password gate remain enforced. Current
page filters, fragments, and active center selection are preserved.

The hotfix was delivered through a code-only Git bundle without a GitHub push. It changes three
runtime files and adds 19 regression cases. The image retains the company release's dependencies,
static assets, and other application files. There are no schema or data migrations and no account
or case records were written during deployment or verification.

- Running image: `ssk-web:language-20261009`, also tagged `ssk-web:latest`.
- Running image ID: `sha256:4c4b830d7528c4c8cbee5816a891fc590ddb10c9753b7d0d491b2e3ea053ae52`.
- Previous image: `ssk-web:before-language-20261009`, retaining the original company release.
- Complete SQLite suite: 603 passed, nine PostgreSQL-only skips.
- Targeted synthetic PostgreSQL suite: 55 passed, including language, UI, staff access,
  deployment, and authorization tests.
- Ruff lint/format, Django deployment checks, migration drift checks, and applied-migration
  checks passed. Candidate and running images each passed 19 runtime language/password-gate checks.
- Public HTTPS language POSTs passed in both directions and returned translated HTML and
  `Content-Language` headers. Both language health endpoints passed. The three runtime source
  files match the deployed commit byte for byte; the web container is healthy with zero restarts.

The disposable local synthetic PostgreSQL container/database and transferred code bundle were
removed after verification. Existing production backups, private files, credentials, and
infrastructure configuration remain unchanged. The restricted build and verification scripts
remain under `/home/sskadmin/ssk-private-releases/language-20261009/`.
