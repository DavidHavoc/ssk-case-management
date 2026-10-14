# Assessment enrollment dropdown deployment, 2026-10-14

The owner requested beneficiary names before codes when creating a new assessment and
explicitly authorized deployment. The update is live at
`https://0ufkrzj.cserverhost.cloud`.

Enrollment options now display `Name | Beneficiary code | Service | Status | Enrollment date`.
The same field is used when editing an assessment. Existing enrollment UUIDs, server-side
authorization, localized service/status labels, and unknown-date handling are preserved.
Related beneficiary and service records are loaded together for saved-assessment choices.

## Release and verification

- Application commit: `4ed1938ccd7a4e9350114db9b6dbd6fc24edd656`.
- Previous application commit: `a90a1f4ef9c9bd0afa245ee06bf32e5cfa4b4712`.
- Running image: `ssk-web:assessment-label-20261014`, also tagged `ssk-web:latest`.
- Running image ID: `sha256:09063f44ee851307e27154e49f13a52d594904c63fd2c4441bd6944e0d9580b1`.
- Retained rollback image: `ssk-web:before-assessment-label-20261014`.
- Previous image ID: `sha256:9bb65ab2bb820737ff2d3d806a9eca2cdf8c03537e27b247fb6be00094617647`.

The committed update was delivered through a code-only Git bundle without a GitHub push.
Only `apps/casework/forms.py` changed in the runtime image. Dependencies, static assets,
and infrastructure configuration were retained. The deployed file matches the committed
SHA-256 checksum. The web container is healthy with zero restarts.

Local verification passed 603 tests with nine PostgreSQL-only skips, Ruff lint/format,
Django system/deployment checks, migration drift checks, and fresh in-memory migrations.
The actual candidate image passed all 80 targeted synthetic PostgreSQL tests, covering
assessment behavior, enrollment identifiers, authorization, Georgian labels, views,
deployment, and language switching. There are no new or pending migrations.

The restricted pre-release database backup restored successfully in an isolated PostgreSQL
container. The candidate passed the bilingual assessment checks against that restored data.
Candidate and running images each passed 26 assessment checks, 22 existing beneficiary-form
checks, and 19 language/password-gate checks. The assessment checks verified 1,140 name-first
option labels per run, including preselected and bound forms.

The public verification suite passed 36 checks across the active centers and both languages,
including actual HTTPS creation pages, enrollment preselection, cross-center denial, anonymous
redirects, and health endpoints. Both public HTTPS health endpoints also returned HTTP 200 from
the desktop. Beneficiary records, enrollment records, sequence counters, and the administrator's
login timestamp were unchanged during verification. No production assessment, beneficiary,
account, or other case record was created or edited. Authenticated reads generated normal audit
events, and the temporary verification session was deleted.

## Recovery and cleanup

Restricted recovery files and verification scripts remain under
`/home/sskadmin/ssk-private-releases/assessment-label-20261014/` on the VPS. The directory uses
mode 700 and the database/private-file backup archives use mode 600. Backup checksums and the
database archive catalog passed verification. The preceding image remains available for
application-only rollback; this release made no schema or data changes.

The isolated PostgreSQL container and its volume, temporary network, disposable test image,
and transferred bundle were removed after verification. No production export or source document
was copied to the desktop. Existing private configuration, private-file permissions, credentials,
account roles, sudo rules, and firewall settings were preserved.
