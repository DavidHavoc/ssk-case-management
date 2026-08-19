# Phased Roadmap

Status: proposed delivery sequence

This roadmap sequences domain change, migration, authorization, workflows, and later modules. It does not authorize production use or a real-data migration. Owner decisions in `DOMAIN_DECISIONS.md` remain binding gates.

## 1. Delivery principles

- Protect the current authorization boundary while the domain model changes.
- Use additive schema changes, synthetic backfills, reconciliation, and controlled cutover.
- Move selectors, forms, views, reports, exports, timelines, and private files together for each authorization boundary.
- Keep person counts, enrollment counts, events, assessments, goals, and timesheet lines distinct.
- Preserve event-time center and specialist attribution.
- Publish governed master data before transactional forms depend on it.
- Do not combine casework, payroll, inventory, assets, and the broader NGO ERP backlog into one release.
- Treat production readiness as an organizational control track, not as the automatic result of feature completion.

## 2. Phase summary

| Phase | Outcome | Depends on | Production status |
|---|---|---|---|
| 0 | Owner decisions, data governance, and migration rules approved | None | Synthetic only |
| 1 | Master data and effective-dated domain foundation | Phase 0 decisions | Synthetic only |
| 2 | Identity, enrollment, placement, transfer, and assignment cutover | Phase 1 | Synthetic only |
| 3 | Service events and corrected activity, location, and format model | Phase 2 | Synthetic or approved staging only |
| 4 | Versioned assessments and measurable individual plans | Phase 2 and approved clinical rules | Synthetic or approved staging only |
| 5 | Role-aware specialist workspace, reports, and privacy hardening | Phases 2 through 4 | Staging candidate |
| 6 | Timesheet submission and center approval | Phase 3 and HR decisions | Staging candidate |
| 7 | Production governance and controlled migration readiness | Phases 0 through 6 as required for launch | Production gate only after approval |
| 8 | Payroll integration | Approved and stable Phase 6 | Separate later phase |
| 9 | Inventory and stock | Separate inventory specification | Separate later phase |
| 10 | Assets | Inventory or separate asset foundation | Separate later phase |
| 11 | Broader NGO ERP discovery | Executive prioritization | Not committed |

## 3. Phase 0: decisions and governance foundation

### Scope

- Approve or amend every Open, mandatory decision from D-001 through D-039.
- Name Service, Data Governance, Clinical or Technical Program, HR and Finance, Privacy and Security, and System owners.
- Approve SSK service catalog and center service offerings.
- Approve official geography source and version.
- Approve diagnosis and social-status coding approach and visibility.
- Confirm early-intervention age bands and 29 February rule.
- Resolve Barthel ranges, AEPS old and new definitions, goal categories, and the 7 to 12 goal ambiguity.
- Define timesheet approvers, self-approval fallback, payroll-safe line content, and correction window.
- Approve data retention, deletion, attachment classification, and real-data migration policy.

### Deliverables

- Approved decision records with named owners and dates.
- Master-data seed workbook or equivalent controlled source using synthetic or reference data only.
- Instrument definition packs with version identifiers and test examples that contain no beneficiary data.
- Role and permission sign-off.
- Migration mapping specification and exception taxonomy.
- UAT roles, environments, and synthetic scenarios.

### Exit criteria

- Every mandatory decision needed for Phase 1 has status Approved.
- No assessment scoring rule has gaps, overlaps, or undefined response meaning.
- No master value lacks a stable code, owner, bilingual-label plan, and retirement rule.
- Privacy and Security Owner has approved the target access model at the identity and enrollment boundary.

## 4. Phase 1: governed master data and time-aware schema

### Scope

- Add governed ServiceDefinition and CenterServiceOffering.
- Add Region, Municipality, DiagnosisDefinition, SocialStatusDefinition, ServiceActivityDefinition, VisitLocationDefinition, DeliveryModeDefinition, ParticipationFormatDefinition, GoalCategory, and TransitionReason.
- Add BeneficiaryIdentity, ServiceEnrollment, EnrollmentStateEvent, EnrollmentCenterPlacement, and EnrollmentSpecialistAssignment.
- Add effective-date and non-overlap constraints.
- Add master publication, retirement, and audit controls.
- Define event-time snapshots for transactional center, specialist, service, and master labels.

### Implementation order

1. Add tables and constraints without removing current fields.
2. Load approved master records with stable codes.
3. Create synthetic mapping fixtures for every current choice value.
4. Add read-only reconciliation commands and reports.
5. Test interval boundaries, duplicate prevention, retirement, and historical labels.

### Key risks and controls

| Risk | Control |
|---|---|
| Overlapping placements or assignments | Database exclusion or equivalent constraints plus transaction-level validation |
| Master rename rewrites history | Effective-dated resolution or transaction-time code and label snapshots |
| Free-text values lost | Preserve legacy raw value and map to a provisional controlled code |
| Cross-service disclosure | Make enrollment the required parent for every new case record selector |

### Exit criteria

- Master data is queryable, versioned, auditable, and cannot be hard-deleted while referenced.
- Synthetic identities can hold two simultaneous different-service enrollments without data collision.
- Same-service overlap behaves according to D-002.
- Transition, transfer, and assignment interval test matrices pass at boundary dates.

## 5. Phase 2: identity and enrollment migration and authorization cutover

### Scope

- Backfill each current Beneficiary into one BeneficiaryIdentity, one ServiceEnrollment, and one initial center placement.
- Backfill enrollment state history from current status and dates with explicit legacy provenance.
- Move specialist assignments to the enrollment boundary.
- Link visits, assessments, plans, goals, and attachments to the correct enrollment.
- Implement suspend, resume, exit, transfer, and re-enrollment services.
- Replace current `beneficiaries_for_user()` semantics with identity and enrollment selectors.
- Update forms and views so posted identity, enrollment, center, and specialist relationships are authorized and effective on the business date.

### Migration sequence

1. Generate a dry-run crosswalk and exception report.
2. Backfill synthetic data in a disposable database.
3. Reconcile counts and hashes.
4. Exercise rollback before any cutover.
5. Enable dual-read comparison in staging where practical.
6. Switch selectors and forms to the new model.
7. Retain old fields read-only during a stabilization period.
8. Remove old fields only in a later cleanup migration after sign-off.

### Authorization test matrix

- current assigned specialist in current center;
- future assignment;
- assignment starting today;
- assignment ending today under the approved interval convention;
- ended assignment;
- current coordinator;
- old-center coordinator before and after transfer;
- destination coordinator before and after transfer;
- Central HR;
- System Manager normal and break-glass mode if adopted;
- direct URL, form POST, report, export, timeline, and attachment download for each case.

### Exit criteria

- Person, enrollment, placement, assignment, and event counts reconcile.
- No specialist can see an unrelated service for the same person.
- Transfer preserves old-center event attribution and applies the approved history-sharing boundary.
- Re-enrollment creates a new episode without mutating the exited episode.
- All current private-file protections remain effective under the new parents.

## 6. Phase 3: service events and monthly service evidence

### Scope

- Introduce ServiceEvent and ServiceEventActivity.
- Separate activity, physical location, delivery mode, and participation format.
- Validate assignment and placement on the event date.
- Support service-specific required fields and units.
- Preserve scheduled, completed, no-show, and cancelled status semantics.
- Replace or version the existing monthly summary so totals include center, service, activity, units, duration, and unique beneficiaries.
- Implement approved corrections and impact detection for submitted or approved timesheets.

### Migration treatment for current visits

- Map unambiguous current values to the new dimensions.
- Use `legacy_unclassified` values when a current combined visit type cannot determine all dimensions.
- Preserve original visit type and notes as migration evidence.
- Never infer physical location from an activity name unless a reviewed mapping explicitly authorizes it.

### Exit criteria

- Every completed event has at least one valid activity.
- Cancelled events contribute no payable units.
- Multi-activity events do not double count payable time under the approved rule.
- Summary rebuilds remain transactionally consistent under concurrent writes.
- Report totals reconcile to source events across center, specialist, service, activity, and month.

## 7. Phase 4: assessment and outcome architecture

This phase can run as two coordinated workstreams after Phase 2.

### 4A. Assessment templates and scoring

- Add AssessmentInstrument and immutable AssessmentTemplateVersion.
- Add versioned domains, items, response types, validation rules, formulas, and score bands.
- Publish approved Barthel and AEPS versions.
- Link new assessments to one published version.
- Preserve initial, repeated, and final purpose within one enrollment and compatible instrument lineage.
- Add calculation trace, override reason, and historical rendering tests.
- Migrate current assessments to a clearly labeled legacy template version before structured mapping.

Exit criteria:

- Historical results do not change when a later template is published.
- Invalid ranges, gaps, overlaps, and impossible response states cannot be published.
- Old and new AEPS results are not compared unless the approved rule permits comparison.
- Assessment reports identify instrument and version.

### 4B. Plans, goal categories, and outcome measurements

- Add governed GoalCategory with service applicability.
- Extend goals with baseline, indicator, measurement type, target, responsible specialist, and status history.
- Add GoalOutcomeMeasurement and dated plan review conclusions.
- Derive per-category and total goal counts.
- Enforce the approved plan activation and goal-count rules.
- Migrate current free-text goals to `unclassified legacy` until reviewed.

Exit criteria:

- Every active plan has the approved minimum goal evidence.
- Goal progress can be reproduced from dated measurements.
- Improved, stable, or worsened is stored as a reviewed conclusion, not inferred silently.
- Reports distinguish goal status from measured outcome.

## 8. Phase 5: specialist workspace, reporting, and privacy hardening

### Scope

- Route specialist-only users to assigned beneficiary enrollments after center selection.
- Implement identity header and enrollment switcher with strict server-side enrollment scope.
- Provide enrollment-scoped overview, visits, assessments, plans and goals, documents, and timeline.
- Add next-due assessment, plan review, and service schedule cues without disclosing hidden services.
- Update coordinator and manager dashboards for distinct person and enrollment counts.
- Add as-of reporting for statuses, transfers, age bands, historical centers, assessments, and outcomes.
- Add privacy-safe Central HR screens and exports.
- Implement small-cell or approved alternative disclosure control for sensitive aggregate reporting.

### Required verification

- English and Georgian UAT at supported widths.
- Keyboard-only and screen-reader review.
- Mixed-role landing and workspace switching.
- Template-context tests proving that hidden identity fields and unrelated enrollments never reach specialist pages.
- Query-count tests for multi-enrollment cards and timelines.
- Export field-level allowlists and spreadsheet-safe output.

### Exit criteria

- The source-evidence specialist workflow is satisfied.
- One person with multiple services is understandable without combining service status or plans.
- Counts are labeled by person, enrollment, or event.
- Restricted data is absent from HTML, validation errors, logs, exports, and audit metadata for unauthorized roles.

## 9. Phase 6: timesheet submission and approval

### Scope

- Create one Timesheet per specialist, center, and month.
- Derive eligible lines from completed ServiceEvents.
- Add draft, submitted, returned, approved, exported, and locked states.
- Enforce coordinator center scope and no self-approval.
- Add alternate approver configuration.
- Provide Central HR with payroll-safe approved lines only.
- Add source-line digest or version so later event changes invalidate approval.
- Support return, correction, resubmission, reapproval, and export audit.

### Boundary rules

- Timesheets do not replace service events.
- Coordinators approve service truth, not pay calculations.
- Central HR does not edit case records.
- Payroll does not consume unapproved or unlocked lines.
- Beneficiary identity and notes never enter payroll-facing data.

### Exit criteria

- Multi-center specialists have separate, correctly scoped timesheets.
- No user can approve their own timesheet.
- Backdated event changes invalidate the correct timesheet only.
- Approval, return, lock, and export histories are complete and auditable.
- Payroll-safe totals reconcile to approved source events without exposing beneficiary data.

## 10. Phase 7: production governance and controlled migration readiness

Feature completion does not satisfy this phase automatically.

### Organizational gates

- Approved lawful basis, privacy notices, retention, correction, export, erasure, incident, and backup-reconciliation policies.
- Approved role provisioning, deprovisioning, periodic review, break-glass, and separation-of-duty procedures.
- MFA through an identity-aware gateway, VPN, SSO, or application control approved under D-032.
- Malware scanning or a formally accepted alternative under D-033.
- External security review and threat model.
- Native Georgian, accessibility, and role-specific UAT.
- PostgreSQL integration, concurrency, capacity, and restore testing.
- Monitoring, alerting, audit review, SMTP, TLS, trusted proxy, dependency scanning, patch ownership, and incident contacts.
- Encrypted off-host backups with approved RPO, RTO, retention, key custody, and observed restore evidence.
- Approved real-data migration plan, reconciliation thresholds, cutover, rollback, and temporary-data disposal.

### Technical acceptance package

- Full tests, Ruff lint and format, Django checks, deployment checks, and migration drift checks.
- Migration rehearsal report using synthetic data.
- Authorization matrix results at assignment and transfer date boundaries.
- Assessment version and scoring validation evidence.
- Timesheet approval and correction evidence if timesheets are in launch scope.
- Data-flow and privacy review for every external integration.

### Exit criteria

- Service Owner, Privacy and Security Owner, System Owner, and migration owner sign the production gate.
- No real data is loaded before sign-off.
- Rollback and disaster recovery have named decision owners.

## 11. Phase 8: payroll integration

### Preconditions

- Phase 6 has operated successfully through representative approval cycles.
- HR and Finance has approved employment terms, pay codes, rates, deductions, taxes, retroactivity, currencies, accounting interface, and statutory reporting.
- Privacy has approved the payroll data set and retention.

### Scope boundary

- Consume approved and locked timesheets.
- Maintain pay-rule versioning and effective dates.
- Produce payroll review and export evidence.
- Keep beneficiary data outside payroll.
- Do not post to accounting until accounting integration has its own specification and reconciliation controls.

### Exit criteria

- Every payroll amount traces to approved time, an effective rule, and an approval event.
- Retroactive corrections do not silently rewrite a closed payroll period.
- Finance reconciliation and statutory review pass.

## 12. Phase 9: inventory and stock

### Required separate specification

- warehouses and regional hubs;
- items, units, lots, expiry dates, and package composition;
- receipts, issues, transfers, returns, adjustments, and stock counts;
- role separation among requester, custodian, approver, and auditor;
- donor or project restrictions if later approved;
- narrow enrollment reference for beneficiary issues without granting case access;
- offline, barcode, and mobile needs if required;
- inventory valuation boundary with finance.

### Exit criteria

- Stock movements reconcile by item, lot, warehouse, and date.
- Expiry and negative-stock rules are approved.
- Warehouse users cannot discover beneficiary case content.

## 13. Phase 10: asset management

### Required separate specification

- asset categories, identifiers, custody, location, condition, and documents;
- vehicles, equipment, tents, and laptops;
- maintenance plans and work records;
- handover and return;
- impairment, disposal, and loss workflows;
- depreciation input and accounting integration boundary;
- restricted linkage when an asset is issued to a beneficiary or staff member.

### Exit criteria

- Asset history is complete from acquisition through disposal.
- Custody and maintenance are auditable.
- Financial calculations use approved finance rules rather than casework assumptions.

## 14. Phase 11: broader NGO ERP discovery

The secondary DOCX mentions donor profiles, donation tracking, grants, volunteers, accounting, budgeting, projects, and expenses. These are not committed requirements. Discovery shall determine whether to build, buy, or integrate each bounded context and shall document identity, data ownership, permissions, accounting controls, donor restrictions, and reconciliation before implementation.

## 15. Cross-phase migration and rollback strategy

Every domain cutover shall use this sequence:

1. Add the new structure.
2. Seed or publish governed reference data.
3. Backfill in a restricted environment.
4. Produce exception and reconciliation reports.
5. Run authorization and business acceptance scenarios.
6. Verify rollback on a disposable database.
7. Switch reads and writes behind a controlled release.
8. Monitor errors, discrepancies, authorization denials, and performance.
9. Keep prior fields or crosswalks until the rollback period ends.
10. Remove obsolete structures only through a separately reviewed cleanup migration.

No phase may solve a migration discrepancy by inventing beneficiary data, inferring a sensitive code from ambiguous narrative, or dropping an unmapped record without an approved exception reason.
