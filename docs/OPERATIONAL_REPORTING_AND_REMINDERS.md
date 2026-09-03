# Operational Reporting and Reminders

## Authorization boundary

Every report source starts with a server-side authorized QuerySet. Filters and aggregation run only after that boundary is established. Center coordinators see records owned by their active center. Specialists see only currently assigned enrollment scope and approved continuity history. System managers remain bound to the selected center on report and reminder pages.

Specialist reports do not select or render personal ID, address, guardian or parent, phone, email, contract number, restricted classifications, identity attachments, or unrestricted notes. CSV export remains limited to System Managers and Center Coordinators. Every CSV cell passes through spreadsheet-formula neutralization, including headers and derived labels.

## Operational report catalog

The report screen provides these decision-useful views:

1. Beneficiaries grouped by selected center, service, enrollment status, SSK age band, region, and municipality, with distinct beneficiary and enrollment counts.
2. Specialist caseload grouped by specialist, with distinct beneficiaries, enrollments, active assignment intervals, and pending, active, and suspended enrollment counts. A specialist sees only their own assignment row.
3. Planned versus delivered service by month, activity, delivery location, and participation format, including visit and unit variance, no-shows, cancellations, and delivered duration.
4. Visit exceptions for no-shows, cancellations, and planned visits whose visit date has passed.
5. Initial, repeated, and final assessment records with instrument, template version, derived score, classification, and delayed-domain count.
6. Assessment progress with current and previous totals, score change, delayed-domain change, and an explicit comparability result.
7. Plan goals grouped by governed category and effective goal status, including overdue target counts.
8. Beneficiary outcomes from the latest authorized plan per enrollment, including the latest condition conclusion and derived goal-achievement percentage.
9. Enrollment lifecycle trends grouped by month, event kind, and service. This includes admission, suspension, resumption, exit, completion, cancellation, and re-enrollment events when present.
10. Current data-quality exceptions, including missing enrollment dates, missing authorized-center beneficiary documentation, missing contract references, missing demographic reporting fields, overdue reviews, missing review dates, and goals marked for review.

Legacy detail reports remain available for operational traceability. They use the same authorization and export controls.

## Filters and reporting date

The report screen supports date, service, specialist, status or type, activity, location, age-band, region, municipality, exception, lifecycle-event, outcome, and data-quality filters where relevant. `to_date` is also the reporting date for age bands, goal status history, assessment comparison, caseload assignment intervals, and overdue calculations. If it is omitted, the application uses the local application date.

## Reminder rules

The Reminders page is an in-application action queue. It derives these items at request time:

- overdue next-review dates on the latest completed assessment for each authorized enrollment;
- active plan reviews that are overdue or fall within the configured upcoming window;
- open enrollment end dates that have passed or fall within the upcoming window;
- authorized staff contracts that have expired or fall within the upcoming window;
- current unresolved data-quality exceptions.

The default upcoming window is 30 days and can be changed with the Django setting `SSK_REMINDER_UPCOMING_DAYS`. Specialists receive assigned-enrollment reminders and their own contract reminder. Coordinator and manager reminders may include restricted operational exceptions such as missing center-scoped documentation, but the reminder text never contains the restricted value.

Reminder generation does not send email, create a message, call an external service, or persist a notification. Email or another delivery channel must not be added without explicit configuration and organizational approval.

## Performance and audit behavior

Aggregated report and reminder builders use fixed-query loading patterns. Tests compare query counts before and after adding records to detect per-row query growth. Report views record a sensitive-read audit event. CSV exports record an export audit event with report type and row count. Denied specialist exports are audited.

## Verification coverage

Automated tests cover center and assignment authorization, restricted-value exclusion, report filters, assessment progress, lifecycle trends, CSV formula neutralization, data-quality visibility, reminder categories, lack of email side effects, and query-count growth.
