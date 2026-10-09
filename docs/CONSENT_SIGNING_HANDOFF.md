# Handwritten consent signing handoff, 2026-10-09

**Release update, 2026-10-09:** the owner chose deployment-day expiry for legacy specialist
access. The pending 90-day decision below is resolved. See
[the integrated release handoff](INTEGRATED_RELEASE_HANDOFF.md).

Implemented locally on the existing `codex/center-beneficiary-codes` working tree. Prior contact,
enrollment, staffing, and bilingual intake work remains preserved. No deployment, SSH, push,
production record access, or production migration occurred. All test people and signatures are
synthetic. This is ready for final review, with the verification limits recorded below.

## Implemented workflow

An authorized manager or center coordinator opens **Sign consent / თანხმობის ხელმოწერა** from
the beneficiary page. The server-rendered review shows the person's exact name/code, template
version, language, the three existing service/care-sharing/confidentiality questions, all four
independent recorded decisions, and the full existing media declaration including its third item.
Unanswered is visibly not recorded. Refusals can be signed. No consent, signer role, or review
confirmation is preselected. Signing adds no clinical enforcement or ordinary casework block.

The signer independently supplies a full name and selects beneficiary, guardian, parent,
supporter, or representative. Non-beneficiary roles require a short stated relationship. This
records the stated capacity; it does not verify identity or legal authority. The authenticated
staff recorder remains a separate identity.

The small native canvas uses mouse/touch/stylus pointer events, has clear/redraw/cancel controls,
and requires both a drawing and a deliberate unchecked-by-default review confirmation before
Save signed consent becomes available. Pressing Enter inside signer text inputs does not submit.
Clear/redraw and return navigation discard the drawing and confirmation. No drawing is saved
before final POST. Every failed submission rerenders current wording with a blank pad, fresh
review token, and unchecked confirmation, while retaining the submitted signer fields.

The authorized printable alternative shows the same wording/decisions, identifies itself as
unsigned, and supplies lines for handwritten signer name, role, relationship, date, and signature.
It is reachable by keyboard in the same tab. A completed paper copy can use the existing private
beneficiary-document upload. Printing alone does not fabricate a digital signed record.

## Stored artifact and dependency choice

The artifact is **self-contained immutable printable HTML**, rather than a server-generated PDF.
This avoids adding a PDF layout/shaping stack to this deliberately small workflow. Printing uses
A4 rules and the browser's print facility. Browser pagination can vary; no PDF file is generated
or represented as the recorded artifact.

Each stored artifact embeds the normalized PNG signature, Noto Sans Georgian variable font
v2.005, complete font copyright/OFL 1.1 license text, and local CSS. It has no external font,
image, script, or stylesheet dependency. Beneficiary, signer, and document text are escaped by
Django templates. Current templates and translations are never applied to a completed document
at view/download time: routes stream the original privately stored bytes.

**Pillow `>=12.1,<13` is the only new runtime dependency.** Verification used Pillow 12.3.0.
It provides actual PNG verification/decoding and normalization, rather than trusting browser
canvas data or a PNG header alone. There is no signing SDK, SPA, font-processing library,
PDF renderer, public signing link, or external signing service.

The unmodified font is bundled with its original official metadata and full license in
`static/fonts/`. Its internal version was checked as 2.005. Its SHA-256 is
`dc591156f36842d38996c4a7a17fee9bb58e45da3e2cac7a31b7d33de700adb9`.
See [font provenance](../static/fonts/README.md),
[official source](https://github.com/google/fonts/tree/main/ofl/notosansgeorgian), and
[Pillow image safety documentation](https://pillow.readthedocs.io/en/stable/handbook/security.html).
No beneficiary document was sent to an external service.

## Snapshot, stale reviews, and duplicate submissions

`SignedConsent` records a protected beneficiary, original signing center, staff recorder,
server UTC signing timestamp, exact language, document version `SSK-CONSENT-1`, unique submission
UUID, and restricted JSON snapshot. The snapshot contains the exact reviewed questions/media
wording, answer codes and displayed labels, displayed beneficiary identity, document labels,
signer name/capacity/stated relationship, and the recorder's displayed identity plus account ID.
Two private attachments bind the normalized signature and generated document to that snapshot.
There is no mutable signature field on the beneficiary.

The signed timestamped review token is bound to person, staff account, center, language, displayed
content/identity/decisions, and a new execution UUID. It expires after one hour. The final service
uses the existing beneficiary lock, reloads account/center/person authority, and compares the
current fingerprint before writing. The intake update marker conservatively invalidates reviews
after any intake change, even when answers were changed and restored. A language, wording,
template-version, decision, or displayed person-name/code change requires a fresh signature.

A completed token retry returns the original authorized document and does not write more files
or records, including after later current-answer edits. The person lock serializes concurrent
PostgreSQL retries; UUID uniqueness is also enforced. Opening Sign consent again creates a fresh
token and allows a subsequent signed record while preserving every earlier document. The detail
page lists signed version/date/language and flags when current decisions differ from the latest
snapshot in the selected center.

Ordinary ORM updates/deletes of completed snapshots and their files are refused. PostgreSQL
triggers also reject raw updates/deletes, including file reparenting. SQLite developer triggers
reject updates and ORM signals reject deletes; raw SQL DELETE remains available for test flush.
These are application/database evidence controls, not external immutable storage or an assurance
against database/storage administrators. Downloaded copies can be edited outside the application.

## Permissions, storage, and audit

Only the existing active intake consent capability grants any signing/document route. Every
route resolves the authorized beneficiary or signed record. Staff membership, selected active
center, account/profile status, and enrollment scope still apply. Specialists, including current
lead/helper specialists, receive no consent/signature access from their separately approved
health/social rights. Unassigned specialists, HR-only accounts, inactive accounts/profiles,
anonymous visitors, and another center's users remain denied.

Each signed record and file stays bound to its signing center. Destination-center access after
a transfer does not expose the prior center's signed evidence, including for a manager currently
working in the destination. Ordinary beneficiary-file policy remains unchanged.

The implementation extends and uses the central policy registry in `private_attachments.py`.
The generated `signed_consent` parent is excluded from ordinary upload/download/delete routes.
Files use existing randomized private storage, containment checks, SHA-256/size metadata,
audited authorized downloads, and atomic uploads. The HTML is stored through the existing
UTF-8 `.txt` validation and served only by consent routes with a private `.html` filename and
`text/html; charset=utf-8`. Ordinary allowed upload types remain unchanged. No arbitrary HTML
upload, public media URL, signature export, or specialist timeline entry is added.

Signature input is limited to 128 KiB, 200 to 1400 pixels wide, and 80 to 600 pixels high. The
server verifies and fully decodes PNG, rejects animation, empty/invisible drawings and implausibly
filled canvases, flattens transparency to white, and rewrites without source metadata. Response
policies block active content/network dependencies and use nosniff and private/no-store caching.
Finalization uses POST and CSRF. Audit metadata contains safe event/file-type information only.

Database rows, both files, and successful audit events roll back together. Generated file paths
are reserved before the storage write so cleanup also handles a storage exception after bytes
were written. Forced first-file, second-file, post-write, and final audit failures left no signed
record, private attachment, file, or successful creation event.

## Migrations and preserved work

Apply the existing uncommitted migration chain through `0019`, followed by:

1. `0020_signed_consent`: additive snapshot model and private parent choice. No backfill.
2. `0021_signed_consent_file_uniqueness`: conditional filename uniqueness for evidence files.
3. `0022_signed_consent_guards`: PostgreSQL/SQLite evidence guards and reversal preflight.

No signing history, answers, or staff permissions are fabricated for existing people. Forward,
reverse, and replay tests compare all original historical-model rows exactly. Empty-schema
reversal works. Once signed evidence exists, reversal refuses before removing its guards/schema;
preserve the schema/files and review compatibility rather than forcing evidence deletion.

One existing intake migration test's final cleanup now restores the graph's current leaf nodes
instead of stopping at `0019`. Its migration assertions remain unchanged. The original full
PostgreSQL run exposed that test-order problem; the combined regression run and repeated full
run pass after repair. All 60 preceding changed/untracked files outside the 14 explicitly scoped
existing-file edits match their pre-task SHA-256 hashes. All work remains uncommitted.

New implementation files are `consent_signing.py`, `consent_views.py`, consent template tags,
the three migrations, review/artifact/wording/history templates, `consent-signature.js`, the bundled
font/license/provenance, `test_consent_signing.py`, and this handoff. Existing scoped edits include
models/private attachment policy/routes/detail context, shared media wording, beneficiary detail,
CSS, dependency declaration, catalog, permission/security/data-model documentation, and the
migration-test cleanup described above.

## Exact final verification

- Complete SQLite suite: **555 passed, 9 PostgreSQL-only skips in 183.97 seconds**.
- Complete disposable PostgreSQL 16 suite: **564 passed, no skips in 314.73 seconds**.
- Focused signing PostgreSQL suite: **64 passed in 48.81 seconds**.
- Combined intake/signing PostgreSQL regression run: **139 passed in 88.58 seconds**.
- Final combined SQLite run: **136 passed, 3 PostgreSQL-only skips in 53.46 seconds**.
- A further focused signing SQLite run after the printable-link refinement:
  **62 passed, 2 PostgreSQL-only skips in 26.96 seconds**.
- Ruff lint passed. Ruff format check: **150 files already formatted**.
- Django system checks and synthetic production-settings deployment checks with
  `--fail-level WARNING` passed. `makemigrations --check --dry-run` reported no changes.
- Fresh full migrations and `migrate --check` passed on separate disposable SQLite/PostgreSQL
  databases. PostgreSQL coverage includes concurrent duplicate finalization, shared intake lock,
  stale rejection after a blocked writer resumes, raw evidence deletion denial, and schema tests.
- `msgfmt --check --check-format` passed. Recompilation matches the delivered `.mo` byte for byte.
  `git diff --check` and no-em-dash checks passed.

The maintained tests cover English/Georgian beneficiary and representative signings by manager
and coordinator; refusals/all-unanswered decisions; exact wording/language/recorder/timestamp;
escaping; later identity/answer edits and a subsequent signature; stale template/wording/locale/
expiry/forged-token submissions; duplicate retries; required signer/relationship/review fields;
blank/malformed/wrong-format/oversized/invisible/dimension-invalid images; anonymous/CSRF/forged
IDs; inactive account/profile/center, removed membership and transfers; lead/helper health access
without signatures; private routes; general export exclusion; storage cleanup and immutability.

## Browser verification and final review limits

The in-app browser used a disposable synthetic preview, never the developer or hosted database.
English beneficiary and Georgian parent/representative signings completed through actual canvas
mouse input. Clear by keyboard discarded drawing/confirmation, Space confirmed, Tab reached the
save button with a visible solid outline, and Enter on that button completed the Georgian record.
Both earlier language records remained separately listed with version/date and translated download
labels. Enter in signer text fields did not submit. The keyboard printable link opened the
unsigned, fully translated paper copy without creating signing evidence.

Both review languages fit **320, 768, 1024, and 1440 pixels** with no document overflow. Tablet
pad and controls, mobile wrapped wording/buttons, and desktop layout were visually inspected.
The signed Georgian artifact fits mobile/tablet/desktop, its embedded font reports loaded, and
its signature image decodes and displays. The browser HTML download's SHA-256 exactly matches
the stored private artifact. Browser error/warning inspection returned no entries for the verified
flow. Screenshots and one synthetic HTML document are retained in the task visualization directory.

Actual finger/stylus hardware, formal screen-reader/axe audits, and native printer pagination
were not exercised. The in-app browser print shortcut did not expose a native print preview.
Browser/A4 print CSS and the complete printable document were inspected, but physical printing
remains a final user review check. No server-generated PDF is claimed.

Preview tabs/server, disposable database/private files, PostgreSQL container/database, and the
browser-created Downloads copy were removed. The retained artifacts are synthetic only.
For final review, inspect the review pad, unsigned paper flow, and stored HTML in the intended
browser/device/printer. Before any separately authorized deployment, retain the preceding
staffing handoff's pending owner decision on the 90-day compatibility deadline. This task neither
changes that policy nor authorizes deployment.
