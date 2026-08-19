# Acceptance Criteria

Status: implementation acceptance specification

These scenarios use synthetic identities and records only. Scenarios that depend on an open mandatory decision shall be finalized against the approved decision before implementation acceptance. Passing user-interface scenarios never substitutes for server-side selector, form, view, report, export, and download tests.

## 1. Acceptance conventions

- `Given` establishes authorized synthetic data and effective dates.
- `When` describes one user or system action.
- `Then` describes observable behavior, stored state, authorization, and audit evidence.
- `As of` means the named business date, not record creation timestamp.
- Counts must state whether they count people, enrollments, events, assessments, goals, or timesheets.
- Not-found behavior is expected for unsafe out-of-scope identifiers. Forbidden behavior is expected for a known role-level action denial.

## 2. Beneficiary identity and service enrollment

### AC-ID-001: One identity, two simultaneous services

Given one synthetic person and two active center service offerings for different services, when an authorized coordinator enrolls the person in both services, then the platform stores one BeneficiaryIdentity and two ServiceEnrollments with independent status, center placement, assignments, plans, and documents.

### AC-ID-002: No duplicated person status

Given one identity with one Active enrollment and one Suspended enrollment, when any card or report is shown, then it does not display a single person-level service status and each status is labeled with its enrollment and service.

### AC-ID-003: Same-service overlap default

Given one non-terminal enrollment for a person and service, when an authorized user attempts another overlapping enrollment in the same service without an approved exception configuration, then the form and model reject it and no second enrollment is stored. Blocked by D-002.

### AC-ID-004: Different-service overlap allowed

Given one active enrollment, when an authorized user creates an enrollment for a different effective service offering on the same date, then creation succeeds without closing or changing the first enrollment.

### AC-ID-005: Optional personal identifier

Given a person without a personal identification number, when an authorized coordinator creates the identity with the required minimum data, then creation succeeds and reports the identifier as not provided, not zero or synthetic filler.

### AC-ID-006: Exact duplicate warning

Given an existing identity with an authorized normalized personal identifier, when an authorized coordinator submits the same normalized identifier for a new identity, then the system blocks automatic creation or routes it to restricted duplicate review without displaying the existing person's restricted details to an unauthorized user.

### AC-ID-007: Possible duplicate is never auto-merged

Given two records with similar name and birth date but no exact approved identifier match, when duplicate detection runs, then it creates a review candidate and does not merge, reassign, or disclose records automatically.

### AC-ID-008: Service assignment isolation

Given one person with two enrollments and a specialist assigned to only one, when the specialist opens the identity or guesses the other enrollment identifier, then only the assigned enrollment is returned and the other returns not found.

### AC-ID-009: Enrollment-owned contract

Given one identity with two enrollments, when a coordinator records an application or contract reference on one enrollment, then it is absent from the other enrollment and from the identity-level general fields.

### AC-ID-010: Identity-level attachment isolation

Given an identity document and a service-enrollment document, when a specialist has enrollment access but no identity-document permission, then the enrollment document follows its parent policy and the identity document is absent from list, timeline, template context, and direct download.

### AC-ID-011: Person and enrollment codes

Given one person has two service enrollments, when lists, cards, documents, and reports render, then person code and enrollment code follow D-039, are clearly labeled, remain stable through transfer and re-enrollment, and are never reused for another identity or episode.

## 3. Enrollment transitions, suspension, exit, and re-enrollment

### AC-ENR-001: Pending to Active

Given a Pending enrollment with an effective center placement, when an authorized coordinator activates it with an effective date, then the current state becomes Active and an append-only transition records old state, new state, effective date, actor, reason if required, and creation timestamp.

### AC-ENR-002: Active to Suspended

Given an Active enrollment, when it is suspended with an approved reason and effective date, then the current state is Suspended and prior visits, assessments, plans, goals, and assignments remain unchanged.

### AC-ENR-003: Suspended service event rejected

Given an enrollment suspended for a business date, when a user attempts to record a completed service event on that date without an approved correction exception, then form and model validation reject the event.

### AC-ENR-004: Suspended to Active

Given a Suspended enrollment, when an authorized coordinator resumes it, then the same enrollment becomes Active through a new state event and its prior episode history remains continuous.

### AC-ENR-005: Exit is terminal

Given an Active or Suspended enrollment, when it is exited with date and reason, then current placement and assignments close under the approved interval convention and routine actions cannot return the enrollment to Active.

### AC-ENR-006: Re-enrollment after exit

Given an Exited enrollment, when the person returns to the same service, then the system creates a new enrollment linked to the prior enrollment and does not change the old start date, exit date, state history, visits, assessments, plans, goals, or reports.

### AC-ENR-007: Cancelled application

Given a Pending enrollment that never started, when it is cancelled, then it requires the approved cancellation reason, becomes terminal, creates no first-service date, and is reported separately from an exited active case.

### AC-ENR-008: Invalid transition

Given an Exited or Cancelled enrollment, when any ordinary user posts a resume or activate command, then the server rejects it even if the user crafts the request directly.

### AC-ENR-009: Backdated transition impact preview

Given later service records or an approved timesheet, when a coordinator proposes a backdated suspension or exit affecting them, then the platform shows the impacted records, requires a reason, and does not finalize until the approved correction and reapproval rules are satisfied.

### AC-ENR-010: State history cannot be edited in place

Given a recorded state event, when an ordinary edit or delete request targets it, then the system denies the mutation. An approved correction creates compensating evidence rather than silently rewriting history.

### AC-ENR-011: Transition effective-date boundary

Given an enrollment changes state on an effective date, when records are created for the day before, the effective date, and the day after, then state eligibility follows D-035 exactly and screens and reports describe the convention consistently.

## 4. Center placement and transfer

### AC-TRF-001: Atomic transfer

Given an Active enrollment in Center A and an effective offering in Center B, when an authorized user transfers it effective on a date, then one transaction closes the Center A placement at that date and opens Center B at that date, with no date having zero or two current placements.

### AC-TRF-002: Destination offering required

Given Center B has no effective offering for the enrollment service on the proposed transfer date, when transfer is submitted, then it is rejected before any placement, assignment, schedule, or audit success state changes.

### AC-TRF-003: Event-time center preserved

Given service events before and after a transfer, when historical reports are run, then pre-transfer records remain attributed to Center A and post-transfer records to Center B.

### AC-TRF-004: Old center loses current card

Given a completed transfer, when a Center A coordinator requests the current enrollment card, destination schedule, or Center B record, then those current or destination scopes are unavailable.

### AC-TRF-005: Old center historical record access

Given a completed transfer and a pre-transfer event delivered in Center A, when a Center A coordinator opens that event through the approved historical workflow, then access follows D-006, reveals no later Center B content, and records any sensitive read.

### AC-TRF-006: Destination continuity history

Given a completed transfer, when an authorized Center B specialist opens the enrollment, then approved continuity records are visible according to D-005 and excluded record and attachment classes are not present in template context.

### AC-TRF-007: Incompatible future work

Given future Center A appointments or assignments, when transfer is proposed, then the system lists them and requires cancellation, reassignment, or an approved carry-forward action before completion.

### AC-TRF-008: No transfer through direct center edit

Given an existing enrollment, when a crafted form POST attempts to replace its current center without the transition service, then the server rejects the request and placement history remains unchanged.

## 5. Master data

### AC-MD-001: Stable code and bilingual labels

Given an authorized master-data steward, when a master value is published, then it has a unique stable code, English and Georgian labels or an approved translation status, effective dates, owner, and active or retired state.

### AC-MD-002: Published value cannot be deleted

Given a master value referenced by a transaction, when any user attempts hard deletion, then the database or service denies it and offers retirement or approved merge behavior.

### AC-MD-003: Historical label remains reproducible

Given a master label is renamed after a service event, when a historical report is rerun for the event date, then the approved historical label or transaction snapshot is reproduced and the current label change is traceable.

### AC-MD-004: Retired values unavailable for new records

Given a value retired before a new record's business date, when a form is loaded or a crafted POST uses it, then the value is unavailable for new selection but existing historical records continue to render.

### AC-MD-005: Municipality belongs to region

Given a municipality linked to Region A, when a submitted identity combines it with Region B, then form and model validation reject the mismatch.

### AC-MD-006: Other requires explanation

Given an enabled `Other` value, when a user selects it without the required note, then the record is not saved. When saved with a note, reporting distinguishes it from governed specific values.

### AC-MD-007: Multiple time-aware statuses

Given one person has several social statuses or diagnoses over time, when an authorized as-of report runs, then only values effective on the report date are counted and historical values remain available to authorized history views.

### AC-MD-008: Coordinator proposal does not publish

Given a coordinator may propose a new value, when they submit a proposal, then ordinary forms do not show it until an authorized steward publishes it and the proposal action is audited.

## 6. Age and age bands

### AC-AGE-001: Years and months display

Given a birth date and reference date exactly four years and six calendar months apart, when age is calculated, then the result is 4 years and 6 months.

### AC-AGE-002: Day before monthly anniversary

Given a reference date one day before the next monthly anniversary, when age is calculated, then the incomplete month is not counted.

### AC-AGE-003: Third birthday boundary

Given the approved default bands, when a child is one day before the 3rd birthday, then the age band is 0 to 35 months. On the 3rd birthday it is 36 to 59 months.

### AC-AGE-004: Fifth birthday boundary

Given the approved default bands, when a child reaches the 5th birthday, then the age band changes from 36 to 59 months to 60 to 83 months.

### AC-AGE-005: Seventh birthday boundary

Given the approved default bands, when a child reaches the 7th birthday, then the child is outside the early-intervention 0 to 6 years band and is not counted in 60 to 83 months.

### AC-AGE-006: Leap-day policy

Given a 29 February birth and a non-leap reference year, when the approved anniversary date is reached, then completed years and months change exactly according to D-011 and tests cover the day before and after.

### AC-AGE-007: Historical reference date

Given a service event from a prior year, when an event report calculates age, then it uses the event date rather than today's date.

### AC-AGE-008: Missing and future birth date

Given a missing birth date, when age is displayed or reported, then it is unknown and no age band is assigned. Given a future birth date, creation or update is rejected.

## 7. Service events

### AC-VIS-001: Separate dimensions

Given a home-delivered individual hygiene activity, when recorded, then activity is Hygiene Service, location is Beneficiary Home, delivery mode is In Person, and participation format is Individual. None is inferred by storing one combined label.

### AC-VIS-002: Remote event

Given a telephone guardian consultation, when recorded, then delivery mode is Telephone, participation format is Guardian Consultation, physical location may be Not Applicable, and the activity is independently selected.

### AC-VIS-003: One or more activities required

Given a completed ServiceEvent, when it has no active activity line, then formset and model or service validation reject it.

### AC-VIS-004: Multi-activity event

Given one encounter includes two approved activities, when saved, then one event and two activity lines exist, event count remains one, activity count is two, and payable time follows the approved non-duplication rule.

### AC-VIS-005: Assignment effective on event date

Given a specialist assignment starts after the proposed event date, when the specialist or coordinator submits that event, then both relationship choices and server validation reject it.

### AC-VIS-006: Placement effective on event date

Given an enrollment transfers on a date, when an event dated before transfer is posted with the destination center or after transfer with the source center, then it is rejected.

### AC-VIS-007: Cancelled units

Given any entered positive units, when the event is saved as Cancelled, then payable units are zero and summary calculations count it only as cancelled.

### AC-VIS-008: Monthly summaries by dimension

Given completed, cancelled, and no-show events across services and activities, when monthly summaries rebuild, then completed visits, service units, duration, distinct people, distinct enrollments, cancellations, and no-shows reconcile by specialist, center, service, activity, and month.

### AC-VIS-009: Concurrent writes

Given two concurrent completed events for the same specialist, center, and month, when both transactions commit, then the monthly summary contains both without lost update.

### AC-VIS-010: Approved-timesheet correction

Given an event is included in an approved timesheet, when an authorized correction changes date, center, activity, units, duration, specialist, or status, then the timesheet becomes invalid or reopens, payroll export is blocked, and reapproval is required.

### AC-VIS-011: Planned schedule is not actual delivery

Given an enrollment has a monthly schedule with planned home, center, or other service activities, when no completed ServiceEvent exists, then planned counts appear only in schedule and variance reports and completed visit, unit, timesheet, and payroll counts remain zero.

## 8. Assessment template versioning and scoring

### AC-ASM-001: Draft template editable

Given a draft AssessmentTemplateVersion with no completed assessment, when an authorized publisher edits its domains or rules, then the draft changes and an audit trail identifies the editor.

### AC-ASM-002: Published template immutable

Given a published version, when any user attempts to change an item, domain, formula, band, or validation rule in place, then the change is rejected and the UI offers a new draft version.

### AC-ASM-003: Historical result stable

Given an assessment recorded under version 1 and later publication of version 2, when the version 1 assessment is opened or its report is rerun, then response validation, score, category, and labels remain reproducible under version 1.

### AC-ASM-004: Effective template selection

Given two published versions with non-overlapping effective periods, when an assessment is created on a business date, then only the version effective and enabled for that service is selectable. A crafted invalid version is rejected.

### AC-ASM-005: Initial assessment chain

Given no earlier compatible assessment in the enrollment, when an Initial assessment is created, then no previous assessment is required and the cycle or sequence is derived.

### AC-ASM-006: Repeated and final assessment chain

Given a Repeated or Final purpose, when no earlier compatible assessment in the same enrollment is selected, then the assessment is rejected. An assessment from another enrollment or incompatible instrument cannot be linked.

### AC-ASM-007: Barthel band validation

Given a draft Barthel template with a scoring gap, overlap, duplicate boundary, or impossible range, when publication is attempted, then publication fails with specific validation errors. Blocked by D-015.

### AC-ASM-008: Barthel category calculation

Given approved bands and raw scores exactly on every lower and upper boundary, when assessments are scored, then each score maps to exactly one category and no valid score is unclassified.

### AC-ASM-009: AEPS assessed state

Given an AEPS domain marked Assessed, when the template requires a percentage and none is entered or the value is outside 0 through 100, then validation rejects it.

### AC-ASM-010: AEPS not assessed state

Given an AEPS domain marked Not Assessed, when a score is posted, then the server rejects or clears it according to the published rule and the domain is excluded from the assessed-domain count.

### AC-ASM-011: Instrument-specific behavior

Given Barthel and AEPS assessments, when they are validated and scored, then each uses its own response schema and scoring service. A generic total-score rule cannot accept an otherwise invalid instrument response.

### AC-ASM-012: Authorized override

Given a scoring rule permits an authorized override, when the approver changes the computed category, then the raw result, computed result, override result, reason, actor, and timestamp remain visible to authorized audit review.

### AC-ASM-013: Instrument-specific chains

Given one enrollment uses two approved instruments, when Initial, Repeated, and Final assessments are recorded, then each instrument lineage has its own chain or cycle, previous links never cross incompatible lineages, and finalization follows D-036.

## 9. Individual plans, goals, and outcomes

### AC-PLN-001: Enrollment-specific plan

Given one person has two services, when a plan is created for one enrollment, then its goals, reviews, and measurements are not visible in the other service unless a separately approved sharing rule exists.

### AC-PLN-002: Active plan requires goals

Given a plan with no valid goals, when a user attempts to activate or complete it, then form and service validation reject the transition.

### AC-PLN-003: Goal category required

Given an active plan goal, when it lacks an active GoalCategory enabled for the service, then it cannot be saved or activated.

### AC-PLN-004: Measurable goal fields

Given a goal, when its selected measurement type requires baseline, target, unit, or scale, then missing or incompatible fields are rejected according to the category or template rule.

### AC-PLN-005: Dated outcome measurement

Given an active goal, when a specialist records progress, then a new GoalOutcomeMeasurement stores date, value or rating, scale, notes, recorder, and optional source assessment without overwriting prior measurements.

### AC-PLN-006: Derived category totals

Given goals in several categories and statuses, when counts are displayed, then total, achieved, and in-progress counts equal source goals as of the named date and cannot be edited directly.

### AC-PLN-007: Overall condition is separate

Given goal outcomes, when a plan review records Improved, Stable, or Worsened, then the conclusion requires rationale and review date and is not silently derived from the percentage of achieved goals.

### AC-PLN-008: Goal-count rule

Given the owner-approved interpretation of 7 to 12, when a plan is activated, then the system enforces a blocker, warning, or no rule exactly as D-017 specifies and tests all boundaries.

### AC-PLN-009: Goal status history

Given a goal moves from Planned to In Progress to Achieved, when history is reviewed, then each transition date, actor, reason where required, and outcome evidence remains available.

### AC-PLN-010: Active-plan concurrency

Given an enrollment already has an Active plan, when another plan is activated, then the platform supersedes or closes the prior plan atomically or rejects the action according to D-037. It never leaves an unapproved number of Active plans.

## 10. Assignment dates and authorization

### AC-AUTH-001: Current access requires current assignment

Given an assignment effective today and all other role and center conditions valid, when a specialist opens the enrollment, then access succeeds. Given the assignment starts tomorrow or ended before today, current card access returns not found.

### AC-AUTH-002: Current assignee continuity history

Given a current assignment starts after earlier approved enrollment records, when the specialist opens the card, then the approved continuity subset is visible according to D-019 and unrelated-service or excluded-class content is absent.

### AC-AUTH-003: Ended assignment removes routine access

Given a specialist authored prior records and the assignment has ended, when the specialist opens the enrollment, timeline, source record, or attachment through routine URLs, then authorship alone does not preserve access.

### AC-AUTH-004: Historical correction request

Given a former assignee is inside the approved correction window, when they request correction to their own service event, then the request exposes only the minimum record fields and routes to an authorized coordinator without reopening full card access.

### AC-AUTH-005: Correction outside window

Given a former assignee is outside the correction window, when they attempt correction, then the request is denied or routed to the approved exceptional process and the denial is auditable.

### AC-AUTH-006: Future-dated record assignment

Given a current assignment ends before a future planned service date, when a completed or scheduled record is posted for that later date, then effective-date validation rejects it.

### AC-AUTH-007: Coordinator center scope

Given a coordinator has Center A membership only, when they list, search, filter, report, export, post, or download a Center B identifier, then no Center B row or restricted error detail is returned.

### AC-AUTH-008: Central HR case isolation

Given a user has only Central HR role, when they request beneficiary lists, identities, enrollments, visits, assessments, plans, goals, timelines, or case attachments, then access is forbidden or not found and no case data enters template context.

### AC-AUTH-009: Central HR staff access

Given Central HR role, when the user opens staff, contract, employment, approved-timesheet, or payroll-safe views, then organization-wide access follows the approved HR field allowlist and sensitive reads are audited.

### AC-AUTH-010: System Manager policy

Given the approved D-023 policy, when a System Manager attempts a sensitive read, routine clinical edit, hard delete, or break-glass action, then each action is allowed, denied, or elevated exactly as approved and is audited with no case values in metadata.

### AC-AUTH-011: Restricted diagnosis and notes

Given note and diagnosis classifications, when an assigned specialist opens the enrollment, then only approved service-relevant values are retrieved. Hidden values do not appear in HTML, form errors, CSV, logs, or normalized timeline entries.

### AC-AUTH-012: Inactive staff revocation

Given an inactive or finished staff profile, when the user still has a Django session and role group, then non-manager center, assignment, case, timesheet, report, and download access is revoked.

### AC-AUTH-013: Selector consistency

Given any out-of-scope enrollment or event, when tested through list, detail, relationship choice, crafted POST, report filter, export, timeline, attachment list, and download, then every path denies the same scope.

### AC-AUTH-014: Primary specialist responsibility

Given an Active enrollment that requires specialist delivery, when assignments are changed, then current Primary and Secondary assignment counts follow D-038, effective intervals do not create conflicting primary responsibility, and an assignment role never exposes another service.

## 11. Specialist landing page and beneficiary card

### AC-UI-001: Specialist landing

Given a specialist-only user with one accessible center, when login completes, then the user lands on the assigned beneficiary enrollment list without passing through the generic dashboard. Blocked by D-024.

### AC-UI-002: Multi-center specialist selection

Given a specialist has two accessible centers, when login completes without a valid session center, then the user selects a center and is sent to assigned enrollments in that center only.

### AC-UI-003: Mixed-role landing

Given a user has Coordinator and Specialist roles, when login completes, then landing and workspace switching follow D-024 without merging or widening authorization.

### AC-UI-004: Beneficiary list minimum fields

Given assigned enrollments, when the specialist list renders, then it shows safe person name and internal code, service, enrollment status, age in years and months, and approved due-work indicators, while personal identifier, full address, contact, contract, hidden diagnoses, other services, and attachments remain absent.

### AC-UI-005: Enrollment context visible

Given one identity with two enrollments, when a user switches enrollment on the card, then service, center, status, actions, records, and timeline update to the selected enrollment and the current context remains visibly labeled.

### AC-UI-006: Quick actions respect effective access

Given an Active enrollment and current assignment, when the card renders, then authorized new event, assessment, plan, and measurement actions appear. Given Suspended, Exited, future assignment, or ended assignment, disallowed actions are absent and direct POST is denied.

### AC-UI-007: Bilingual and accessible workflow

Given English and Georgian locales at supported mobile and desktop widths, when the specialist list and card are navigated by keyboard, then headings, labels, status text, focus, errors, enrollment switcher, tables, and actions remain usable and no page-level overflow hides content.

## 12. Timesheets

### AC-TS-001: Center-month separation

Given a specialist completes eligible events in two centers during one month, when timesheets are generated, then two timesheets exist, one per center, and each contains only that event-time center's eligible lines.

### AC-TS-002: Draft derived from source events

Given completed, cancelled, no-show, and ineligible events, when a draft timesheet is built, then only approved eligible completed activity units appear and totals reconcile to source events.

### AC-TS-003: Payroll-safe content

Given a Central HR user opens an approved timesheet, then lines include only approved staff, center, month, pay or activity code, units, and approval evidence. Beneficiary name, code, identifier, diagnosis, status, notes, and filenames are absent from query results and output.

### AC-TS-004: Specialist submits own only

Given a draft timesheet, when its specialist submits it, then the state becomes Submitted with timestamp and source digest. Another specialist cannot submit it through a direct POST.

### AC-TS-005: Coordinator center approval

Given a Submitted timesheet for Center A, when an authorized Center A coordinator approves it, then the state becomes Approved with approver, timestamp, totals, and source digest. A Center B coordinator cannot view or approve it.

### AC-TS-006: No self-approval

Given the submitter and proposed approver are the same person, when approval is posted, then the server rejects it regardless of UI visibility.

### AC-TS-007: Alternate approver

Given a center has no independent coordinator approver, when a designated organization-level service approver acts, then approval succeeds only under the configured scope and is visibly distinguished from ordinary center approval.

### AC-TS-008: Return for correction

Given a Submitted or Approved timesheet, when a permitted approver or Central HR returns it with a reason, then the state becomes Returned, payroll export is blocked, and source events remain editable only through their authorized workflows.

### AC-TS-009: Source change invalidates approval

Given an Approved timesheet, when an included source event changes a payroll-relevant field, then the approval digest no longer matches, the timesheet reopens or becomes Invalidated according to the approved state model, and reapproval is required.

### AC-TS-010: Lock and export

Given an Approved timesheet, when Central HR locks and exports it, then export records format, row count, timesheet IDs or digest, actor, and timestamp without beneficiary data. An unapproved or invalidated timesheet cannot be exported.

## 13. Reporting, privacy, and audit

### AC-REP-001: Counting unit labeled

Given a dashboard or report total, when it renders, then it states whether the value counts people, enrollments, events, assessments, goals, or timesheets and links to a reproducible filter where applicable.

### AC-REP-002: As-of enrollment status

Given an enrollment that was Active, then Suspended, then Active, when reports run at dates inside each interval, then the enrollment appears in the correct status for each as-of date.

### AC-REP-003: Transfer reporting

Given a transfer, when reports run for source and destination centers, then transferred-out and transferred-in counts reconcile and service events remain under their event-time center.

### AC-REP-004: Simultaneous services

Given one person with two active services, when an active-person report runs, then distinct people equals one and active enrollments equals two.

### AC-REP-005: Age reference stated

Given an age-band report, when it renders or exports, then it states the reference date and applies the same years, months, and band rule to screen and CSV.

### AC-REP-006: Assessment version reported

Given assessments under several template versions, when results are reported, then instrument and version are explicit and incompatible versions are not combined without an approved comparison rule.

### AC-REP-007: Outcome report

Given goals and measurements, when an outcome report runs, then it distinguishes current goal status, measured change, category, plan review conclusion, and missing measurement.

### AC-REP-008: Row export authorization

Given a report, when a user exports it, then the base authorized selector is applied before filters, hidden fields remain excluded, formula-leading values are neutralized, and export is audited.

### AC-REP-009: Sensitive aggregate disclosure

Given a cross-center diagnosis, social-status, or narrow-geography report with a cell below the approved threshold, when shown or exported, then the disclosure control in D-034 applies consistently and explains suppressed values without revealing them.

### AC-REP-010: Audit metadata minimization

Given sensitive reads, transitions, transfers, assignment changes, template publications, overrides, timesheet decisions, exports, and downloads, when audit events are inspected, then they identify action, actor, target identifier, center where relevant, outcome, and safe metadata without names, personal identifiers, diagnosis text, notes, filenames, or content.

### AC-REP-011: Direct download authorization

Given a valid attachment identifier outside the user's current parent scope, when downloaded directly, then the response is not found or forbidden according to policy, the denial is audited, and neither storage path nor original filename is disclosed in the denial.

### AC-REP-012: Logging boundary

Given searches, filters, form submissions, and downloads containing synthetic sensitive markers, when application, proxy, and error logs are inspected, then request bodies, query strings, beneficiary values, filenames, credentials, and session values are absent.

## 14. Migration acceptance

### AC-MIG-001: Current beneficiary split

Given each current synthetic Beneficiary, when migration runs, then exactly one identity, one service enrollment, and one initial center placement are created unless an approved duplicate crosswalk says otherwise.

### AC-MIG-002: UUID crosswalk

Given every current record, when migration completes, then a controlled crosswalk maps old UUID to target identity, enrollment, and transactional UUIDs and no source record silently disappears.

### AC-MIG-002A: Staff center-role migration

Given current staff memberships, role groups, and specialist center assignments, when migration runs, then effective StaffCenterRoleAssignments preserve supported current scope and primary-center meaning. Missing historical dates are reported and are not silently invented.

### AC-MIG-002B: Beneficiary-code migration

Given current beneficiary codes, when migration runs, then every original code is preserved as the approved person code, enrollment code, or legacy alias under D-039, and external reconciliation can resolve the old code without exposing another person's record.

### AC-MIG-003: Assignment migration

Given current assignments with dates, when migrated, then they become enrollment assignments, preserve role and dates, and satisfy approved effective-authorization rules. Ambiguous or invalid dates enter an exception report.

### AC-MIG-004: Visit mapping

Given a current combined visit type that does not determine activity, location, mode, and format, when migrated, then approved values are mapped and unresolved dimensions use a visible legacy-unclassified code. The migration does not invent a physical location.

### AC-MIG-005: Assessment mapping

Given current assessments and free-text domains, when migrated, then each assessment references a legacy template version, raw fields remain recoverable, and unambiguous domain mappings are separated from review-required values.

### AC-MIG-006: Diagnosis narrative

Given current diagnosis or status text, when migrated, then it remains restricted legacy narrative unless an approved deterministic mapping exists. The process does not infer codes from ambiguous text.

### AC-MIG-007: Goal category migration

Given current free-text goals, when migrated, then each remains linked to its plan and uses `unclassified legacy` until an authorized review assigns a category.

### AC-MIG-008: Attachment classification

Given current beneficiary attachments, when migration runs, then deterministic categories follow D-029 and ambiguous files enter restricted review. Files are not duplicated into identity and enrollment scopes by default.

### AC-MIG-009: Summary rebuild

Given migrated service events, when summaries rebuild, then totals reconcile to source counts by center, specialist, month, status, units, and duration within approved tolerances. Imported derived summaries are not treated as authoritative.

### AC-MIG-010: Authorization before cutover

Given migrated synthetic data, when every role and date-boundary scenario is exercised across list, detail, POST, report, export, timeline, and file, then no broader access exists than the approved target policy.

### AC-MIG-011: Rollback rehearsal

Given a disposable staging migration, when rollback is invoked within the planned window, then prior application revision, database shape, private files, and access behavior are restored consistently and reconciliation evidence is retained without sensitive content.

### AC-MIG-012: No obsolete-field removal before sign-off

Given target reads and writes are enabled, when stabilization and owner reconciliation have not completed, then cleanup migration cannot remove current source fields or crosswalks.

## 15. Later-phase acceptance gates

### AC-LATER-001: Payroll phase boundary

Given casework and timesheets are complete, when payroll work begins, then a separate approved specification defines rates, taxes, deductions, currencies, retroactivity, approvals, accounting output, retention, and statutory review before payroll calculation code is accepted.

### AC-LATER-002: Payroll traceability

Given a later payroll result, when audited, then every amount traces to an approved locked timesheet, an effective pay-rule version, and an approval event without beneficiary data.

### AC-LATER-003: Inventory isolation

Given a warehouse user in the later inventory phase, when stock is issued with an enrollment reference, then the user sees only the minimum issue reference and cannot open the beneficiary card, diagnosis, notes, assessments, plans, or private files.

### AC-LATER-004: Inventory reconciliation

Given receipts, issues, transfers, returns, adjustments, and counts, when inventory is reconciled, then item, lot, expiry, warehouse, unit, and movement totals balance under the approved negative-stock and expiry rules.

### AC-LATER-005: Asset lifecycle

Given an asset in the later asset phase, when its history is reviewed, then acquisition, identifiers, location, custody, condition, maintenance, transfer, loss, and disposal are auditable and financial calculations follow approved finance rules.

### AC-LATER-006: Broader ERP scope

Given donor, grant, volunteer, accounting, budgeting, project, or expense requests from the secondary DOCX, when implementation is proposed, then each has a separately approved bounded-context specification and is not accepted through the casework criteria alone.

## 16. Production acceptance gate

The platform shall not be accepted for real beneficiary data until all of the following are true:

- Mandatory decisions for the launch scope are approved and evidenced.
- Role-specific business UAT passes with synthetic data.
- Native Georgian and accessibility review pass.
- Full automated tests, Ruff lint and formatting, Django checks, deployment checks, and migration drift checks pass on the release candidate.
- PostgreSQL integration, concurrency, capacity, migration, backup, and restore rehearsals pass.
- External security review and threat model findings are resolved or formally accepted.
- Approved MFA or compensating access control, TLS, trusted proxy, SMTP, monitoring, alerting, audit review, malware handling, dependency scanning, patching, and incident response are operational.
- Retention, correction, export, erasure, deletion, legal hold, backup reconciliation, and privacy-request procedures are approved.
- Encrypted off-host backup ownership, retention, RPO, RTO, key custody, and observed restore evidence are recorded.
- Real-data migration scope, reconciliation thresholds, cutover, rollback, temporary-data disposal, and final approval are signed by named owners.

Feature completeness or a successful synthetic demonstration alone is not production acceptance.
