# Feature Parity Checklist

This matrix compares the inspected Frappe working tree with the standalone Django MVP.

| Legacy behavior | Django implementation | Status |
|---|---|---|
| Center registry and contact validation | `Center` model and scoped center views | Implemented |
| User-linked Employee center | `StaffProfile` with primary center and center memberships | Implemented with multi-center support |
| Shared specialist profile | `SpecialistProfile` linked one-to-one to staff | Implemented |
| Specialist primary and additional centers | `SpecialistCenterAssignment` with uniqueness constraints | Implemented |
| Inactive Employee access revocation | Inactive staff profiles are excluded from center and specialist selectors | Implemented |
| Coordinator-managed roster | Current-center roster add, create, edit, and remove views | Implemented |
| Specialist role assignment | New specialist workflow assigns `SSK Specialist` Group | Implemented |
| Beneficiary profile and age | Full case profile with calculated age and category | Implemented |
| Restricted beneficiary fields | Server-side form removal, template omission, report omission, export restriction | Implemented |
| Beneficiary specialist rows | Unique through model with center and date validation | Implemented |
| Center-scoped list and document access | Shared authorization selectors for every route | Implemented |
| Specialist assigned-beneficiary access | Beneficiary assignment selector | Implemented |
| Visit enrollment, center, specialist assignment, activity, location, and business-date validation | Model, selector, and form validation | Implemented |
| Visit month `YYYY-MM` | First-of-month database date with `YYYY-MM` display | Implemented |
| Planned, completed, no-show, and cancelled visits | Explicit workflow states, delivered-unit normalization, participants, duration, and cancellation reasons | Implemented |
| Service activity and location catalog | Governed bilingual catalogs with effective dates and reporting order | Implemented |
| Monthly enrollment service schedule | Activity, location, format, planned count, units, and participants by month | Implemented |
| Planned versus delivered reporting | Authorized monthly variance by beneficiary, enrollment, activity, location, and format | Implemented |
| Visit correction evidence | Required correction reason, immutable snapshots, and ordinary audit event | Implemented |
| Initial, repeated, and final assessments | Explicit per-enrollment and per-instrument chains with final closure and correction revisions | Implemented |
| Versioned assessment templates | Draft, published, withdrawn, service-effective selection, immutable historical versions | Implemented |
| Instrument-specific assessment responses | Numeric, percentage, assessed state, choice, text, not applicable, calculated totals and classifications | Implemented |
| Early-intervention domain tracking | Structural old AEPS and new AEPS drafts with supplied domains and no licensed questions | Implemented pending clinical publication approval |
| Legacy assessment preservation | Locked legacy versions, preserved totals, unchanged free-text domain rows, review-required mapping | Implemented |
| Individual plan date and specialist validation | Model and form validation | Implemented |
| Active or completed plan requires goals | Transactional inline-form workflow validation | Implemented |
| Versioned plan periods | Sequential enrollment-specific versions with prior-period links and atomic supersession | Implemented |
| Measurable plan goals | Bilingual governed category, baseline, target, specialist, date, status, achievement evidence, and assessment links | Implemented |
| Goal and review history | Append-only status transitions, outcome measurements, and dated child-condition reviews | Implemented |
| Visit goal linkage | Optional enrollment-scoped goals worked on during a visit | Implemented |
| Plan outcome reporting | Authorized category and overall counts derived from goals with separate reviewed child-condition outcome | Implemented |
| Monthly specialist service summary | Signal-driven center-specific aggregates | Implemented and corrected for multi-center work |
| Specialist sees only own summary | Summary selector | Implemented |
| Center and specialist filtered report | Authorized HTML report filters | Implemented |
| Coordinator CSV export | Formula-safe UTF-8 CSV without restricted values | Implemented |
| Specialist beneficiary export denied | Export endpoint denies specialist role | Implemented |
| System Manager record delete | Current-center delete routes with protected-reference handling and audit events | Implemented |
| Sensitive case files private | Non-public storage and randomized names | Implemented |
| Private attachment upload | Parent, center, and uploader are bound before model validation | Implemented |
| Parent-authorized downloads | Download view rechecks current parent access | Implemented |
| Specialist denied direct beneficiary attachment | Beneficiary attachment selector | Implemented |
| Attachment metadata filtering | Unauthorized attachment rows never enter template context | Implemented |
| Employee contract attachment privacy | Permission-controlled private project agreements, employee contracts, and additional staff documentation | Implemented |
| Georgian language setup | Django locale, selector, complete PO and MO catalogs | Implemented for extracted MVP strings; native-speaker UAT remains required |
| Synthetic demo seed | `seed_demo_data` management command | Implemented |
| Stock Entry center validation | Not in focused case-management scope | Not included |
| Asset center and beneficiary validation | Not in focused case-management scope | Not included |
| Salary Slip integration | Legacy did not implement posting | Not included |
| Automated retention and erasure | Requires organizational policy and reviewed design | Future work |
| Beneficiary data-subject export | Requires identity, approval, encryption, and delivery decisions | Future work |
| Frappe ToDo assignment filters | No direct replacement in MVP | Future evaluation |
| Frappe Communication attachment inheritance | No Communication entity in MVP | Not applicable |

## Required parity validation

- Execute the legacy browser UAT scenarios against a staging Django deployment.
- Obtain business-owner approval for intentional scope exclusions.
- Validate Georgian terminology with native-speaking coordinators and specialists.
- Reconcile report totals against a synthetic migration rehearsal.
