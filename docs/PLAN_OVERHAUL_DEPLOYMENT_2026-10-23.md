# Plan overhaul deployment on 2026-10-23

The owner explicitly authorized deployment and a GitHub push. The Individual and Early
intervention plan flow is live at `https://0ufkrzj.cserverhost.cloud`. Both kinds currently
share the selectable care-activity table, Barthel display, and beneficiary or representative
signing flow described in `PLAN_OVERHAUL_2026-10-23.md`.

- Application commit: `dc3480753470cac2e66e0d480f35bcce9ed30f18`.
- Previous application commit: `1f8f925d32bbb1aeb8341cda45cb0803927fa38d`.
- Running image: `ssk-web:plans-20261023`, also tagged `ssk-web:latest`.
- Running image ID: `sha256:2a3e4ec9dcc7ad63c98fc0872fe5bf07c70a9abb2974a99d99f11786d653ab64`.
- Retained previous image: `ssk-web:before-plans-20261023`.
- Previous image ID: `sha256:5bfbeccaa54073ed51e4dbc1e3ea97e97214cbff0cc509dcdee3331a9cacb8ed`.
- Migrations 0026 and 0027 applied successfully, with no pending migrations.
- GitHub `main` and `codex/plan-overhaul-20261023` received the release through an atomic,
  fast-forward push. The VPS received the same commit through a code-only Git bundle.

Runtime dependencies were retained from the preceding image. Static assets were rebuilt,
and all tracked runtime file checksums match the application commit. The web container is
healthy with zero restarts. Its source checkout is clean at the application commit.

The actual candidate image passed the complete synthetic PostgreSQL suite: 675 tests with
no failures or skips. Candidate-image Ruff lint and format checks passed. Local verification
also passed the full SQLite suite with 662 tests and ten PostgreSQL-only skips, then the
final focused 43-test plan and view run. Django system and deployment checks, migration drift
checks, translation compilation, JavaScript syntax, and whitespace checks passed.

A restricted initial database backup restored successfully in an isolated PostgreSQL
container. Both migrations were rehearsed on that restore, including reversal to migration
0025 and reapplication. All 2,810 original rows across 66 tables remained unchanged. Candidate
checks passed 234 bilingual plan/beneficiary/authorization checks and 760 name-first enrollment
options, plus 145 assessment checks and 1,140 assessment enrollment options.

Web writes were stopped for the final database and private-file backups, final restore
rehearsal, production migrations, and record reconciliation. The final database backup
restored and migrated successfully in isolation. Reconciliation again preserved every original
field of all 2,810 rows. The only additions to original system tables were two migration rows,
one content type, four permissions, and normal audit events from authorized reads.

The running image passed the same runtime plan checks. Public HTTPS verification passed 262
bilingual plan/beneficiary/authorization/static-asset checks and 760 enrollment options, plus
161 assessment checks and 1,140 assessment enrollment options. The checks covered both plan
kinds, date/status fields, the three review frequencies, all 31 activities including the four
Technical choices, Barthel previews, beneficiary-page sections, cross-center denial, anonymous
redirects, hashed assets, and health. Both public health endpoints also returned successfully
from the desktop.

No production plan, signature, beneficiary, assessment, or account was fabricated or edited
for verification. Existing beneficiaries, enrollments, counters, plans, and the administrator
login timestamp remained unchanged during the read-only checks. Temporary verification
sessions were deleted. Original private files, private configuration, Nginx configuration,
and TLS contents and permissions were verified unchanged. No credential, role, SSH, sudo,
or firewall configuration was changed.

Restricted recovery artifacts remain under
`/home/sskadmin/ssk-private-releases/plans-20261023/`. The directory uses mode 700 and its
files use mode 600. Initial/final database dumps, archive catalogs, final private-file backup,
checksums, original-row digests, verification scripts/logs, and the previous image are retained.
Backup checksums were reverified after cleanup.

The isolated test/restore databases, their container and anonymous volume, internal network,
disposable test image, temporary source export, and transferred bundle were removed. No
production export or source document was copied to the desktop.

Recovery must preserve plans and signing evidence created after deployment. The migrations
refuse reversals that would discard new plan evidence. Prefer a forward repair after new
casework exists, and do not restore a pre-release database over subsequent casework. The
successful rollback rehearsal used the isolated pre-release dataset only.
