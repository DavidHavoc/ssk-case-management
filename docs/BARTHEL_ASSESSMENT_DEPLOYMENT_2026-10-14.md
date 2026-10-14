# Barthel assessment deployment, 2026-10-14

The owner supplied the Georgian scale, confirmed the five dependency and care-need bands,
required a beneficiary or representative signature, and explicitly authorized deployment.
The release is live at `https://0ufkrzj.cserverhost.cloud`.

Assessment creation now shows named templates without version numbers and beneficiary
choices with completed age and code. The built-in `ბართელის სკალა` provides ten required
multiple-choice activities. Scores are validated and summed on the server, with a browser
preview of the total, functional dependency, and care need. A score of 55 displays 55/100,
Severe dependency, and High care need. The confirmed bands are 0-20 Total / Very high,
21-60 Severe / High, 61-90 Moderate / Moderate, 91-99 Slight / Low, and 100 Independent / Minimal.

Additional care needs are recorded separately, and the interface explains that Barthel alone
does not determine home-care visit frequency or service intensity. New assessments remain
drafts until a beneficiary or representative signs the reviewed content. Signed evidence and
documents are private and immutable; corrections require another signature. Existing
assessments remain unchanged and unsigned.

## Release and verification

- Application commit: `82ba0c7c4c1ac7cf0b38aacf0eeb9eed6a4eaea5`.
- Previous application commit: `4ed1938ccd7a4e9350114db9b6dbd6fc24edd656`.
- Running image: `ssk-web:barthel-20261014`, also tagged `ssk-web:latest`.
- Running image ID: `sha256:a4f0494485debdbd443ab6c1bc733baf97cf16bc30f9c7e8fe898e2cbfe71ccd`.
- Retained previous image: `ssk-web:before-barthel-20261014`.
- Previous image ID: `sha256:09063f44ee851307e27154e49f13a52d594904c63fd2c4441bd6944e0d9580b1`.
- Migrations 0023, 0024, and 0025 applied successfully, with no pending migrations.

The release was delivered through a code-only Git bundle without a GitHub push. Runtime
dependencies were retained from the preceding image. Static assets were rebuilt, and all
runtime source checksums match the application commit. The web container is healthy with
zero restarts, and the remote checkout is clean at the application commit.

Local verification passed the complete synthetic PostgreSQL suite with 652 tests and the
SQLite suite with 642 tests and ten PostgreSQL-only skips. Final focused PostgreSQL assessment,
signing, correction, and authorization regressions passed all 81 tests. Ruff lint/format,
Django system/deployment checks, migration consistency, JavaScript syntax, and translation
catalog checks passed. Synthetic browser verification included the 55-point result,
representative signing, both languages, and responsive layouts.

The actual candidate image passed all 652 tests against a separate synthetic PostgreSQL
database on the VPS. Initial and final production database backups restored successfully in
isolated databases. The migrations were rehearsed on each restore before production changes.
Web writes were stopped for the final backup, reconciliation, and production migrations.

Reconciliation preserved every original field of all 2,756 rows across 65 tables. The only
additions to existing tables were the 25 expected template, section, question, band,
migration, content-type, and permission rows, plus normal audit events from authorized reads.
No production beneficiary, assessment, signature, account, service history, or other case
record was created or edited for verification. Original private files match the final backup,
including their contents and permissions.

Candidate and running images each passed 145 bilingual assessment checks and 1,140 enrollment
option checks, plus 22 beneficiary-form checks and 19 language/password-gate checks. The public
HTTPS suite passed 161 checks across both languages and active centers, including creation,
preselection, age/code labels, scored choices, signing-step wording, care-needs text, hashed
JavaScript/CSS assets, cross-center denial, anonymous redirects, and health. Both public
health endpoints also returned HTTP 200 from the desktop. Existing assessments, beneficiaries,
enrollments, counters, and the administrator login timestamp remained unchanged during these
checks. The temporary verification session was deleted.

## Recovery and cleanup

Restricted initial/final database dumps, private-file backups, checksums, archive catalogs,
reconciliation evidence, and verification scripts/logs remain under
`/home/sskadmin/ssk-private-releases/barthel-20261014/` on the VPS. The directory uses mode 700
and its files use mode 600. Both backup checksum sets were reverified after cleanup.

The previous image remains available with the recovery backups. This release adds schema and
immutable evidence, so any rollback must preserve assessments and signatures created after
deployment. Database migrations refuse reversal that would discard new evidence. Do not restore
the pre-release database over subsequent casework.

The isolated restore/test databases, container and volume, internal network, disposable test
image, exported source tree, and transferred bundle were removed. No production export or
source document was copied to the desktop. Private configuration and TLS contents and modes
were verified unchanged. Credentials, roles, sudo rules, and firewall settings were not changed.
