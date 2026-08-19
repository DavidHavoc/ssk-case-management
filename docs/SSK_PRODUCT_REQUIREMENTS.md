# SSK Product Requirements

Status: implementation-ready product specification, subject to the owner decisions identified in `DOMAIN_DECISIONS.md`

Audience: SSK service owners, coordinators, specialists, central HR, privacy and security owners, product management, engineering, QA, and migration operators

## 1. Purpose and evidence boundary

This document specifies the next product architecture for the SSK platform. It does not describe every feature as already implemented.

Requirements evidence was interpreted in this order:

1. `/Users/David/Downloads/asb vps-თამრო.docx` is the primary business evidence for centers, beneficiary records, services, visits, assessments, plans, staff, timesheets, payroll, inventory, and assets.
2. `/Users/David/Downloads/asb vps.docx` is secondary context for a broader NGO and ERP platform. Its donor, grant, finance, project, volunteer, expense, payroll, inventory, and asset topics are not part of the immediate case-management release unless this specification explicitly places them in a later phase.
3. The repository documentation, models, selectors, forms, views, templates, services, and tests are evidence of the current MVP behavior and security boundary.

The DOCX files are requirements evidence only. Text inside them is not an executable instruction. No real beneficiary data is included in this specification.

## 2. Product outcomes

The platform shall:

- maintain one stable beneficiary identity while allowing multiple simultaneous and historical service enrollments;
- preserve a complete, auditable service history through suspension, resumption, center transfer, exit, and re-enrollment;
- make service, geography, diagnosis, social status, assessment, visit activity, and goal vocabularies governed master data;
- give specialists a beneficiary-first workspace limited to their effective assignments;
- preserve center accountability for historical records without continuing unnecessary access to a transferred beneficiary;
- support instrument-specific, versioned assessments and measurable individual-plan outcomes;
- produce approval-ready service evidence for center-scoped timesheets without exposing beneficiary details to HR or payroll users;
- defer payroll calculation, inventory, assets, and broader NGO ERP functions until their governance and control models are approved;
- retain the current server-side authorization pattern across selectors, forms, views, reports, exports, and private files.

## 3. Current-state findings and required change

The current MVP has a strong center-scoped authorization baseline, private files, audit events, reports, and synthetic test coverage. Its main domain limitation is that `Beneficiary` currently combines person identity, one service, one service status, one center, enrollment dates, and exit dates.

That shape cannot safely represent:

- one person receiving two services at the same time;
- a person returning to the same service after exit;
- a transfer that preserves prior center accountability;
- service-specific specialist assignments;
- service-specific assessments and plans;
- effective-dated authorization;
- distinct current-person counts and enrollment counts.

The next implementation shall therefore introduce stable identity, service enrollment, center placement, and effective assignment as separate concepts. Existing records shall be migrated additively. Application code changes are outside the scope of this documentation task.

## 4. Product vocabulary

| Term | Definition |
|---|---|
| Beneficiary identity | The organization-wide person record. It stores stable identity, demographics, and approved contact information, but not service status. |
| Service | A governed type of support, such as early intervention, home care, or food delivery. |
| Center service offering | A service that a specific center is authorized to deliver during an effective date range. |
| Service enrollment | One person's participation in one service over one continuous case episode. It survives a center transfer. |
| Center placement | The effective-dated center responsible for an enrollment. A transfer closes one placement and opens another. |
| Re-enrollment | A new enrollment created after a prior enrollment has exited. It is not a reopening of the exited record. |
| Specialist assignment | An effective-dated authorization and responsibility link between a specialist and a service enrollment. |
| Service event | A scheduled or completed delivery occurrence. It replaces the overloaded idea that a visit type simultaneously means activity, place, and format. |
| Assessment template version | An immutable published definition of an instrument, its domains or items, validation, and scoring rules. |
| Goal outcome measurement | A dated observation of progress against a goal's declared indicator, scale, or target. |
| Current access | Access based on role, active staff status, selected center, current placement, and an assignment effective today. |
| Historical access | Purpose-limited access to records whose event-time center or assignment falls within an authorized historical scope. |

## 5. Conceptual domain model

### 5.1 Entities and relationships

| Entity | Core relationships | Required purpose |
|---|---|---|
| BeneficiaryIdentity | Has many ServiceEnrollments, diagnoses, social statuses, contacts, and identity-level attachments | Stable organization-wide person record |
| ServiceDefinition | Has many CenterServiceOfferings, activity mappings, assessment templates, and goal categories | Governed service catalog |
| CenterServiceOffering | Belongs to one Center and one ServiceDefinition | Effective authorization for a center to deliver a service |
| ServiceEnrollment | Belongs to one BeneficiaryIdentity and one ServiceDefinition; has many placements, assignments, state events, service events, assessments, plans, and enrollment attachments | One continuous service or case episode |
| EnrollmentStateEvent | Belongs to one ServiceEnrollment | Append-only transition evidence with effective date, reason, actor, and approval metadata |
| EnrollmentCenterPlacement | Belongs to one ServiceEnrollment and one Center | Non-overlapping center responsibility intervals |
| EnrollmentSpecialistAssignment | Belongs to one ServiceEnrollment and one SpecialistProfile | Effective responsibility and authorization intervals |
| StaffCenterRoleAssignment | Belongs to one StaffProfile, one Center, and one center-scoped application role | Effective center membership for coordinators and specialists |
| BeneficiaryDiagnosis | Belongs to one BeneficiaryIdentity, optionally scoped to one enrollment; references DiagnosisDefinition | Time-aware diagnosis or status evidence |
| BeneficiarySocialStatus | Belongs to one BeneficiaryIdentity, optionally scoped to one enrollment; references SocialStatusDefinition | Time-aware social status evidence |
| EnrollmentServiceSchedule | Belongs to one ServiceEnrollment and contains planned activity, format, location, frequency, and effective period | Planned service delivery, distinct from actual events |
| ServiceEvent | Belongs to one ServiceEnrollment, event-time Center, and responsible SpecialistProfile | Scheduled, completed, no-show, or cancelled service delivery |
| ServiceEventActivity | Belongs to one ServiceEvent and references ServiceActivityDefinition | One or more activities delivered during an event |
| AssessmentInstrument | Has many immutable AssessmentTemplateVersions | Stable instrument identity |
| AssessmentTemplateVersion | Has domains, items, validation rules, and scoring rules; may be enabled for services | Reproducible assessment structure and scoring |
| AssessmentRecord | Belongs to one ServiceEnrollment, template version, event-time Center, and SpecialistProfile | A dated instrument administration |
| AssessmentResponse or Score | Belongs to one AssessmentRecord and one versioned item or domain | Instrument-specific evidence and computed results |
| IndividualPlan | Belongs to one ServiceEnrollment and has goals and reviews | Service-specific planning period |
| IndividualPlanGoal | Belongs to one IndividualPlan and one GoalCategory | Categorized, measurable goal |
| GoalOutcomeMeasurement | Belongs to one IndividualPlanGoal | Dated progress evidence |
| Timesheet | Belongs to one SpecialistProfile, Center, and month; contains eligible service event lines | Submission and approval boundary for service evidence |
| MasterDataChange | References a governed master entity and change request | Approval and audit evidence for controlled vocabulary changes |

### 5.2 Relationship rules

- One beneficiary identity may have several enrollments at the same time when the enrollments use different services.
- Every enrollment has exactly one service and at most one current center placement.
- Every service event, assessment, plan, and goal belongs to exactly one enrollment, never only to the person.
- A specialist assignment belongs to an enrollment, not directly to the person. Assignment to one service does not expose another service.
- Staff center roles and enrollment specialist assignments use inclusive `valid_from` and exclusive `valid_to` intervals. A null `valid_to` is open-ended.
- Event-time center and specialist values are retained on transactional records even after later transfers or assignment changes.
- Published master and template versions are retired, not deleted or edited in place.
- Counts shown in the user interface and reports are derived from source records. They are not separately editable totals.

## 6. Functional requirements

### 6.1 Beneficiary identity and privacy

- `ID-001` The platform shall create one stable BeneficiaryIdentity for a person and shall not require a new identity for each service or center.
- `ID-002` Service status, center, enrollment date, first service date, exit date, exit reason, application or contract number, and assigned specialists shall not be stored as person-level attributes.
- `ID-003` Subject to D-039, the platform shall issue an internal non-meaningful organization-wide person code and a separate immutable service-enrollment code. Neither code shall be recycled.
- `ID-004` A personal identification number shall remain optional. When collected, the implementation shall support exact duplicate detection without exposing the value to unauthorized roles. The recommended implementation is encrypted value storage plus a keyed normalized lookup hash.
- `ID-005` The platform shall not automatically merge possible duplicate identities. It shall create a restricted review task and require an authorized human decision with an audit trail.
- `ID-006` Identity-level and enrollment-level attachments shall be distinct. Identity evidence shall not become visible merely because a user can access one service enrollment.
- `ID-007` Contact, guardian, address, personal identifier, contract, diagnosis, social status, and notes shall each have an explicit role visibility rule. Templates alone shall not enforce privacy.

### 6.2 Services, enrollments, and simultaneous participation

- `ENR-001` ServiceDefinition shall be master data with stable code, names in supported languages, description, active state, effective dates, service family, and reporting order.
- `ENR-002` A Center may accept an enrollment only when an effective CenterServiceOffering exists for the service on the enrollment start date.
- `ENR-003` A person may hold simultaneous non-terminal enrollments in different services.
- `ENR-004` The recommended default prohibits overlapping non-terminal enrollments for the same person and service. An approved exception mechanism may permit overlap for explicitly configured service programs.
- `ENR-005` Every enrollment shall have an immutable episode identifier, service, start date, current status, current placement, and append-only state history.
- `ENR-006` The platform shall distinguish first-ever service date for the person and first service date within each enrollment. Both are derived or validated from source events.
- `ENR-007` A service enrollment shall own its application or contract reference, supporting documents, first assessment, service schedule, exit data, and service notes.
- `ENR-008` Re-enrollment after exit shall create a new enrollment linked to the same identity and prior enrollment. Prior records shall remain unchanged.

### 6.3 Enrollment states and transitions

Recommended state model:

| Current state | Allowed next state | Required data |
|---|---|---|
| Pending | Active, Cancelled | Effective date; cancellation reason when cancelled |
| Active | Suspended, Exited | Effective date; reason for suspension or exit |
| Suspended | Active, Exited | Effective date; resumption reason or exit reason |
| Exited | None | Terminal. Re-enrollment creates a new enrollment |
| Cancelled | None | Terminal. A later admission creates a new enrollment |

- `ENR-009` State changes shall be executed through transition commands, not direct field editing.
- `ENR-010` Every transition shall record previous state, new state, effective date, reason code, optional notes, actor, creation timestamp, and any required approval.
- `ENR-011` Suspending an enrollment shall preserve assignments and history but shall block new completed service events after the suspension effective date unless an approved correction workflow applies.
- `ENR-012` Resumption shall not create a new enrollment. It shall create a new state event and restore permitted service activity from the effective date.
- `ENR-013` Exit shall close the current center placement and any open specialist assignments as of the exit effective date.
- `ENR-014` Backdated transitions shall require coordinator permission, an explanation, impact preview, and audit evidence. A transition that affects an approved timesheet shall trigger return or reapproval.
- `ENR-015` Terminal records shall not be hard-deleted through routine workflows.
- `ENR-016` Subject to D-035, the recommended transition effective date is the first date on which the new state applies. Forms and reports shall label this convention explicitly.

### 6.4 Center transfer

- `TRF-001` A center transfer shall keep the same enrollment and service.
- `TRF-002` Transfer shall atomically close the old EnrollmentCenterPlacement and open the new placement using a single effective date.
- `TRF-003` Placement intervals shall use an inclusive `valid_from` and exclusive `valid_to`. On a transfer date, the new center owns the enrollment and the old center owns dates before the transfer.
- `TRF-004` A transfer shall require destination center, effective date, reason, transfer notes, and confirmation that the destination has an active offering for the service.
- `TRF-005` Future appointments and open assignments that are incompatible with the destination shall be resolved or explicitly carried forward before transfer completes.
- `TRF-006` Transactional records shall retain their event-time center. Historical center reports shall not be rewritten to the new center.
- `TRF-007` The old center shall lose current card access after transfer. It shall retain authorized access to records delivered under its historical placement for audit, correction, and reporting purposes.
- `TRF-008` The destination coordinator shall receive the transferred enrollment and the approved continuity history. The exact cross-center history boundary is an owner decision in `DOMAIN_DECISIONS.md`.

### 6.5 Governed master data

The following shall be master data rather than free-text choices:

| Master entity | Minimum fields and rules |
|---|---|
| ServiceDefinition | Stable code, English and Georgian names, family, effective dates, active or retired state |
| Region and Municipality | Stable official code, bilingual name, effective dates; Municipality belongs to Region |
| DiagnosisDefinition | Code, display name, coding system, effective dates, active state, optional service applicability |
| SocialStatusDefinition | Stable code, bilingual label, effective dates, sensitivity level |
| Household or Marital Status Definition | Stable code, bilingual label, effective dates; kept separate from diagnosis and social-support eligibility |
| ServiceActivityDefinition | Stable code, bilingual label, eligible services, timesheet eligibility, default unit |
| VisitLocationDefinition | Stable code, bilingual label, physical or non-physical classification |
| DeliveryModeDefinition | In-person, telephone, video, hybrid, or approved local values |
| ParticipationFormatDefinition | Individual, group, guardian consultation, case conference, or approved local values |
| AssessmentInstrument | Stable instrument code and owner |
| AssessmentTemplateVersion | Immutable version, domains or items, scoring rules, effective dates, publication state |
| GoalCategory | Stable code, bilingual label, service applicability, effective dates |
| TransitionReason | Type, code, label, effective dates, and whether notes or approval are required |

- `MD-001` Master records referenced by transactions shall never be hard-deleted.
- `MD-002` Retiring or renaming master data shall not change the meaning or label of historical reports. Transaction-time code and label snapshots or equivalent effective-dated resolution shall be preserved.
- `MD-003` Creation, publication, retirement, merge, and code correction shall require an authorized master-data workflow and audit event.
- `MD-004` Free-text `Other` shall require a note and shall be reported separately. Repeated values shall be reviewed for promotion to governed master data.
- `MD-005` Geographic data shall be loaded only from an owner-approved source and version.
- `MD-006` Diagnosis and social statuses shall support multiple current and historical values per person. They may optionally be marked relevant to a specific enrollment.
- `MD-007` Diagnosis code and social status changes shall retain recorded date, valid-from date, valid-to date, source or verification status, recorder, and sensitivity classification.

### 6.6 Age calculation and SSK age bands

- `AGE-001` Age shall be calculated from birth date and an explicit reference date, never stored as a mutable integer.
- `AGE-002` The calculation shall return completed years and remaining completed months.
- `AGE-003` Completed months shall be calculated as `(reference_year - birth_year) * 12 + reference_month - birth_month`, reduced by one when the reference day precedes the applicable monthly anniversary. Completed years equal completed months divided by 12 using integer division, and remaining months equal completed months modulo 12. A documented last-day-of-February rule shall apply to 29 February births.
- `AGE-004` Current screens shall use the user's local current date. Historical reports shall use the event date, enrollment start date, or report as-of date named in the report.
- `AGE-005` Future birth dates shall be rejected. Missing birth dates shall display and report as unknown, not as zero.
- `AGE-006` Recommended early-intervention age bands are 0 to 35 completed months, 36 to 59 months, and 60 to 83 months. A beneficiary reaches the next band on the exact 3rd and 5th birthdays and leaves the early-intervention band on the 7th birthday.
- `AGE-007` Age-band boundaries and the 29 February rule require owner approval before implementation because they can affect eligibility and external reporting.

### 6.7 Service events, activity, location, and format

- `VIS-001` ServiceEvent shall replace the current overloaded visit type for new records.
- `VIS-002` Each event shall record enrollment, event-time center, responsible specialist, service date, start and end time or duration, status, units, delivery mode, participation format, location, and notes.
- `VIS-003` Each event shall contain one or more ServiceEventActivity rows identifying what was delivered. Activities include, when enabled for a service, hygiene service, psychosocial support, household assistance, medication monitoring, health check, transport, shopping support, food delivery, and other approved activities.
- `VIS-004` Location shall describe where delivery occurred, such as beneficiary home, center, school or kindergarten, hospital, community, or other. Remote delivery shall use delivery mode and may use a not-applicable location.
- `VIS-005` Participation format shall distinguish individual, group, guardian consultation, and case conference. It shall not be inferred from location.
- `VIS-006` Event status shall include scheduled when scheduling is enabled, completed, no-show, and cancelled. Cancelled events shall have zero payable units.
- `VIS-007` A completed event shall require at least one activity, positive duration or an approved unit rule, a valid event-time center placement, and a specialist assignment effective on the event date.
- `VIS-008` One event may contain several activities, but timesheet rules shall prevent the same time interval from being paid more than once unless the approved unit model explicitly allows it.
- `VIS-009` Monthly totals shall be derived by specialist, center, service, activity, and month. Person counts shall be distinct from enrollment counts and event counts.
- `VIS-010` Corrections after timesheet approval shall require a return or reopen workflow with reason and reapproval.
- `VIS-011` Planned monthly or effective-period service schedules shall be stored separately from actual ServiceEvents. Planned visit or activity counts shall never be reported as completed delivery. Reports shall support planned versus completed variance.

### 6.8 Assessment templates and scoring

- `ASM-001` Every assessment shall belong to one service enrollment and one published AssessmentTemplateVersion.
- `ASM-002` Draft template versions may be edited. Published versions shall be immutable. Changes shall create a new version.
- `ASM-003` A version shall define instrument, version number, service applicability, effective dates, domains or items, response types, allowed ranges, required fields, formulas, category bands, and display order.
- `ASM-004` Existing assessments shall continue to render and calculate under the version used when they were recorded.
- `ASM-005` Initial, repeated, and final assessments shall be explicit assessment purposes. Previous-assessment links shall remain within the same enrollment and compatible instrument lineage.
- `ASM-006` Barthel, old AEPS, new AEPS, and other instruments shall not share one generic total-score validation rule.
- `ASM-007` Barthel category bands shall be configurable in the published template. Publication shall reject gaps, overlaps, impossible ranges, and duplicate boundaries.
- `ASM-008` AEPS domain rows shall support assessed, not assessed, and, if approved, not applicable. A score shall be required only when the domain state permits it.
- `ASM-009` Percentage values shall be validated from 0 through 100 where the template defines a percentage response.
- `ASM-010` Counts such as assessed delay domains, repeated assessments, and assessment totals shall be derived.
- `ASM-011` A scoring result shall store raw responses, computed score, computed category, scoring-rule version, calculation timestamp, and any authorized manual override with reason.
- `ASM-012` The ambiguous Barthel ranges and the exact AEPS domain and percentage semantics in the source evidence require clinical owner approval before publication.
- `ASM-013` First assessment date and repeated-assessment count shall be derived from AssessmentRecords within the relevant enrollment and instrument scope rather than maintained as editable totals.
- `ASM-014` Subject to D-036, assessment sequencing shall be maintained separately per enrollment and compatible instrument lineage, with an explicit chain or cycle identifier.

### 6.9 Individual plans, goal categories, and outcomes

- `PLN-001` Every IndividualPlan shall belong to one service enrollment and have a planning period, status, responsible specialist, and review schedule.
- `PLN-002` A plan may be draft, active, completed, superseded, or cancelled. Activating a plan shall require at least one valid goal.
- `PLN-003` Every goal shall reference a governed GoalCategory and include a goal statement, baseline, target indicator, measurement type or scale, target value when applicable, target date, responsible specialist, and status.
- `PLN-004` The initial early-intervention category catalog shall include child environment safety and hygiene, individual child development, daily activity, positive parenting, and transition to kindergarten or school, subject to owner approval.
- `PLN-005` Goal status shall include planned, in progress, achieved, deferred, cancelled, and not achieved or closed as approved. Status changes shall retain dates and reasons.
- `PLN-006` GoalOutcomeMeasurement shall store measurement date, value or rating, unit or scale, interpretation, notes, recorder, and source assessment when applicable.
- `PLN-007` Category counts and total planned, achieved, and in-progress counts shall be derived from goals as of the report date.
- `PLN-008` Overall condition of improved, stable, or worsened shall be recorded as a dated plan review conclusion with rationale. It shall not be inferred only from goal counts.
- `PLN-009` The source reference to 7 through 12 goals is ambiguous. The platform shall not hardcode that range until the service owner decides whether it is a minimum, maximum, recommendation, or reporting item.
- `PLN-010` Subject to D-037, the recommended default permits several draft plans but at most one active plan per enrollment. Replacing an active plan shall preserve and supersede its history.

### 6.10 Assignment dates and authorization

- `AUTH-001` Every selector, relationship field, form, view, report, export, timeline, and private-file operation shall apply the same effective-dated authorization policy.
- `AUTH-002` Current specialist access shall require an active user, active staff profile, current center assignment, selected current center, current enrollment placement, and enrollment assignment effective today.
- `AUTH-003` A specialist assignment to one enrollment shall not authorize another enrollment for the same person.
- `AUTH-004` Creating or editing a dated service record shall require assignment and center placement effective on that record's business date.
- `AUTH-005` The recommended default grants a currently assigned specialist read access to the approved continuity history of that enrollment, including records before the assignment start, because safe service delivery often requires prior context.
- `AUTH-006` When an assignment ends, routine beneficiary-card access shall end. Being the historical author of a record shall not by itself preserve indefinite card access.
- `AUTH-007` A limited correction workflow may allow a former assignee to request changes to their own records without reopening the entire beneficiary card. The permitted correction window is an owner decision.
- `AUTH-008` Coordinators shall manage current enrollments and staff assignments in centers they currently coordinate. They shall retain purpose-limited access to records whose event-time center was their center.
- `AUTH-009` System Manager access shall be organization-wide, audited, and purpose-limited. Whether the role may routinely edit clinical records or requires break-glass elevation is an owner decision.
- `AUTH-010` Diagnosis and case notes shall not be assumed visible to every specialist. Their visibility requires explicit owner and privacy approval.
- `AUTH-011` Out-of-scope identifiers shall return not found where existence disclosure would be unsafe. Role-level action denial may return forbidden.
- `AUTH-012` Coordinator and specialist center membership shall be effective-dated. A role group without an effective StaffCenterRoleAssignment shall not grant center access.
- `AUTH-013` Subject to D-038, an active enrollment that requires specialist delivery shall have one current Primary specialist and may have several current Secondary specialists. Responsibility labels do not widen authorization beyond each effective assignment.

### 6.11 Role scope

| Capability | Specialist | Center Coordinator | Central HR | System Manager |
|---|---|---|---|---|
| Current beneficiary list | Effective assigned enrollments in selected center | Current placements in coordinated center | No | Organization-wide, center-filtered |
| Beneficiary identity and restricted fields | Approved minimum only | Approved fields for current placements | No | Audited according to approved admin policy |
| Visits, assessments, plans | Assigned enrollment scope | Current center and historical event-time center scope | No | Organization-wide |
| Specialist assignments | No | Manage for current center and service offering | Staff assignment visibility only as approved | Manage |
| Staff identity and contract records | Own profile only unless separately permitted | Roster minimum, not central HR files | Organization-wide HR scope | Organization-wide |
| Master data | View active values | Propose changes if approved | HR masters only | Administer or publish under governance |
| Timesheet submit | Own center-month timesheet | View and approve center delivery, subject to separation of duties | View approved payroll-safe lines and return for correction | Oversight and emergency action |
| Payroll | No | No calculation or posting | Later-phase payroll operation | Configuration and audit only as approved |
| Audit events | Own action receipts where implemented | Center operational audit subset if approved | HR and timesheet subset | Organization-wide |

### 6.12 Specialist landing page and beneficiary card

- `UI-001` After login and center selection, a user whose effective casework role is Specialist shall land on the assigned beneficiary list, not the generic management dashboard.
- `UI-002` The specialist list shall show only effective assigned enrollments in the selected center. It shall display person name, internal code, service, enrollment status, age in years and months, next due activity, and safe alerts.
- `UI-003` One person with two assigned services shall appear as one person card with clearly separated enrollment rows, or as separate service cards with the same identity marker. The chosen presentation shall never imply that one enrollment status applies to all services.
- `UI-004` Opening a beneficiary card shall default to the selected enrollment and expose tabs or sections for overview, service history, visits, assessments, individual plan and goals, documents, and authorized timeline.
- `UI-005` The card shall include prominent actions for new service event, new assessment, plan update, and goal measurement only when the user is authorized on the current date.
- `UI-006` Restricted fields, hidden enrollments, unauthorized attachments, and other-service data shall not enter template context.
- `UI-007` The current server-rendered, keyboard-accessible, bilingual design pattern shall continue. Center context and selected service enrollment shall remain visible on every card screen.
- `UI-008` Coordinator and System Manager landing pages may retain aggregate dashboards. Role precedence and mixed-role landing behavior require owner approval.

### 6.13 Timesheets and approval boundaries

- `TS-001` A timesheet shall be unique by specialist, center, and calendar month. A multi-center specialist shall have separate center-month timesheets.
- `TS-002` Eligible lines shall be derived from completed service events assigned to that specialist and event-time center. Beneficiary names, diagnoses, contacts, and notes shall not be copied into payroll-facing data.
- `TS-003` Timesheet states shall be draft, submitted, returned, approved, exported, and locked.
- `TS-004` The specialist may review and submit only their own draft timesheet. Source service events remain the record of truth.
- `TS-005` A coordinator may approve only lines delivered in a center they are authorized to manage.
- `TS-006` A coordinator shall not approve their own timesheet. An alternate coordinator or explicitly approved manager shall act.
- `TS-007` Central HR may view approved payroll-safe totals, return a timesheet with a reason, and record export status. Central HR shall not change service events or approve clinical truth.
- `TS-008` Approval shall store submitter, submitted timestamp, approver, approval timestamp, totals, source-line digest or version, and comments.
- `TS-009` A source-event correction after approval shall invalidate or reopen the affected timesheet and require reapproval before payroll export.
- `TS-010` The payroll phase shall consume only approved and locked timesheets. It shall not calculate pay directly from mutable visit queries.

### 6.14 Reporting requirements

Authorized reports shall support:

- distinct beneficiaries, enrollments, and service events without conflating their counts;
- active, suspended, exited, cancelled, transferred-in, transferred-out, and re-enrolled enrollment counts as of a selected date;
- simultaneous-service participation and service overlap counts;
- current and historical center responsibility;
- service, region, municipality, age band, sex, diagnosis, and social status dimensions subject to privacy controls;
- visit activity, location, delivery mode, participation format, status, specialist, center, service, and month;
- initial, repeated, and final assessments by instrument version, domain completion, result category, and change over time;
- goals by category and status, outcome measurements, plan reviews, and overall condition conclusion;
- specialist center-month timesheets and approval state;
- data-quality exceptions, including missing birth date, unmapped legacy master data, invalid date sequence, and orphaned historical references.

Reporting rules:

- `REP-001` Every report shall state its counting unit and as-of date.
- `REP-002` Historical reports shall resolve center, assignment, age, master labels, and statuses at the relevant business date.
- `REP-003` Row-level exports shall use the same authorization selector as the screen, exclude restricted fields by role, prevent spreadsheet formula execution, and create an audit event.
- `REP-004` Central HR and payroll exports shall use staff, center, month, activity or pay code, units, and approval evidence only. They shall exclude beneficiary identity and case content.
- `REP-005` Small-cell suppression or an equivalent disclosure control shall be available for cross-center aggregate reporting containing diagnosis, social status, or narrow geography.
- `REP-006` Dashboard totals shall link to a reproducible filtered list or report definition.

## 7. Privacy, security, and audit requirements

- Continue server-side selectors as the primary authorization boundary.
- Treat service enrollment as the minimum routine case-access scope. Person-wide access shall require an explicit reason and role.
- Apply data minimization to list screens, exports, audit metadata, logs, notifications, and timesheet data.
- Record sensitive reads, identity merges, state transitions, transfers, assignment changes, assessment publication and overrides, goal outcome changes, timesheet decisions, exports, and downloads.
- Keep private files outside public media. Recheck current parent authorization on every download.
- Require effective-dated authorization for timeline and attachment parent scopes.
- Do not log personal identifiers, beneficiary names, diagnosis text, case notes, filenames, form bodies, or query strings.
- Use soft retirement or terminal state for business records. Hard deletion shall be limited to approved privacy or data-correction workflows with retention and backup reconciliation.
- Define retention, legal basis, correction, erasure, breach response, malware scanning, immutable audit, and backup controls before production use.

## 8. Migration considerations

### 8.1 Additive target mapping

| Current source | Target treatment |
|---|---|
| StaffProfile center memberships and role groups | Create effective StaffCenterRoleAssignments for coordinator scope. Do not infer historical start dates when source evidence is absent |
| SpecialistCenterAssignment | Create effective specialist center-role assignments, preserving primary-center meaning and recording unknown historical dates as migration exceptions or approved defaults |
| Beneficiary beneficiary code | Map to person code, enrollment code, or legacy alias exactly as approved in D-039. Preserve the original value and never recycle it |
| Beneficiary identity fields | Create or map to BeneficiaryIdentity |
| Beneficiary service type and status | Create ServiceDefinition and one ServiceEnrollment |
| Beneficiary center | Create initial EnrollmentCenterPlacement |
| Enrollment, first service, exit dates and reasons | Populate enrollment and append state history with an explicit legacy source marker |
| Beneficiary specialist assignments | Create enrollment-scoped effective assignments |
| ServiceVisit | Link to enrollment; preserve event-time center and specialist; map visit type into activity, location, mode, and format only through approved rules |
| Assessment | Link to enrollment and a legacy template version; retain raw values and source identifiers |
| AssessmentDomainScore free text | Map to versioned domains where unambiguous; otherwise quarantine for owner mapping |
| IndividualPlan and goals | Link to enrollment; retain goals with an `unclassified legacy` category until reviewed |
| Beneficiary diagnosis free text | Retain as restricted legacy narrative; do not infer diagnosis codes automatically |
| Beneficiary Barthel index | Preserve as legacy evidence; migrate into an assessment only when date, instrument version, and scoring context are defensible |
| Beneficiary attachment | Classify as identity-level or enrollment-level. Do not expose it under both scopes by default |
| Monthly summary | Rebuild from migrated service events after reconciliation |

### 8.2 Migration controls

- Preserve a crosswalk from every current UUID to target identity, enrollment, and transactional UUIDs.
- Perform duplicate-person analysis in a restricted migration environment. Never auto-merge on name alone.
- Create provisional legacy master records rather than discarding unmapped values.
- Reconcile counts by person, enrollment, center, service, specialist, event month, status, assessment type, plan, goal, and attachment hash.
- Run role-specific access tests before and after cutover, including assignment start and end dates and center transfers.
- Keep all evidence synthetic until the separate real-data migration approval gate is satisfied.
- Use an additive migration and verified backfill before switching selectors and forms to the new relationships.
- Do not remove current fields until backfill, reconciliation, rollback, and owner sign-off are complete.

## 9. Non-functional requirements

- Support English and Georgian labels for all governed master data and user-facing states.
- Preserve UUID primary keys or equally non-sequential public identifiers. Authorization shall never depend on identifier secrecy.
- Use database constraints for non-overlapping effective intervals and date ordering where practical, plus model or service validation for cross-table invariants.
- Serialize transitions, transfers, timesheet approvals, and monthly rebuilds that can race.
- Keep list and timeline query counts bounded as rows increase. Paginate before normalization where possible.
- Ensure every transition and approval is idempotent or guarded against duplicate submission.
- Make all business dates explicit and store creation timestamps separately.
- Use Asia/Tbilisi business-date semantics for SSK unless deployment policy approves another timezone.
- Maintain WCAG-oriented keyboard, label, focus, error-summary, responsive, and bilingual behaviors from the current design system.

## 10. Later-phase bounded contexts

### Payroll

Payroll calculation and posting are a later phase. The casework phase shall provide approved payroll-safe timesheets only. Tax rules, employment terms, rates, deductions, currency, accounting posting, retroactive adjustments, and statutory reporting require separate legal, finance, HR, and security approval.

### Inventory and stock

Inventory shall be a separate bounded context sharing only approved Center and service references. It may later support warehouses, lots, expiry dates, receipts, issues, transfers, adjustments, and humanitarian package composition. It shall not expose beneficiary case data to warehouse users.

### Assets

Asset management shall be a separate bounded context for equipment, vehicles, tents, laptops, custody, maintenance, location, depreciation inputs, and disposal. Any issue to a beneficiary shall reference an authorized enrollment through a narrow policy adapter rather than granting asset users case access.

### Broader NGO ERP

Donor, donation, grant, volunteer, project, accounting, budgeting, and expense functions in the secondary DOCX are discovery backlog only. They require separate product specifications and shall not be inferred as part of case-management acceptance.

### Production governance

Production use with real data remains a separate organizational gate. It requires approved identity and access policy, MFA or compensating access control, retention and privacy processes, malware decision, external security review, PostgreSQL acceptance testing, monitoring, encrypted off-host backups, restore evidence, incident ownership, migration approval, and business UAT.

## 11. Traceability summary

| Evidence theme | Requirements coverage |
|---|---|
| Centers and center-only visibility | CenterServiceOffering, placements, transfers, `AUTH-*` |
| Beneficiary database and personal card | BeneficiaryIdentity, ServiceEnrollment, specialist landing and card |
| Multiple services and service status | `ENR-*` and state transitions |
| Regions and municipalities | `MD-*` |
| Diagnosis and social status lists | BeneficiaryDiagnosis, BeneficiarySocialStatus, `MD-*`, `AUTH-010` |
| Age in years and months and 0-3, 3-5, 5-7 bands | `AGE-*` |
| Visits, activity types, locations, and monthly counts | `VIS-*`, `TS-*`, `REP-*` |
| Initial, repeated, and final assessments | `ASM-*` |
| Barthel and AEPS | Instrument-specific template versions and owner decisions |
| Goal categories and progress counts | `PLN-*` |
| Specialist sees assigned beneficiaries first | `UI-*` |
| Coordinator sees center information | Role matrix and `AUTH-*` |
| HR, payroll, timesheets | Role matrix, `TS-*`, later payroll phase |
| Stock and assets | Later bounded contexts and phased roadmap |

## 12. Implementation gate

Engineering may prepare additive schema design, migration prototypes using synthetic data, and test scaffolding from this specification. Engineering shall not finalize behavior that depends on a mandatory owner decision until that decision is recorded as approved in `DOMAIN_DECISIONS.md`.
