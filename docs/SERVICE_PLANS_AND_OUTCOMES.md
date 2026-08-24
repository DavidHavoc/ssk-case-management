# Service Plans and Outcomes

## Scope

Each individual plan belongs to one service enrollment. A plan is a reviewable period with a sequential version number, start and end dates, responsible specialist, review schedule, and optional link to the previous period. Several drafts are allowed. Activating a new period supersedes the prior active period inside one database transaction.

Plan states are Draft, Active, Completed, Superseded, and Cancelled. Active and completed plans require at least one valid goal. The repository does not enforce the unapproved 7 to 12 goal recommendation.

## Goal catalog and measurement

Migration `0010` seeds five bilingual early-intervention categories:

- child safety and hygiene;
- individual development;
- daily activities;
- positive parenting;
- kindergarten or school transition.

An additional `LEGACY-UNCLASSIFIED` category preserves goals created before governed categories existed. Those goals retain their original text, target date, status, and progress notes. They are marked `requires_review` because migration does not invent a baseline, target, achievement date, or clinical evidence.

Every reviewed goal stores its category, statement, baseline, measurable target, measurement type, unit or scale when needed, responsible specialist, target date, status, achieved date, evidence, and progress notes. Goals may link to assessment records from the same enrollment. Visits may optionally link to same-enrollment goals worked on.

Goal states are Planned, In Progress, Achieved, Deferred, and Cancelled. The valid transitions are:

- Planned to In Progress, Deferred, or Cancelled;
- In Progress to Achieved, Deferred, or Cancelled;
- Deferred to Planned, In Progress, or Cancelled;
- Achieved and Cancelled are terminal.

Deferred and cancelled transitions require a reason. Achieved goals require an achieved date and evidence. Every status change appends a dated transition with its actor and evidence.

## Progress and review history

Goal outcome measurements are append-only. A measurement stores a date, numeric value or rating, unit or scale, interpretation, notes, recorder, and optional same-enrollment source assessment.

Plan reviews are append-only. Each review stores its date, a child-condition conclusion of Improved, Worsened, Stable, or Not Yet Assessed, a rationale, recorder, and optional same-enrollment source assessment. A new review never updates or deletes an earlier conclusion.

## Derived totals and reports

The application does not store aggregate goal counts. Plan detail derives total, planned, in-progress, achieved, deferred, and cancelled counts by category and overall.

The Plan Goals and Outcomes report applies the authorized plan selector before calculating one row per category and one overall row for each plan. It compares planned, in-progress, and achieved goals and displays the latest review conclusion on or before the report date. Coordinator and System Manager CSV exports use the same authorized source.

## Authorization and attachments

Goals, measurements, reviews, assessment links, visit links, reports, and exports are reachable only through an authorized enrollment-specific plan or visit. Server-side forms restrict relationship choices, model validation rejects cross-enrollment links, and nested views return not found for an unauthorized parent.

Plan attachment behavior is unchanged. Files remain private, randomized, audited, and authorized through the parent plan selector.

## Georgian support

Goal category names are stored in English and Georgian. All new forms, state labels, validation messages, plan pages, and report headings use Django translation strings. The Georgian message catalog is compiled and covered by form-label tests. Native-speaker terminology review remains part of user acceptance testing.
