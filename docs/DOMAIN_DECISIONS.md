# Domain Decisions

Status: proposed decision register

This register contains unresolved business questions discovered from the primary requirements DOCX, the secondary NGO ERP DOCX, the current repository, and the existing independent review. A recommendation is not approval. Items marked mandatory shall be approved by the named owner before the dependent behavior is implemented.

## 1. Decision status and ownership

| Status | Meaning |
|---|---|
| Open, mandatory | Engineering may design around the boundary but shall not finalize the affected behavior before owner approval |
| Open, non-mandatory | Engineering may adopt the recommended default unless the owner objects during specification review |
| Approved | The named owner has accepted the decision and approval evidence is linked |
| Superseded | A later decision replaces this item without deleting its history |

Recommended decision owners:

- Service Owner: program policy, enrollment, transfer, assessment, goals, and workflow
- Privacy and Security Owner: access, restricted data, retention, and production safeguards
- HR and Finance Owner: staff, timesheet, payroll, separation of duties, and statutory rules
- Clinical or Technical Program Owner: assessment instruments, scoring, and outcome meaning
- Data Governance Owner: master data, codes, historical labels, and migration mapping
- System Owner: System Manager powers, production operation, and emergency access

## 2. Open decisions

### D-001: How is one person identified across services and centers?

Status: Open, mandatory

Recommended default: Use one organization-wide BeneficiaryIdentity with a non-meaningful internal person code. Keep personal identification number optional, encrypted, and exact-matchable through a keyed normalized hash. Send possible duplicates to restricted human review and never auto-merge.

Alternatives:

1. Create a new person record for every service or center.
2. Require personal identification number as the universal key.
3. Use probabilistic automatic merging based on name, birth date, and contact data.

Security and operational consequences: Separate records create duplicate histories, inaccurate unique-person reports, and unsafe fragmented care. A required government identifier excludes people without usable documentation and increases breach impact. Automatic matching can merge two people and disclose one person's records to another service team. The recommended model adds a controlled merge-review workload and requires an encryption and key-management design.

Owner approval mandatory before implementation: Yes. Service Owner and Privacy and Security Owner.

### D-002: May the same person have overlapping enrollments in the same service?

Status: Open, mandatory

Recommended default: Permit simultaneous enrollments in different services. Prohibit overlapping non-terminal enrollments for the same person and service unless a specific service configuration explicitly allows it.

Alternatives:

1. Prohibit all simultaneous services.
2. Permit unlimited overlap, including the same service at several centers.
3. Model center participation as separate enrollments even during a transfer.

Security and operational consequences: Prohibiting all overlap contradicts multidisciplinary service delivery. Unlimited same-service overlap risks duplicate payment, conflicting plans, and unclear center accountability. Separate transfer enrollments fragment assessment and plan history. Configured exceptions require clear reporting and approval rules.

Owner approval mandatory before implementation: Yes. Service Owner.

### D-003: Which enrollment states and transitions are authoritative?

Status: Open, mandatory

Recommended default: Use Pending, Active, Suspended, Exited, and Cancelled. Exit and cancellation are terminal. Resumption returns Suspended to Active. Re-enrollment after exit creates a new enrollment linked to the prior episode.

Alternatives:

1. Use only Active, Suspended, and Completed exactly as listed in the source evidence.
2. Reopen an exited enrollment when a person returns.
3. Add separate Referred, Waitlisted, Declined, and Discharged states in the first release.

Security and operational consequences: Too few states conceal applications that never started. Reopening an exited episode rewrites historical duration and performance reporting. More states improve operational detail but increase transition rules, training, migration, and reporting complexity.

Owner approval mandatory before implementation: Yes. Service Owner.

### D-004: What does a center transfer do to the enrollment?

Status: Open, mandatory

Recommended default: Keep one enrollment, close the prior center placement, and open the destination placement atomically on the transfer effective date. Use inclusive `valid_from` and exclusive `valid_to` intervals.

Alternatives:

1. Exit at the old center and create a new enrollment at the new center.
2. Change the center field in place and do not retain placement history.
3. Allow two current center placements during a transition period.

Security and operational consequences: Exit plus re-enrollment fragments continuity and may falsely increase intake and exit counts. In-place change destroys accountability for prior events. Overlapping current centers expands access and makes timesheet approval ambiguous. The recommended model requires an atomic transfer service and event-time center snapshots.

Owner approval mandatory before implementation: Yes. Service Owner and Data Governance Owner.

### D-005: How much prior history does the destination center receive after transfer?

Status: Open, mandatory

Recommended default: The destination coordinator and currently assigned destination specialists may read the transferred enrollment's care-relevant history, including assessments, plans, goals, and service summaries. Identity documents, unrelated enrollments, internal old-center notes, and HR information remain excluded unless separately authorized.

Alternatives:

1. Show the complete enrollment history and every attachment.
2. Show only records created after transfer.
3. Provide a coordinator-authored transfer summary instead of source records.

Security and operational consequences: Complete sharing can overexpose internal or identity evidence. Post-transfer-only access can impair safe continuity. A transfer summary minimizes disclosure but may omit necessary details and adds preparation burden. The recommended boundary requires record and attachment classifications and carefully tested selectors.

Owner approval mandatory before implementation: Yes. Service Owner and Privacy and Security Owner.

### D-006: What historical access remains at the old center?

Status: Open, mandatory

Recommended default: Old-center coordinators retain read and correction authority only for records whose event-time center is their center, subject to retention and approval rules. They lose the current enrollment card, future schedule, destination assignments, and new-center records.

Alternatives:

1. Remove all access immediately after transfer.
2. Preserve full enrollment access indefinitely.
3. Preserve read-only access for a fixed transition period, then remove it.

Security and operational consequences: Immediate removal impairs audit, reconciliation, and timesheet correction. Full access violates least privilege after responsibility ends. A fixed period is simpler but may conflict with audit or funding cycles. Event-time scope is more precise but increases selector and test complexity.

Owner approval mandatory before implementation: Yes. Service Owner and Privacy and Security Owner.

### D-007: Who owns and publishes master data?

Status: Open, mandatory

Recommended default: Appoint a Data Governance Owner. Coordinators may propose values, but only an authorized data steward or System Manager acting as steward may publish, retire, merge, or correct codes. Published values are never hard-deleted.

Alternatives:

1. Let every coordinator create values directly.
2. Let only developers change fixtures or migrations.
3. Centralize every proposal and publication with the Service Owner.

Security and operational consequences: Decentralized creation produces duplicate and inconsistent reporting values. Developer-only maintenance is slow and puts business meaning outside accountable ownership. Full service-owner control may become a bottleneck. A steward workflow requires audit, bilingual labels, and change review.

Owner approval mandatory before implementation: Yes. Data Governance Owner and Service Owner.

### D-008: Which source is authoritative for regions and municipalities?

Status: Open, mandatory

Recommended default: Load a versioned, owner-approved official Georgian geographic list with stable codes and Region to Municipality hierarchy. Retire superseded entries without rewriting historical records.

Alternatives:

1. Continue free-text region and municipality fields.
2. Maintain an SSK-specific list without source versioning.
3. Use a live third-party geography API.

Security and operational consequences: Free text produces duplicates and poor reporting. An unversioned internal list cannot explain historical boundary changes. A live API introduces availability, privacy, and uncontrolled-change risks. A versioned list requires a refresh and mapping process.

Owner approval mandatory before implementation: Yes. Data Governance Owner.

### D-009: How are diagnosis and social status represented and protected?

Status: Open, mandatory

Recommended default: Allow multiple effective-dated coded values plus restricted notes and verification status. Link them to the person, with optional enrollment relevance. Keep household or marital status separate from diagnosis and social-support eligibility. Specialists receive only values needed for their assigned service. Aggregate reports apply disclosure controls.

Alternatives:

1. Keep one free-text diagnosis or status field.
2. Store values only on each enrollment.
3. Give every assigned specialist all person-level diagnosis and social status history.

Security and operational consequences: One text field is difficult to validate and report. Enrollment-only storage duplicates person-level evidence and can diverge. Full visibility increases exposure of highly sensitive data across unrelated services. The recommended model needs classification, field-level permissions, and a cross-service purpose rule.

Owner approval mandatory before implementation: Yes. Service Owner and Privacy and Security Owner.

### D-010: What exactly are the SSK early-intervention age bands?

Status: Open, mandatory

Recommended default: Define 0 to 35 completed months, 36 to 59 completed months, and 60 to 83 completed months. A beneficiary leaves the early-intervention band on the 7th birthday. Display age as completed years and remaining completed months.

Alternatives:

1. Treat the labels 0-3, 3-5, and 5-7 as inclusive at both ends.
2. Use completed whole years only.
3. Use funding-program-specific age bands with no organization-wide default.

Security and operational consequences: Inclusive boundaries overlap at ages 3 and 5. Whole years cannot provide the requested month precision and may misclassify eligibility near boundaries. Program-specific bands are flexible but complicate organization-wide reports and UI. The recommended boundaries are deterministic but require confirmation against SSK policy and funder rules.

Owner approval mandatory before implementation: Yes. Service Owner.

### D-011: How are 29 February births handled in years-and-months age?

Status: Open, mandatory

Recommended default: In a non-leap year, treat the last day of February as the anniversary for completed-year and completed-month calculation.

Alternatives:

1. Treat 1 March as the anniversary.
2. Use raw day-of-month subtraction, which may show one month less on 28 February.

Security and operational consequences: The choice can change eligibility or age-band results for a small number of people. A consistent documented rule is necessary for reproducible reporting. The implementation needs tests for leap and non-leap reference years.

Owner approval mandatory before implementation: Yes. Service Owner.

### D-012: Can one service event contain several activities?

Status: Open, mandatory

Recommended default: Use a ServiceEvent header with one or more activity lines. Keep location, delivery mode, and participation format on the header. Prevent overlapping or duplicated payable time unless an approved unit rule permits it.

Alternatives:

1. Require exactly one activity per event.
2. Keep one combined visit-type choice as in the current MVP.
3. Create a separate event for every activity performed during the same encounter.

Security and operational consequences: One activity is simple but can underreport multidisciplinary work. One combined choice prevents reliable location and modality reporting. Multiple events can double count visits and time. Activity lines require clear payroll and reporting aggregation rules.

Owner approval mandatory before implementation: Yes. Service Owner and HR and Finance Owner.

### D-013: Which visit dimensions and values are required?

Status: Open, mandatory

Recommended default: Record activity, physical location, delivery mode, and participation format as separate dimensions. Seed the source-evidence activities and locations as governed master data. Require a note for Other.

Alternatives:

1. Use activity plus a single free-text description.
2. Combine individual, group, guardian consultation, remote, and location in one list.
3. Make every dimension optional.

Security and operational consequences: Free text and compound lists reduce analytics and increase inconsistent payroll mapping. Optional dimensions create incomplete donor and service reports. More required fields increase specialist data-entry time, so defaults and service-specific applicability must be designed carefully.

Owner approval mandatory before implementation: Yes. Service Owner.

### D-014: How are assessment templates versioned and corrected?

Status: Open, mandatory

Recommended default: Draft versions are editable. Published versions are immutable. A scoring or item change creates a new version. A published version may be withdrawn for future use but remains available for historical rendering. Corrections to completed assessments create an audited revision or amendment, not a silent template mutation.

Alternatives:

1. Edit the active template in place.
2. Store the whole template as ungoverned JSON on each assessment.
3. Allow deletion of unused and used versions.

Security and operational consequences: In-place edits make past scores irreproducible. Ungoverned JSON is flexible but weakens validation and reporting. Deletion breaks historical records. Immutable versions add publication workflow and migration effort but provide defensible results.

Owner approval mandatory before implementation: Yes. Clinical or Technical Program Owner and Data Governance Owner.

### D-015: What are the approved Barthel scoring bands?

Status: Open, mandatory

Recommended default: Do not publish the source ranges as-is because they contain gaps and an ambiguous boundary. Use a provisional continuous configuration of 0-65, 66-75, 76-95, and 96-100 only after the clinical owner confirms that it reflects the intended instrument and labels.

Alternatives:

1. Reproduce the source ranges literally, including 70-75, 80-95, and greater than 95.
2. Store the raw score only and do not compute a category.
3. Adopt an externally referenced standard after a separate evidence review.

Security and operational consequences: Literal ranges leave some values unclassified and may overlap policy meaning. Raw-only storage avoids an incorrect clinical label but cannot meet category reporting needs. External standards may not match SSK's intended local use. Incorrect scoring can affect service decisions and reports.

Owner approval mandatory before implementation: Yes. Clinical or Technical Program Owner.

### D-016: Are old AEPS and new AEPS separate instruments or versions, and what do their domain values mean?

Status: Open, mandatory

Recommended default: Model one AEPS instrument lineage with distinct published old and new template versions when cross-version lineage is clinically valid. Each version defines its own domains, assessed or not-assessed rules, percentage requirements, and scoring formulas. Do not compare scores across versions unless the owner approves a conversion rule.

Alternatives:

1. Treat old and new AEPS as unrelated instruments.
2. Use one template with a free-text version label.
3. Force the same domains and total-score formula across both.

Security and operational consequences: Separate instruments reduce unsafe comparison but can fragment reporting. A free-text label is error-prone. Forced equivalence can produce clinically invalid trends. Versioned lineage needs exact domain definitions and comparison policy.

Owner approval mandatory before implementation: Yes. Clinical or Technical Program Owner.

### D-017: Which goal categories are authoritative, and is 7 to 12 a goal-count rule?

Status: Open, mandatory

Recommended default: Seed the five categories in the primary DOCX as early-intervention GoalCategory values. Treat 7 to 12 as an unapproved program recommendation and do not enforce it until the owner clarifies whether it is a minimum, maximum, range, or reference to numbered source items.

Alternatives:

1. Hard-require every active plan to have 7 through 12 goals.
2. Keep free-text goals without categories.
3. Require at least one goal in every category.

Security and operational consequences: An incorrect hard limit may block legitimate plans or encourage meaningless goals. Free text weakens outcome reporting. One-per-category may not fit each beneficiary. Configurable categories and warnings require service-specific validation.

Owner approval mandatory before implementation: Yes. Service Owner.

### D-018: How is goal achievement measured?

Status: Open, mandatory

Recommended default: Each goal declares a baseline, indicator, measurement type or scale, target, and review date. Dated GoalOutcomeMeasurements provide evidence. Goal status is set through a reviewed workflow. Improved, stable, or worsened is a separate plan-review conclusion with rationale.

Alternatives:

1. Use status only, with no measured values.
2. Derive condition automatically from the proportion of achieved goals.
3. Require every goal to use a numeric percentage.

Security and operational consequences: Status-only records are subjective and hard to audit. Automatic condition inference can misrepresent complex cases. Numeric-only measurement excludes qualitative outcomes. The recommended mixed model takes more configuration and specialist training.

Owner approval mandatory before implementation: Yes. Service Owner and Clinical or Technical Program Owner.

### D-019: How do assignment dates affect current and historical specialist access?

Status: Open, mandatory

Recommended default: Use inclusive `valid_from` and exclusive `valid_to` intervals for staff center roles and enrollment specialist assignments. Current card access requires an assignment effective today. Record creation and edit require an assignment effective on the record's business date. A currently assigned specialist may read the approved continuity history of that enrollment, including records before assignment. Ending the assignment removes routine card access.

Alternatives:

1. Ignore assignment dates, matching current MVP behavior.
2. Let a specialist see only records dated inside their assignment interval.
3. Preserve access forever to any record authored by the specialist.

Security and operational consequences: Ignoring dates leaves access after responsibility ends. Date-sliced history impairs continuity. Lifetime author access exposes transferred or closed cases indefinitely. The recommended rule is least-privilege for current work but needs a separate correction path for historical records.

Owner approval mandatory before implementation: Yes. Service Owner and Privacy and Security Owner.

### D-020: How can a former assignee correct a historical service record?

Status: Open, mandatory

Recommended default: Do not restore full beneficiary-card access. Permit an audited correction request for the former specialist's own event within an approved correction window. A current coordinator reviews and applies or approves the change. Approved or exported timesheets must be reopened and reapproved.

Alternatives:

1. No former-assignee corrections.
2. Former assignees retain read and edit access indefinitely.
3. A coordinator makes every correction without specialist input.

Security and operational consequences: No correction path leaves known errors. Indefinite access violates least privilege. Coordinator-only editing may weaken authorship accountability. A correction request adds workflow and requires a decision on the allowable window.

Owner approval mandatory before implementation: Yes. Service Owner, Privacy and Security Owner, and HR and Finance Owner.

### D-021: Should assigned specialists see diagnosis and case notes?

Status: Open, mandatory

Recommended default: Make diagnosis and notes separately classifiable. Show only service-relevant diagnosis values and care notes to a currently assigned specialist. Hide unrelated-service notes, identity verification evidence, and restricted social-status detail.

Alternatives:

1. Preserve the current MVP rule that diagnosis and case notes are visible to assigned specialists.
2. Hide all diagnosis and notes from specialists.
3. Let coordinators mark each individual note as shareable.

Security and operational consequences: Full visibility may overexpose sensitive data. No visibility can impair service delivery. Per-note classification offers precision but increases author burden and the risk of incorrect labels. The recommended model needs safe defaults and clear note types.

Owner approval mandatory before implementation: Yes. Service Owner and Privacy and Security Owner.

### D-022: What is the Central HR role?

Status: Open, mandatory

Recommended default: Create a distinct `SSK Central HR` role. It may manage organization-wide staff profiles, contracts, employment status, HR documents, approved timesheet totals, and payroll-safe exports. It has no beneficiary list, identity, diagnosis, note, assessment, plan, or attachment access.

Alternatives:

1. Continue assigning individual Django staff permissions without a named role.
2. Give HR System Manager access.
3. Let center coordinators manage all HR records for their center.

Security and operational consequences: Ad hoc permissions are harder to review. System Manager gives excessive case access. Coordinator HR scope can expose contracts and fragment employment records. A named role improves review but requires migration of current permissions and separation of HR from case selectors.

Owner approval mandatory before implementation: Yes. HR and Finance Owner and Privacy and Security Owner.

### D-023: What routine powers does System Manager have over case content?

Status: Open, mandatory

Recommended default: System Manager administers users, roles, centers, master data, configuration, and audit. Organization-wide sensitive case reads are audited. Routine clinical edits and hard deletion require explicit case-administration permission or time-limited break-glass elevation rather than being inherent forever.

Alternatives:

1. Preserve unrestricted read, edit, and delete access for every System Manager.
2. Remove all case access from System Manager.
3. Split the role into Security Administrator, Data Administrator, and Case Administrator immediately.

Security and operational consequences: Unrestricted access concentrates privacy and integrity risk. No case access can block support and recovery. Immediate full role split is strongest but operationally heavier for a small organization. Break-glass controls need approval logging and periodic review.

Owner approval mandatory before implementation: Yes. System Owner and Privacy and Security Owner.

### D-024: What is the specialist's post-login landing page and mixed-role precedence?

Status: Open, mandatory

Recommended default: A specialist-only user lands on assigned beneficiary enrollments after center selection. Coordinators and System Managers land on the aggregate dashboard. A user holding Coordinator and Specialist defaults to the coordinator dashboard but can enter a clearly labeled specialist workspace.

Alternatives:

1. Send every role to the generic dashboard.
2. Send any user with Specialist role to the beneficiary list, even if also a coordinator.
3. Ask mixed-role users to choose a workspace after every login.

Security and operational consequences: A generic dashboard does not match the source workflow and slows routine work. Specialist precedence can hide coordinator responsibilities. Repeated workspace selection adds friction. Role-aware landing must not change authorization scope.

Owner approval mandatory before implementation: Yes. Service Owner.

### D-025: How is a multi-service beneficiary shown on the beneficiary card?

Status: Open, non-mandatory

Recommended default: Show one identity header and separate enrollment switcher rows. Keep service status, center, assignment, visits, assessments, plans, and documents inside the selected enrollment. Do not aggregate sensitive case content across services by default.

Alternatives:

1. Show separate duplicate-looking cards for each enrollment.
2. Combine all services into one timeline and one plan area.
3. Use an identity page only for coordinators and separate cards for specialists.

Security and operational consequences: Separate cards can confuse identity and duplicate-person counts. A combined timeline risks cross-service disclosure and unclear ownership. Role-specific layouts improve minimization but increase UI and test complexity. The recommended switcher makes context explicit.

Owner approval mandatory before implementation: No. The Service Owner should confirm during prototype review.

### D-026: Where is the timesheet approval boundary?

Status: Open, mandatory

Recommended default: One specialist, center, and month per timesheet. The specialist submits. An authorized coordinator for that center approves service truth. Central HR consumes approved payroll-safe totals and may return but not edit source events. A coordinator cannot approve their own timesheet.

Alternatives:

1. One organization-wide monthly timesheet per specialist.
2. Central HR approves all service lines.
3. Pay directly from completed visits without submission or approval.

Security and operational consequences: One organization-wide sheet makes center accountability and multi-center approval ambiguous. HR approval exposes case-operation detail and moves clinical responsibility outside the center. Direct payment from mutable visits lacks approval evidence and correction controls. Center-month sheets add workflow for multi-center specialists.

Owner approval mandatory before implementation: Yes. HR and Finance Owner and Service Owner.

### D-027: Who approves a coordinator's own timesheet or a center with one coordinator?

Status: Open, mandatory

Recommended default: Route to a designated alternate coordinator or organization-level service approver who has timesheet approval permission but no payroll calculation authority. System Manager may act only through an audited emergency path.

Alternatives:

1. Allow self-approval.
2. Let Central HR approve.
3. Leave the timesheet unapproved until another coordinator is appointed.

Security and operational consequences: Self-approval violates separation of duties. HR approval blurs service and payroll responsibility. No fallback can delay pay. A designated approver requires an organization-level assignment and periodic review.

Owner approval mandatory before implementation: Yes. HR and Finance Owner.

### D-028: What information reaches payroll and when?

Status: Open, mandatory

Recommended default: Payroll receives only locked approved totals and lines containing staff, center, month, pay or activity code, units, rate reference where later approved, and approval evidence. It receives no beneficiary identity or case notes. Payroll posting remains out of the casework phase.

Alternatives:

1. Send beneficiary-level visit details to payroll.
2. Send only one monthly total with no source-line digest.
3. Implement tax and salary calculation in the same release as timesheets.

Security and operational consequences: Beneficiary-level payroll data is unnecessary exposure. A total without traceability is difficult to audit. Combining tax and salary rules expands legal and financial risk and delays casework improvements. Payroll-safe lines require stable pay-code mapping and locking.

Owner approval mandatory before implementation: Yes. HR and Finance Owner and Privacy and Security Owner.

### D-029: How are current beneficiary attachments classified during migration?

Status: Open, mandatory

Recommended default: Define identity-document and enrollment-document categories. Use metadata and owner-approved mapping where deterministic. Send ambiguous files to a restricted review queue. Do not make the same file visible in both scopes by default.

Alternatives:

1. Move every current beneficiary attachment to identity scope.
2. Move every file to the single migrated enrollment.
3. Duplicate files into both scopes.

Security and operational consequences: Identity scope may expose service contracts too broadly. Enrollment scope may hide identity evidence needed for controlled administrative use. Duplication increases retention, deletion, and access inconsistencies. Review adds migration workload but prevents silent overexposure.

Owner approval mandatory before implementation: Yes. Data Governance Owner and Privacy and Security Owner.

### D-030: What is the deletion and retention model for case records?

Status: Open, mandatory

Recommended default: Replace routine hard deletion with terminal state, correction, or voiding. Permit hard deletion only through an approved privacy or erroneous-record workflow with reason, dual authorization where required, immutable audit evidence, attachment cleanup, and backup reconciliation.

Alternatives:

1. Preserve current System Manager hard-delete behavior.
2. Never delete any record.
3. Automatically delete after a fixed period without a case-specific legal hold process.

Security and operational consequences: Routine hard deletion damages audit and reporting. Never deleting violates minimization and may conflict with policy. Automatic deletion can remove data under hold or active service. The recommended workflow depends on approved retention, legal basis, and backup handling.

Owner approval mandatory before implementation: Yes. Privacy and Security Owner, Service Owner, and System Owner.

### D-031: Which later module is built first after casework and timesheets?

Status: Open, mandatory

Recommended default: Sequence payroll integration after approved timesheets, then inventory and stock, then assets. Treat donor, grant, finance, volunteer, project, and expense functions as separate discovery initiatives.

Alternatives:

1. Build inventory before payroll.
2. Build one combined ERP program covering all secondary-DOCX modules.
3. Integrate an external ERP for every later function.

Security and operational consequences: Payroll depends directly on timesheet outputs but has statutory risk. Inventory may deliver high humanitarian value earlier. A combined ERP effort creates broad scope and shared-data risks. External integration reduces custom logic but adds vendor, privacy, identity, and synchronization dependencies.

Owner approval mandatory before implementation: Yes. Executive Service Owner and HR and Finance Owner.

### D-032: What production access control compensates for the lack of application MFA?

Status: Open, mandatory

Recommended default: Require an approved identity-aware access gateway with MFA or restrict HTTPS to an approved VPN and office network until application-level MFA or SSO is implemented. Keep Django authorization authoritative inside that boundary.

Alternatives:

1. Permit public password-only HTTPS access.
2. Implement application MFA before any production launch.
3. Restrict access only by source IP without remote-access support.

Security and operational consequences: Public password-only access increases account-takeover risk. Application MFA provides stronger direct control but adds delivery and recovery complexity. IP restriction is simple but operationally brittle. Gateway or VPN requires trusted-proxy review and availability planning.

Owner approval mandatory before implementation: Yes. Privacy and Security Owner and System Owner.

### D-033: Is malware scanning required for uploaded files?

Status: Open, mandatory

Recommended default: Require malware scanning and quarantine before production use with real uploads. Until integrated, limit file types and size as currently implemented and do not claim malware protection.

Alternatives:

1. Accept content-validation controls without malware scanning.
2. Disable all uploads in production.
3. Use content disarm and reconstruction in addition to scanning.

Security and operational consequences: No scanning leaves a malware delivery path to authorized staff. Disabling uploads removes a primary requirement. Content disarm is stronger but may alter evidence and increase cost. Quarantine needs asynchronous status, failure handling, and privacy-safe scanning infrastructure.

Owner approval mandatory before implementation: Yes. Privacy and Security Owner and System Owner.

### D-034: What aggregate reporting disclosure control is required?

Status: Open, mandatory

Recommended default: Apply role-based cross-center reporting and configurable small-cell suppression for diagnosis, social status, and narrow geographic reports. Keep center operational reports unsuppressed only for users who already have row-level access.

Alternatives:

1. Publish every aggregate count regardless of size.
2. Disable diagnosis and social-status reporting.
3. Permit reports only to System Manager.

Security and operational consequences: Small groups can re-identify people even without names. Disabling reports reduces program learning. System-Manager-only reporting creates bottlenecks and excessive privilege. Suppression complicates totals and export interpretation and needs a documented threshold.

Owner approval mandatory before implementation: Yes. Privacy and Security Owner and Service Owner.

### D-035: Does a transition date mean the last day in the old state or the first day in the new state?

Status: Open, mandatory

Recommended default: Treat every transition effective date as the first business date on which the new state applies. An exit effective on a date means service is no longer Active on that date. Label the field `Effective from` in transition workflows instead of relying on the ambiguous phrase `Exit date`.

Alternatives:

1. Treat exit and suspension dates as the last eligible service day.
2. Use different conventions for exit, suspension, and transfer.
3. Store a timestamp and infer the business date from exact time.

Security and operational consequences: Ambiguous conventions can authorize an event, assignment, center, or payment on the wrong day. Different conventions increase user and reporting errors. Exact timestamps do not resolve program policy and may be inappropriate for date-based source records. The recommended rule aligns with exclusive interval ends but requires careful migration of existing exit dates.

Owner approval mandatory before implementation: Yes. Service Owner and HR and Finance Owner.

### D-036: How are initial, repeated, and final assessments sequenced when several instruments are used?

Status: Open, mandatory

Recommended default: Maintain a separate assessment chain per enrollment and instrument lineage. Each chain begins with one Initial assessment, may contain any approved number of Repeated assessments, and may end with one Final assessment. A Final assessment closes that chain. Starting again after closure requires a new explicitly numbered chain or cycle.

Alternatives:

1. Keep one sequence across all instruments in the enrollment.
2. Allow several Initial assessments in one open chain.
3. Do not require previous-assessment links and derive order only by date.

Security and operational consequences: One cross-instrument sequence can imply invalid score comparability. Several initial records make baseline reporting ambiguous. Date-only ordering is vulnerable to backdated corrections and same-day records. Separate chains need clear instrument lineage and cycle identifiers.

Owner approval mandatory before implementation: Yes. Clinical or Technical Program Owner.

### D-037: May one enrollment have several active individual plans?

Status: Open, mandatory

Recommended default: Permit several drafts but at most one Active plan per enrollment. Activating a replacement supersedes or closes the prior Active plan through an audited transition. Goals from prior plans remain historical.

Alternatives:

1. Permit concurrent Active plans for different disciplines.
2. Permit only one plan record for the full enrollment and edit it in place.
3. Use one Active plan per specialist.

Security and operational consequences: Concurrent plans may support multidisciplinary work but can create conflicting goals and review dates. One mutable plan destroys version history. Specialist-specific plans fragment shared outcomes. One active enrollment plan is simpler but requires shared ownership and may not fit every program.

Owner approval mandatory before implementation: Yes. Service Owner.

### D-038: How many current primary specialists may an enrollment have?

Status: Open, mandatory

Recommended default: Allow exactly one current Primary specialist when an Active enrollment requires specialist delivery, plus any approved number of current Secondary specialists. Services that legitimately use shared primary responsibility may configure a different rule.

Alternatives:

1. Allow several Primary specialists without a limit.
2. Do not distinguish Primary and Secondary.
3. Assign one specialist to the person across every service.

Security and operational consequences: Several primary assignees blur responsibility and alerts. No role distinction weakens case ownership. Person-wide assignment violates service isolation. Enforcing one primary requires non-overlap constraints and a transfer-of-responsibility workflow.

Owner approval mandatory before implementation: Yes. Service Owner.

### D-039: Is the beneficiary code a person code or a service-enrollment code?

Status: Open, mandatory

Recommended default: Use one organization-wide person code on BeneficiaryIdentity and a separate immutable enrollment or case-episode code on each ServiceEnrollment. During migration, preserve the current beneficiary code as the person code or a legacy person-code alias when uniqueness and business meaning are confirmed. Never recycle either code.

Alternatives:

1. Keep one person code only and identify enrollments by UUID.
2. Treat the current code as the enrollment code and generate a new person code.
3. Use center-specific beneficiary codes that may repeat across centers.

Security and operational consequences: One code only is simple but may make service paperwork and reconciliation ambiguous. Reclassifying the current code can break external references. Repeating center codes complicates transfers, duplicate detection, and organization-wide reporting. Two codes require clear UI labels and migration crosswalks but preserve both identity and episode meaning.

Owner approval mandatory before implementation: Yes. Service Owner and Data Governance Owner.

## 3. Mandatory approval summary

The following decisions block implementation of their dependent behavior:

| Area | Blocking decisions |
|---|---|
| Identity and deduplication | D-001 |
| Enrollment and transfer | D-002 through D-006 |
| Master data and sensitive classifications | D-007 through D-009 |
| Age | D-010 and D-011 |
| Visits | D-012 and D-013 |
| Assessments | D-014 through D-016 |
| Plans and outcomes | D-017 and D-018 |
| Authorization and roles | D-019 through D-024 |
| Timesheets and payroll boundary | D-026 through D-028 |
| Migration, retention, and later phases | D-029 through D-031 |
| Production security and reporting privacy | D-032 through D-034 |
| Date semantics, assessment chains, plans, primary responsibility, and code meaning | D-035 through D-039 |

D-025 may use the recommended default during implementation, with confirmation during prototype review.

## 4. Approval record template

For each approved decision, add:

```text
Decision ID:
Approved option or amended rule:
Approver name and role:
Approval date:
Effective date:
Evidence link or meeting record:
Required follow-up:
Supersedes:
```

Approval evidence shall not contain beneficiary data, credentials, production exports, or other restricted values.
