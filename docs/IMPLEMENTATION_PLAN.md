# Implementation Plan

## Discovery result

The legacy repository was inspected across its README, privacy and deployment documents, DocType schemas, Python validation, permission hooks, private-file controller, specialist roster services, report implementation, patches, demo seed, and automated tests.

The main rules carried into this application are:

- all case records are center-scoped;
- coordinators have center-wide access;
- specialists need a center assignment and beneficiary assignment;
- a case record specialist or a beneficiary assignment can authorize visit, assessment, and plan access;
- restricted beneficiary values are not available to specialists;
- direct URLs, filtered lists, form choices, downloads, reports, and exports use the same server-side scope;
- assessments follow initial, repeated, and final chains;
- active and completed plans require goals;
- service-visit changes rebuild monthly totals;
- sensitive files follow current parent authorization.

## Delivery phases

| Phase | Scope | MVP status |
|---|---|---|
| 1 | Legacy audit and parity mapping | Complete |
| 2 | Django project, PostgreSQL settings, containers, authentication, centers, roles | Complete |
| 3 | Beneficiaries, specialist rosters, server-side authorization | Complete |
| 4 | Visits, assessments, plans, goals, monthly summaries | Complete |
| 5 | Private files, audit events, reports, CSV export, localization | Complete |
| 6 | Automated security and workflow tests, linting, checks | Complete for local MVP |
| 7 | Staging deployment, PostgreSQL load checks, security review, UAT | Required before production |
| 8 | Approved production operations, monitoring, restore drills, policy sign-off | Required before production |

## Implementation decisions

- Django Groups store the three application roles so a staff member can hold more than one role.
- Staff center memberships support coordinators assigned to multiple centers.
- Specialist Center Assignment is the authority for specialist center access.
- The session stores one active center. Every scoped view validates that selection against current membership.
- UUID primary keys reduce identifier predictability, but authorization never depends on UUID secrecy.
- Monthly summaries use specialist, center, and month. This corrects legacy primary-center attribution for specialists who work in multiple centers.
- Restricted values are removed from specialist forms and templates, and specialist report and export routes never query those columns.
- Operational reports and in-application reminders derive from the same authorized enrollment, visit, assessment, plan, lifecycle-event, assignment, and staff-contract selectors as routine workflows.
- Reminder generation has no email or external delivery side effect. Delivery channels require separate configuration and approval.
- Private files are stored outside public static paths and have no public URL.
- Stock, assets, payroll posting, automated retention, and data-subject workflows are not part of this focused case-management MVP.

## Acceptance gates

Before production, complete the remaining work listed in the production, backup, security, migration, and parity documents. No real beneficiary data should enter this application before those gates are approved.
