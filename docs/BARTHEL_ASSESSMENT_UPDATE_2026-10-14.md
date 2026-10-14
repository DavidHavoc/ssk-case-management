# Barthel assessment update, 2026-10-14

Status: implemented and verified locally. This update has not been deployed or pushed to GitHub.

## Owner-confirmed behavior

- Assessment creation shows template names without version numbers. The version remains internal to the reproducible scoring record.
- Beneficiary enrollment choices include the person's name, beneficiary code, service, status, enrollment date, and completed age. Unknown age is explicit.
- `ბართელის სკალა` is built in with ten required activities and thirty scored choices. The browser previews the complete result; the server derives and validates every score.
- Inclusive bands are 0-20 Total / Very high, 21-60 Severe / High, 61-90 Moderate / Moderate, 91-99 Slight / Low, and 100 Independent / Minimal. These supersede the incomplete screenshot categories. A score of 55 displays 55/100, Severe dependency, and High care need.
- Additional care needs are recorded as a narrative. The interface and retained document explain that Barthel alone does not determine home-care visit frequency or intensity. No schedules or service plans are inferred.
- Creation ends with review and a required beneficiary or representative signature. Staff recorder and signer remain separate. A representative states their relationship. Drawing and signed-paper PDF alternatives are supported.
- New assessments remain drafts until signing. Signed answers, result, and narratives are retained in a private, immutable document with authorized viewing and downloads. Changed or expired reviews require fresh signatures. Signed corrections require another signature before superseding the earlier revision.
- Existing assessments remain intact and unsigned. Beneficiary source values, codes, account roles, and service histories are not rewritten by these migrations.

## Schema and publication

- 0023 adds scored choices, separate dependency/care levels, additional care needs, and signed assessment evidence. SQLite guards are restored around transactional table rebuilding. Reversal refuses to discard new assessment evidence.
- 0024 publishes `BARTHEL`, version `ssk-20261014-1`, with the supplied activities and the confirmed bands. It retains the original structural draft. Reversal refuses to delete a used template.
- 0025 adds database guards for signed assessment records and their files. Reversal refuses to remove completed signing evidence.

The published template is available through the existing effective-date and service authorization checks. Other draft instruments remain unpublished. No real beneficiary data, signature, or source file was used in local verification.

## Verification

- Complete synthetic PostgreSQL suite: 652 tests passed, no skips.
- Complete SQLite suite: 642 tests passed, ten PostgreSQL-only skips.
- Final PostgreSQL assessment, signing, correction locking, and authorization regressions: all 81 tests passed after the final refinements.
- Ruff lint and format, Django system and production deployment checks, migration consistency, JavaScript syntax, and translation catalog checks passed.
- Browser checks verified the 55-point preview, Georgian and English wording, completed age and code, the creation-to-signing transition, and the drawn representative-signature completion path. Review and signature layouts were inspected at 320, 768, 1024, and 1440 pixels. Wide response tables scroll within their containers.
- Focused tests cover all reachable Barthel scores, tampered choices/points, missing responses, required and expired reviews, changed content and authority, cross-center access, private file routes, escaping, paper signatures, duplicate submissions, storage rollback, database immutability, and fresh signatures for corrections.

Local disposable databases, generated synthetic signatures, the preview server, and the PostgreSQL test container are removed after verification. The established production backup, restore, code-only delivery, and hosted verification procedure remains necessary for deployment.
