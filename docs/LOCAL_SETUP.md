# Local Setup

## Docker workflow

Requirements: Docker Engine with Compose support.

```bash
cp .env.example .env
docker compose up --build
```

The development Compose file starts PostgreSQL and the Django development server. It applies migrations after PostgreSQL reports healthy.

Create synthetic demonstration records:

```bash
docker compose exec web python manage.py seed_demo_data
docker compose exec web python manage.py changepassword synthetic.manager@example.invalid
```

The seed refuses to run when `DJANGO_DEBUG` is disabled. If `SSK_DEMO_PASSWORD` is set before seeding, the command applies that local-only password to every demo account without printing it. Do not use shared or production passwords for demo accounts.

Stop the application without deleting data:

```bash
docker compose down
```

Removing named volumes deletes the local database and private demo files. Confirm the target environment and whether anything must be retained before using any volume-removal option.

## Native Python workflow

Requirements:

- Python 3.11 or later;
- PostgreSQL 16 or a compatible supported version;
- gettext for compiling translations.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
```

Export the settings from `.env` through your shell or an approved environment loader. The application deliberately does not parse `.env` itself.

Create the PostgreSQL role and database according to local policy, set `DATABASE_URL`, then run:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

## Quality checks

```bash
SSK_USE_SQLITE=1 .venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
SSK_USE_SQLITE=1 .venv/bin/python manage.py check
SSK_USE_SQLITE=1 .venv/bin/python manage.py makemigrations --check --dry-run
```

Run the full suite against PostgreSQL in CI or staging before release. SQLite checks are useful for fast local feedback but do not validate PostgreSQL execution plans, concurrency, collation, backup, or restore behavior.

For the security acceptance run, execute `pytest` inside the Compose `web` service so the PostgreSQL-only summary concurrency test runs rather than skips.

## User setup

Create the first Django superuser only on an approved local or staging environment:

```bash
.venv/bin/python manage.py createsuperuser
```

A superuser is treated as System Manager. When an administrator creates a specialist, the application displays a one-time temporary access code. The employee signs in with that code and must immediately choose a private password. An authorized administrator can generate a replacement code from the employee record when needed.
