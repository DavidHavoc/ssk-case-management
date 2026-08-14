# Migration Plan from Frappe

No real data has been migrated. This plan defines a controlled future project.

## Principles

- Keep the Frappe repository and production system read-only during discovery and extraction windows.
- Never copy production data into developer laptops, screenshots, documentation, tickets, or ordinary CI.
- Use encrypted transfer and a restricted migration environment.
- Map by stable legacy identifiers, not display names.
- Preserve a reconciliation table from legacy identifier to Django UUID.
- Validate authorization and counts before any users receive access.
- Plan an explicit rollback and final source-system state.

## Proposed mapping

| Frappe source | Django target | Notes |
|---|---|---|
| User | User | Normalize email and active state, map roles separately |
| Employee | Staff Profile | Preserve employee identifier and primary center |
| Center | Center | Preserve legacy name in a migration crosswalk, generate stable code if needed |
| Specialist Profile | Specialist Profile | Link through migrated Staff Profile |
| Specialist Center Assignment | Specialist Center Assignment | Preserve primary and additional center meaning |
| Beneficiary | Beneficiary | Preserve case code, dates, and approved fields |
| Beneficiary Specialist child rows | Beneficiary Specialist Assignment | Validate center availability and duplicate rows |
| Service Visit | Service Visit | Convert visit month to first-of-month date and reconcile totals |
| Assessment | Assessment | Load parent rows before previous-assessment links |
| Assessment Domain Score | Assessment Domain Score | Load after Assessment |
| Individual Plan | Individual Plan | Load parent row before goals |
| Individual Plan Goal | Individual Plan Goal | Load after Individual Plan |
| Monthly Summary | Rebuild in Django | Do not trust imported derived totals without reconciliation |
| File | Private Attachment | Copy bytes into private storage, hash, map parent, authorize |
| Version and audit data | Separate retention decision | Do not import by default without policy and schema review |

## Migration stages

### 1. Data governance approval

Approve source owner, migration operators, legal basis, field scope, exclusions, retention, transfer encryption, evidence handling, cutover, rollback, and disposal of temporary copies.

### 2. Source profiling

In an approved isolated environment, count every source record, orphan, duplicate assignment, missing center, invalid date, invalid previous-assessment link, unsupported attachment URL, and inconsistent specialist assignment. Record counts and identifiers only where required, with restricted evidence access.

### 3. Extract

Build versioned export scripts against a read-only Frappe database account or approved Frappe export endpoint. Produce encrypted structured data and file manifests. Include SHA-256 hashes for attachments. Never use report exports that bypass parent authorization for routine access.

### 4. Transform

- map legacy names to Django UUIDs;
- normalize role names to the three application Groups;
- create staff center memberships and specialist assignments;
- normalize whitespace, email case, enumerations, and month values;
- retain blank optional values instead of inventing personal data;
- quarantine inconsistent records for business review;
- preserve a reason for every excluded record.

### 5. Load order

1. Centers
2. Users and Staff Profiles
3. Specialist Profiles and Center Assignments
4. Beneficiaries
5. Beneficiary Specialist Assignments
6. Service Visits
7. Assessments, then previous links and domain scores
8. Individual Plans and goals
9. Private Attachments
10. Rebuilt monthly summaries

Load with dedicated migration services that call the same model validation or equivalent prevalidated bulk rules. Do not use unrestricted bulk insertion without reconciliation.

### 6. Reconcile

Compare counts by Center, type, status, month, and Specialist. Compare service-unit and duration totals. Verify assessment chains and active-plan goals. Verify every file hash and authorized parent. Sample records with business owners using synthetic identifiers in evidence where possible.

### 7. Security validation

Test manager, coordinator, assigned specialist, unassigned specialist, cross-center user, report, export, form POST, and download paths. Confirm restricted fields do not leak into pages, errors, logs, audit metadata, or CSV.

### 8. Rehearsal and cutover

Run at least one full timed staging rehearsal. For production, define a write freeze, final delta method, user communication, DNS or proxy change, support window, and rollback deadline. Keep the legacy system according to approved read-only retention, not by accidental indefinite availability.

### 9. Temporary-data disposal

After approval and rollback expiry, securely dispose of decrypted extracts, temporary databases, file staging directories, and migration credentials. Retain only approved encrypted evidence and the crosswalk for its approved period.

## Unresolved decisions

- treatment of Frappe Comments, Communications, ToDo, Version, and Deleted Document;
- employee contract attachment scope;
- stock, asset, payroll, and accounting references excluded from the focused application;
- duplicate or missing personal ID handling;
- final retention of the Frappe source;
- migration downtime and delta strategy;
- external object storage and antivirus scanning.
