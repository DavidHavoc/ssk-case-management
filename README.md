# SSK Case Management

SSK Case Management is a focused Django 5.2 application for secure, center-scoped case work. The user-facing module is SSK Center. It replaces the case-management portion of the legacy Frappe and ERPNext application with a maintainable Django monolith.

## Current MVP

The repository includes:

- PostgreSQL-backed Django models and migrations
- System Manager, SSK Center Coordinator, and SSK Specialist roles
- multi-center staff and specialist assignments with an explicit active-center selector
- beneficiaries as durable person records with server-enforced restricted fields
- configurable service catalogs and effective-dated enrollment episodes, center placements, specialist assignments, transfers, exits, and re-enrollment history
- controlled Georgian geography, effective-dated diagnosis and social-status classifications, and SSK age bands
- governed service activities and locations, monthly enrollment schedules, planned and delivered service visits, correction history, and variance reporting
- versioned assessments and measurable service-plan periods with bilingual goal categories, progress history, child-condition reviews, and derived outcome reports
- private attachments with randomized storage names and authorized downloads
- audit events for sensitive reads, changes, downloads, and exports
- login throttling, administrator-issued temporary access codes, required first-login password changes, CSRF protection, and production cookie settings
- authorized reports and spreadsheet-safe CSV export
- responsive templates and English plus Georgian localization setup
- Docker Compose development and production examples
- synthetic demo data and pytest security coverage

This is a complete local MVP, not a claim of production readiness. Production use still requires organizational policy decisions, external security review, PostgreSQL-backed acceptance testing, backup restore exercises, monitoring, operational ownership, and user acceptance testing.

## Quick start with Docker

```bash
cp .env.example .env
docker compose up --build
docker compose exec web python manage.py seed_demo_data
docker compose exec web python manage.py changepassword synthetic.manager@example.invalid
```

Open `http://localhost:8000`. Demo identities use only `.invalid` addresses and synthetic values.

## Local verification

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
SSK_USE_SQLITE=1 .venv/bin/python manage.py migrate
SSK_USE_SQLITE=1 .venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
SSK_USE_SQLITE=1 .venv/bin/python manage.py check
SSK_USE_SQLITE=1 .venv/bin/python manage.py makemigrations --check --dry-run
```

SQLite is an explicit test-only convenience. Development, staging, and production are designed for PostgreSQL.

## Documentation

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data model](docs/DATA_MODEL.md)
- [Beneficiary and service enrollment foundation](docs/BENEFICIARY_ENROLLMENT_FOUNDATION.md)
- [Service visits and schedules](docs/SERVICE_VISITS_AND_SCHEDULES.md)
- [Service plans and outcomes](docs/SERVICE_PLANS_AND_OUTCOMES.md)
- [Permission matrix](docs/PERMISSION_MATRIX.md)
- [Local setup](docs/LOCAL_SETUP.md)
- [Production deployment](docs/PRODUCTION_DEPLOYMENT.md)
- [VPS deployment and system administration runbook](docs/VPS_OPERATIONS_RUNBOOK.md)
- [Backup and restore](docs/BACKUP_AND_RESTORE.md)
- [Security and privacy](docs/SECURITY_AND_PRIVACY.md)
- [Frontend design system](docs/FRONTEND_DESIGN_SYSTEM.md)
- [UI verification report](docs/UI_VERIFICATION_REPORT.md)
- [Frappe migration plan](docs/FRAPPE_MIGRATION_PLAN.md)
- [Feature parity checklist](docs/FEATURE_PARITY.md)

## Legacy specification

The functional source was inspected read-only at `/Users/David/Documents/GitHub/ASB-center`. The new application does not import from, modify, or depend on that repository, Frappe, or ERPNext.
