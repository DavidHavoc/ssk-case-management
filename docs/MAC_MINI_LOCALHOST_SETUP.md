# Mac Mini Localhost Setup with PostgreSQL

This guide installs SSK Case Management on a Mac mini for local evaluation. It uses PostgreSQL in
Docker, but the website is available only from a browser on the same Mac at
`http://localhost:8000`. It does not use Cloudflare, a domain, public HTTPS, router port
forwarding, or a public IP address.

Use synthetic test data only. This setup uses Django's development server, plain local HTTP, and
debug mode. It is not a production deployment and must not contain real beneficiary, employee,
clinical, identity, or attachment data.

For controlled remote evaluation through Cloudflare, use
[Customer Mac mini setup and production readiness](MAC_MINI_CUSTOMER_SETUP.md). For a conventional
server deployment, use [VPS operations](VPS_OPERATIONS_RUNBOOK.md).

## 1. Intended architecture

```text
Browser on the same Mac mini
    |
    | http://localhost:8000
    v
Django development container
    |
    +---- PostgreSQL 16 container and private database volume
    |
    +---- private attachment volume
```

The repository's `docker-compose.yml` binds the website to `127.0.0.1:8000`. PostgreSQL has no
host port. Another computer or phone must not be able to connect to this installation.

## 2. Instructions for a browser-based support agent

The support agent cannot assume it can see the customer's files or Terminal. It must:

1. Explain each change before asking the customer to run it.
2. Give one short command block at a time and wait for the non-secret output.
3. Never claim success until the returned output or screen proves it.
4. Never ask for `.env`, passwords, secret keys, personal data, database dumps, or private files.
5. Ask the customer to replace `REPOSITORY_URL` locally. Do not guess the repository URL.
6. Stop on any error and diagnose it before continuing.
7. Never run `docker compose down --volumes`, `docker volume rm`, `docker system prune`, database
   drop commands, or broad deletion commands.
8. Never change the port binding from `127.0.0.1` to `0.0.0.0` or remove the IP address.
9. Never enable router port forwarding or expose ports 5432 or 8000.
10. Keep a checklist of completed steps, the Git commit, warnings, and customer feedback without
    copying secrets or personal data.

Before starting, the agent should ask for:

- the public Git repository URL;
- whether the Mac uses Apple silicon or an Intel processor;
- confirmation that only the Mac's own browser needs access; and
- confirmation that only synthetic evaluation data will be used.

If the customer later asks for access from other devices, stop using this guide. Moving from
localhost to a network service changes the security model and requires the Cloudflare or VPS guide.

## 3. Prepare the Mac mini

1. Install current macOS security updates and restart.
2. Enable FileVault and store the recovery key in an approved password manager.
3. Enable the macOS firewall.
4. Use a named macOS account rather than a shared account.
5. Use Ethernet when possible.
6. Keep at least 20 GB of free disk space for the application, images, database, files, and local
   evaluation backups.
7. Do not enable File Sharing, Remote Login, Screen Sharing, or Remote Management for this setup.
8. Do not add any router port-forwarding rule.

The Mac may sleep when it is not being tested. If the customer wants the local site to remain
available throughout the day, prevent system sleep while connected to power. The display may still
sleep.

## 4. Install Docker and Git

Install Docker Desktop for the Mac's Apple silicon or Intel processor from the
[official Docker Desktop guide](https://docs.docker.com/desktop/setup/install/mac-install/). Confirm
that the organization's use complies with Docker's current license.

Open Docker Desktop and finish its setup. Git is normally available through Apple's command-line
developer tools. If `git` is missing, macOS will offer to install those tools when the command is
first run.

Verify the installation:

```bash
git --version
docker version
docker compose version
```

All commands must return version information. `docker version` must show both a Client and Server.

## 5. Download the repository

The examples use `$HOME/ssk-case-management` as the installation directory:

```bash
cd "$HOME"
git clone REPOSITORY_URL ssk-case-management
cd "$HOME/ssk-case-management"
git status --short
git rev-parse HEAD
```

Replace `REPOSITORY_URL` with the public HTTPS clone URL. `git status --short` should return no
lines. Record the commit hash without recording secrets.

Confirm the required files:

```bash
test -f docker-compose.yml
test -f .env.example
test -f manage.py
echo "Required repository files are present"
```

Do not continue if the final message is not shown.

## 6. Create the local environment file

Create `.env` from the local example:

```bash
cd "$HOME/ssk-case-management"
umask 077
cp .env.example .env
chmod 600 .env
nano .env
```

Generate a local Django secret in a second Terminal window:

```bash
openssl rand -hex 64
```

Replace `replace-with-a-long-random-value` in `.env` with the generated value. Do not send the
value to the support agent. Save it in the password manager if the customer wants to preserve
login sessions between rebuilds.

For this localhost workflow, confirm that the other values remain exactly as follows:

```text
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000
DATABASE_URL=postgresql://ssk:ssk-development-only@db:5432/ssk
DJANGO_TRUST_X_FORWARDED_FOR=0
DJANGO_SECURE_SSL_REDIRECT=0
```

Do not set `DJANGO_DEBUG=0` for plain HTTP localhost. The project's production configuration uses
secure HTTPS-only session and CSRF cookies, so changing only the debug flag would break normal
login and would not create a safe production deployment.

In `nano`, press Control+O, Return, then Control+X to save and exit. Verify without showing the
file contents:

```bash
test "$(stat -f '%Lp' .env)" = "600"
if grep -q 'replace-with-a-long-random-value' .env; then
  echo "ERROR: replace the Django secret"
else
  echo "Local environment file is ready"
fi
git check-ignore .env
```

Expected output includes `Local environment file is ready` and `.env`.

The PostgreSQL password in this local configuration is intentionally development-only. PostgreSQL
is not published to the Mac or network, and this setup must never be reclassified as production.

## 7. Start Django and PostgreSQL

Use the fixed Compose project name `ssklocal` in every command. This makes volume names predictable
for backup and troubleshooting.

Validate the Compose file:

```bash
cd "$HOME/ssk-case-management"
docker compose -p ssklocal config --quiet
```

Build and start both containers:

```bash
docker compose -p ssklocal up -d --build
docker compose -p ssklocal ps
```

The web container waits for PostgreSQL, automatically applies Django migrations, and then starts
the Django development server. Wait until PostgreSQL reports healthy and the web container reports
running.

If startup fails, inspect recent logs. Check the returned text for personal data before sending it
to an agent:

```bash
docker compose -p ssklocal logs --tail=100 db web
```

## 8. Verify localhost isolation and PostgreSQL

Confirm the port bindings:

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}'
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

Expected web binding:

```text
127.0.0.1:8000->8000/tcp
```

There must be no `0.0.0.0:8000`, no `*:8000`, and no published port 5432. Stop and correct the
configuration if any of those are shown.

Verify the application and database:

```bash
curl --fail --silent --show-error http://localhost:8000/en/health/
docker compose -p ssklocal exec db \
  psql --username=ssk --dbname=ssk --command='SELECT version();'
docker compose -p ssklocal exec web python manage.py showmigrations --plan
```

The health endpoint should return:

```json
{"status": "ok"}
```

The database command must identify PostgreSQL, and the migration list should show applied entries
with `[X]`.

As a second isolation test, try `http://MAC_IP_ADDRESS:8000` from another device on the same home
network. It must fail to connect. Do not change the binding to make this test succeed.

## 9. Create the first System Manager

Create one named application administrator:

```bash
cd "$HOME/ssk-case-management"
docker compose -p ssklocal exec web python manage.py createsuperuser
```

Use a unique username, an organization-controlled email address, and a unique password. Do not use
a shared account and do not send the password to the support agent. A Django superuser is treated
as a System Manager by this application.

Open the following address in a browser on the Mac:

```text
http://localhost:8000/en/accounts/login/
```

Sign in with the System Manager account. Then use the application's normal workflows to:

1. create synthetic center records;
2. create synthetic named employee accounts;
3. assign the minimum required roles and center memberships;
4. test the one-time temporary access-code workflow; and
5. confirm that each employee must set a private password on first login.

Do not use the Django raw admin interface as the normal staff-management workflow.

## 10. Optional synthetic demonstration data

The repository includes an idempotent development-only seed command. Run it only after the release
test suite passes and only in this `DJANGO_DEBUG=1` localhost environment:

```bash
docker compose -p ssklocal exec web python manage.py seed_demo_data
docker compose -p ssklocal exec web \
  python manage.py changepassword synthetic.manager@example.invalid
```

The seed uses `.invalid` email addresses and synthetic values. Choose a local-only password at the
hidden prompt. Never reuse a real or production password.

If the seed command fails, stop and return the error to the developer. Do not attempt to repair the
database manually and do not continue with a partially seeded evaluation.

## 11. Customer acceptance test

- [ ] `http://localhost:8000` opens from the Mac's browser.
- [ ] The Mac's LAN IP and port 8000 do not open from another device.
- [ ] PostgreSQL is reported healthy and has no published host port.
- [ ] The System Manager can create a synthetic center and employee.
- [ ] Temporary access codes force a password change.
- [ ] English and Georgian pages display as expected.
- [ ] Each role sees only its allowed navigation and records.
- [ ] Direct cross-center and unassigned record URLs are denied.
- [ ] Private attachment downloads require authorization.
- [ ] Reports and CSV exports show only fields allowed for that role.
- [ ] Audit events appear for sensitive reads, changes, downloads, exports, and login activity.
- [ ] Container restart preserves PostgreSQL data and private attachments.
- [ ] The customer records missing fields, workflows, reports, wording, and usability problems
      using synthetic data only.

## 12. Stop, start, and inspect the application

Show status:

```bash
cd "$HOME/ssk-case-management"
docker compose -p ssklocal ps
```

Show recent logs:

```bash
docker compose -p ssklocal logs --tail=100 db web
```

Stop without deleting data:

```bash
docker compose -p ssklocal stop web db
```

Start again:

```bash
docker compose -p ssklocal up -d
```

Restart both services:

```bash
docker compose -p ssklocal restart db web
```

Never add `--volumes` to a stop or down command. Removing the named volumes deletes the local
database and private evaluation files.

## 13. Back up local evaluation data

A complete backup needs both PostgreSQL and private attachments. Create a backup before updates and
after important testing sessions.

Create a restricted staging directory:

```bash
BACKUP_DIR="$HOME/SSK Local Backups/$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
mkdir -p "$BACKUP_DIR"
```

Stop web writes, dump PostgreSQL, and archive attachments:

```bash
cd "$HOME/ssk-case-management"
docker compose -p ssklocal stop web
docker compose -p ssklocal exec -T db sh -c \
  'pg_dump --format=custom --no-owner --username="$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$BACKUP_DIR/ssk-db.dump"
docker run --rm \
  --volume ssklocal_private_media:/source:ro \
  --volume "$BACKUP_DIR":/backup \
  alpine:3.21 \
  tar -C /source -czf /backup/ssk-private-files.tar.gz .
shasum -a 256 \
  "$BACKUP_DIR/ssk-db.dump" \
  "$BACKUP_DIR/ssk-private-files.tar.gz" \
  > "$BACKUP_DIR/SHA256SUMS"
docker compose -p ssklocal up -d web
```

Confirm that `ssk-db.dump`, `ssk-private-files.tar.gz`, and `SHA256SUMS` exist and are nonempty. A
local backup on the same Mac is useful for evaluation mistakes but does not protect against Mac
loss or disk failure. Never place a backup in Git or send it through chat.

Do not restore over the live database. Follow [Backup and restore](BACKUP_AND_RESTORE.md) for an
isolated restore rehearsal.

## 14. Update the local installation

Create a backup and record the current commit first. The working tree must be clean:

```bash
cd "$HOME/ssk-case-management"
git status --short
git rev-parse HEAD
```

If `git status --short` returns any lines, stop and ask the developer to review them. Otherwise:

```bash
git fetch --tags
git pull --ff-only
git rev-parse HEAD
docker compose -p ssklocal up -d --build
docker compose -p ssklocal exec web python manage.py check
docker compose -p ssklocal exec web \
  python manage.py makemigrations --check --dry-run
curl --fail --silent --show-error http://localhost:8000/en/health/
```

Repeat the login, role, cross-center, attachment, report, and audit checks. Record the new commit and
any problems.

## 15. Limits of localhost mode

This setup deliberately provides:

- PostgreSQL rather than SQLite;
- data persistence across ordinary container restarts;
- the application's normal role and authorization behavior; and
- a simple experience for one person using the Mac's browser.

It does not provide:

- access from another computer or phone;
- HTTPS or a trusted public hostname;
- Cloudflare Access or multi-factor authentication;
- Gunicorn or a production reverse proxy;
- production-safe debug and cookie settings;
- automated encrypted off-site backup and restore evidence;
- centralized monitoring or incident alerting;
- managed high availability; or
- approval to use real beneficiary data.

Do not solve these limitations by opening port 8000, enabling router forwarding, setting
`DJANGO_ALLOWED_HOSTS=*`, or using a tunnel that is not documented and access-controlled. Move to
the [Cloudflare Mac mini guide](MAC_MINI_CUSTOMER_SETUP.md) or the
[VPS operations runbook](VPS_OPERATIONS_RUNBOOK.md).

## 16. Customer feedback record

Ask the customer to return the following without secrets or real personal data:

```text
Deployment commit:
Evaluation dates:
Tester role:
Mac model and macOS version:
Browser and version:

What worked:

Missing workflows or fields:

Confusing wording or steps:

Incorrect permissions or visibility:

Reports or exports needed:

Performance or reliability problems:

Screenshots using synthetic data only:

Priority for each issue: blocking, high, normal, or low
```
