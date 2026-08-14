# Production Deployment

The included Compose design is a starting point for a small deployment. It is not a substitute for infrastructure review, TLS certificate management, monitoring, patch ownership, and organizational approval.

## Components

- PostgreSQL with a persistent encrypted volume
- Django image running Gunicorn as a non-root user
- Nginx reverse proxy
- persistent private-file volume mounted only into Django

Use a managed PostgreSQL service and managed encrypted object storage when operational requirements justify them. Preserve the application download authorization boundary if private storage changes.

## Required environment

Create `.env.production` outside version control with values equivalent to the following. The repository ignores `.env` variants and the Docker build context excludes them.

```text
POSTGRES_DB=ssk
POSTGRES_USER=ssk
POSTGRES_PASSWORD=<generated database password>
DATABASE_URL=postgresql://ssk:<url-encoded-password>@db:5432/ssk
DATABASE_SSLMODE=prefer
DJANGO_SECRET_KEY=<generated application secret>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=cases.example.org
DJANGO_CSRF_TRUSTED_ORIGINS=https://cases.example.org
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_TRUST_X_FORWARDED_FOR=1
DJANGO_DEFAULT_FROM_EMAIL=noreply@example.org
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=<approved SMTP host>
EMAIL_PORT=587
EMAIL_HOST_USER=<approved SMTP user>
EMAIL_HOST_PASSWORD=<approved SMTP password>
EMAIL_USE_TLS=1
PRIVATE_MEDIA_ROOT=/app/media/private
```

The settings map these standard `EMAIL_*` values into Django. If a different approved backend is used, document and test its required environment values. Production startup fails closed when required application, database, host, or email values are absent or unsafe. The default SMTP backend also requires TLS or SSL.

The provided Nginx file replaces `X-Forwarded-For` with the direct client address. Do not enable `DJANGO_TRUST_X_FORWARDED_FOR` behind a proxy that accepts an untrusted header without replacing it.

## Release sequence

1. Back up PostgreSQL and private files according to [Backup and restore](BACKUP_AND_RESTORE.md).
2. Record the source revision, image digest, migration plan, and rollback owner.
3. Build and scan the image in CI.
4. Place the approved TLS certificate chain at `deploy/tls/fullchain.pem` and its private key at `deploy/tls/privkey.pem`. This ignored directory is mounted read-only into Nginx. Use a managed secret mount instead when available.
5. Deploy the database and web image into staging.
6. Run migrations as a one-time release operation:

   ```bash
   docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate --noinput
   ```

7. Run deployment checks:

   ```bash
   docker compose -f docker-compose.prod.yml run --rm web python manage.py check --deploy
   docker compose -f docker-compose.prod.yml run --rm web python manage.py makemigrations --check --dry-run
   ```

8. Start or update services:

   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```

9. Verify `/en/health/`, login, password reset email, center selection, denied cross-center URLs, private downloads, and audit events.
10. Complete role-specific UAT with synthetic staging data.

## TLS and network controls

The included Nginx configuration redirects port 80 to port 443 and terminates TLS with the mounted certificate and key. It sends a fixed HTTPS proxy header to Django, so the application does not trust a client-supplied scheme header. Replace this topology only after documenting the trusted proxy chain. Restrict PostgreSQL to application and administrative networks. Do not publish the database port. Restrict SSH and container administration to approved operators.

## Logging and monitoring

- The included reverse-proxy and Gunicorn formats omit query strings. Preserve this property when integrating centralized logging.
- Do not add beneficiary names, identifiers, form data, or filenames to application logs.
- Alert on elevated 403, 404, 429-equivalent login blocks, 500, health failures, database saturation, disk capacity, and backup failures.
- Define audit-event review ownership and retention through policy.
- Use centralized logs with access control and encrypted transport.

## Release rollback

Application rollback must account for database migration compatibility. Prefer forward fixes. If a release requires database restore, isolate the site, restore both database and private files from the same recovery point, reconcile later privacy actions, run permission checks, and obtain release approval before reopening access.

## Work required before production

- external security review and threat modeling;
- PostgreSQL integration, concurrency, and load testing;
- native-speaker Georgian review;
- approved account lifecycle and role review process;
- SMTP, monitoring, alerting, and incident response integration;
- encrypted off-host backup automation and restore evidence;
- malware scanning decision for uploaded files;
- data retention, export, correction, and disposal policy;
- full business UAT and accessibility review;
- infrastructure hardening and dependency vulnerability scanning.
