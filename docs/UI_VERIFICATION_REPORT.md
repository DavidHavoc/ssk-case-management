# UI verification report

## Baseline

The verified MVP baseline is commit `2e3feff`, tagged `verified-mvp-v0.1.0`. The redesign is implemented on `codex/modern-yellow-ui`. Nothing has been pushed.

Before the baseline commit, ignored local environment files, TLS material, databases, generated static files, caches, private media, and the virtual environment were confirmed to be untracked. The baseline passed 53 PostgreSQL tests, Ruff lint and format checks, Django system and deployment checks, migration drift checks, and Georgian catalog validation.

## Redesign coverage

The shared shell and component system cover authentication, center selection, dashboard, beneficiaries, specialist roster, visits, assessments, plans and goals, monthly summaries, reports and CSV controls, audit events, attachments, forms, pagination, validation, empty states, permission errors, not-found errors, server errors, and destructive confirmations.

Authorization selectors, role gates, model validation, and authorized form querysets were not weakened or replaced.

## Automated verification

- PostgreSQL pytest: 58 passed, including five new UI regression tests.
- Ruff lint: passed.
- Ruff format check: 74 files already formatted.
- JavaScript syntax check: passed for `static/js/app.js`.
- Django system check: zero issues.
- Production image build and `check --deploy`: zero issues.
- Migration drift check: no changes detected in development and production settings.
- Georgian `msgfmt --check --check-format`: passed with zero fuzzy or untranslated application messages.
- Static collection in the production image: passed with the CSS and JavaScript assets post-processed.
- Git whitespace and added-line em dash checks: passed.

Rendered HTML from each major page family was scanned with axe-core 4.10.3 against WCAG 2.1 A and AA rules. No structural violations were reported. The DOM-based audit cannot calculate final rendered contrast, so the primary text pairs were checked separately:

| Pair | Contrast |
|---|---:|
| Near-black on white | 18.26:1 |
| Muted text on white | 5.91:1 |
| Muted text on warm background | 5.47:1 |
| White on sidebar charcoal | 17.58:1 |
| Near-black on brand yellow | 11.11:1 |
| Red status text on white | 7.52:1 |
| Green status text on white | 6.05:1 |
| Orange status text on white | 5.52:1 |

## Browser review

- Reviewed English and Georgian at 320, 768, 1024, and 1440 pixels.
- Dashboard, lists, detail pages, create and edit forms, delete confirmations, center selector, specialist roster, summaries, reports, CSV controls, audit events, attachment uploads, authentication, password reset, validation, access denied, and not-found behavior were navigated.
- No page-level horizontal overflow or clipped headings and labels were found. Wide tables scroll only inside focusable labeled regions.
- The mobile drawer updates `aria-expanded`, keeps the closed drawer out of the tab order, closes with Escape, and returns focus to the trigger.
- Forms expose persistent labels, linked summaries, inline error alerts, and stable save and cancel actions.
- Manager, coordinator, and specialist roles were exercised. Manager-only navigation stayed absent for other roles. Specialist pages did not expose restricted beneficiary labels, beneficiary attachment controls, or CSV export.
- Cross-role denial rendered the designed access-denied state. Server-side authorization regression tests remained unchanged and passed.
- Browser console review reported zero warnings or errors.
- Screens used only seeded synthetic data, including English and Georgian labels, populated tables, empty-capable states, and validation errors.

## Screenshots

Before and after screenshots are stored under `docs/screenshots/before` and `docs/screenshots/after`. They use only synthetic demonstration records.
