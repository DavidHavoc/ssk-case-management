# Data Model

All domain records use UUID primary keys and created and updated timestamps unless stated otherwise.

## Identity and centers

| Entity | Important fields and relationships |
|---|---|
| User | Django username, email, password hash, required-password-change state, preferred language, Group roles |
| Center | Unique code and name, active state, contact information |
| Staff Profile | One User, unique employee number, project or program, position, active, inactive, or finished status, contact number, contract dates, description, notes, primary Center, and many Center memberships |
| Specialist Profile | One Staff Profile and shared specialist description |
| Specialist Center Assignment | One Specialist Profile, one Center, optional primary flag |

Constraints prevent duplicate specialist and center pairs and more than one primary center per specialist.

## Case records

| Entity | Important fields and relationships |
|---|---|
| Beneficiary | Unique case code, person identity, demographic, contact, free-text case notes, controlled geography, and restricted fields |
| Service Definition | Stable code, service family, effective dates, overlap policy, active state |
| Center Service Offering | Center, Service Definition, effective dates, enabled state |
| Service Enrollment | Beneficiary, Service Definition, episode code, status, dates, prior enrollment, preserved legacy source values |
| Enrollment Center Placement | Service Enrollment, Center, effective dates |
| Enrollment Specialist Assignment | Service Enrollment, Specialist Profile, role, effective dates |
| Enrollment State Event | Service Enrollment, lifecycle event, effective date, from and to states, actor, reason; transfer center history remains in placements |
| Region and Municipality | Controlled Georgian geography with each Municipality assigned to one Region |
| Diagnosis Definition and Beneficiary Diagnosis | Coded diagnosis catalog and effective-dated beneficiary classification with explicit specialist visibility |
| Social Status Definition and Beneficiary Social Status | Coded social-status catalog and effective-dated beneficiary classification with explicit specialist visibility |
| Beneficiary Specialist Assignment | Preserved legacy beneficiary-level assignment |
| Service Activity Definition | Governed bilingual activity code, effective dates, reporting order, default unit label, optional applicable services |
| Visit Location Definition | Governed bilingual location code, physical or remote kind, effective dates, reporting order |
| Enrollment Service Schedule | Service Enrollment, month, activity, delivery location, individual or group format, planned visits and units, expected participants |
| Service Visit | Service Enrollment, Beneficiary, event-time Center, Specialist, visit date and month, activity, delivery location, format, status, units, duration, participants, cancellation reason, optional goals worked on |
| Service Visit Correction | Service Visit, actor, reason, and immutable before and after field snapshots |
| Assessment Instrument | Stable instrument code, tool identifier, lineage, active state |
| Assessment Template Version | Instrument, immutable version, publication state, service scope, effective dates, scoring and comparison rules |
| Assessment Template Section and Field | Ordered versioned structure, typed response contract, validation, total and delay rules |
| Assessment Score Band | Versioned inclusive lower and upper bounds with a derived classification label |
| Assessment | Service Enrollment, Beneficiary, event-time Center, responsible Specialists, purpose, date, explicit chain, template version, derived total, classification, delayed-domain count, recommendations, notes, and review date |
| Assessment Response | Assessment, versioned field, assessed state, typed value, notes |
| Assessment Domain Score | Preserved legacy free-text domain, baseline and current scores, notes, and mapping-review state |
| Goal Category | Stable bilingual code and labels, effective dates, reporting order, service applicability, legacy marker |
| Individual Plan | Service Enrollment, Beneficiary, event-time Center, Specialist, version, previous period, status, period dates, review frequency and due date |
| Individual Plan Goal | Individual Plan, Goal Category, statement, baseline, measurable target, measurement type and scale, responsible Specialist, target date, status, achieved date, evidence, progress notes, assessment links |
| Goal Status Transition | Goal, prior and new status, effective date, actor, reason, evidence; append-only |
| Goal Outcome Measurement | Goal, date, numeric value or rating, scale, interpretation, notes, recorder, optional source Assessment; append-only |
| Individual Plan Review | Plan, review date, improved, worsened, stable, or not-yet-assessed conclusion, rationale, recorder, optional source Assessment; append-only |
| Specialist Monthly Service Summary | Specialist, Center, month, visit and service aggregates |

Enrollment assignment and placement intervals use included `valid_from` and excluded `valid_to` boundaries. A null assignment `valid_from` is preserved only as incomplete legacy history and does not establish authorization. Database constraints prevent invalid date ordering. Model and service validation reject overlapping center placements and disallowed same-service enrollment overlap. Preserved source intervals that began and ended on the same date are explicitly marked as legacy rather than discarded.

Service Visit derives visit month from visit date. Service Visit, Assessment, and Individual Plan validate that beneficiary, center, and specialist match the selected enrollment at the business date. A visit also validates that its enrollment is open, its activity and location are effective, and its specialist assignment applies on the visit date. The event-time center is retained when an enrollment later transfers.

Planned schedules are separate from actual visits. Planned, no-show, and cancelled visit records contribute zero delivered service units. Completed visits require positive units and duration. Group visits require at least two participants. Cancelled visits require a reason. Editing an existing visit requires a correction reason and appends an immutable correction record while the ordinary audit log records the update action.

One Beneficiary can have concurrent enrollments for different services. Same-service overlap is rejected unless the Service Definition explicitly permits it. Re-enrollment creates a new episode linked to its prior episode.

## Privacy records

| Entity | Important fields and relationships |
|---|---|
| Private Attachment | Parent type and UUID, optional staff document category, Center, private file, original name, size, SHA-256, uploader |
| Audit Event | Actor, Center, event type, outcome, target type and UUID, safe metadata, timestamp |
| Login Throttle | HMAC key, failure count, window start, update timestamp |

Private Attachment intentionally uses a restricted parent-type map rather than accepting arbitrary models. Audit Event metadata accepts only a small allowlist and never stores beneficiary field values or file contents.

## Derived summary rules

A summary is unique by Specialist, Center, and calendar month. Rebuilds count:

- completed visits;
- planned visit records;
- completed service units;
- completed duration minutes;
- unique beneficiaries with completed visits;
- no-show visits;
- cancelled visits.

Updating a visit rebuilds both its new summary key and its previous key. Deleting the last visit removes the empty summary.

The planned versus delivered monthly report groups schedules and completed visits by beneficiary, enrollment, activity, location, format, and month. It includes schedule-only and delivery-only rows so missing plans and unplanned delivery remain visible. Payroll calculations are not part of this model.

Goal totals are never stored. Plan detail and outcome reporting calculate total, planned, in-progress, achieved, deferred, and cancelled goals from source goal records by category and overall. A child-condition conclusion comes only from the latest applicable plan review and is not inferred from goal counts.

## Derived beneficiary timeline rules

The enrollment timeline is a read model for transactional activity and has no duplicate transaction-event table. Lifecycle history is stored separately as append-only Enrollment State Events. Transaction activity dates are:

- Service Visit: `visit_date`
- Assessment: `assessment_date`
- Individual Plan: `plan_start_date`
- Individual Plan Goal: `target_date`, falling back to its plan's `plan_start_date`
- Private Attachment: `created_at`

Entries are ordered by activity date descending, record creation timestamp descending, fixed type rank, and UUID. The final fields make ties deterministic. Attachments display their full creation timestamp while the heterogeneous database index compares their calendar date with date-based case records.

## Index strategy

- Service plus status and beneficiary for enrollment lists
- Enrollment plus effective date for placements, assignments, and lifecycle history
- Enrollment plus date and status or type for visits, schedules, assessments, and plans
- Activity plus location, month, and status for service-delivery reporting
- Region plus municipality name for controlled geography
- Beneficiary plus classification and effective date for diagnosis and social status
- Specialist plus month or status for reporting
- Beneficiary plus date for case timelines
- Parent type plus UUID for attachment lookup
- Actor, Center, target, and timestamp for audit review
