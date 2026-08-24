# Customer Mac Mini Setup and Production Readiness Guide

This guide is for a customer who will run SSK Case Management on a Mac mini at home for
hands-on evaluation. It is also an instruction set for a browser-based support agent that cannot
open the customer's files or Terminal directly.

The initial installation is an **evaluation environment**. Use synthetic test data only. Do not
enter real beneficiary, employee, clinical, identity, or attachment data until every item in the
[production readiness gate](#16-production-readiness-gate) has an owner and has been approved.

If the customer wants access only from a browser on the Mac mini, with no domain and no
Cloudflare, use [Mac mini localhost setup](MAC_MINI_LOCALHOST_SETUP.md) instead. Do not combine the
localhost `.env` and Compose commands with this Cloudflare production-like workflow.

The intended path is:

```text
Approved user browser
    |
    | HTTPS and Cloudflare Access authentication
    v
Cloudflare Access and Cloudflare Tunnel
    |
    | outbound tunnel, with no router port forwarding
    v
Mac mini, 127.0.0.1:8000
    |
    v
Django and Gunicorn container
    |
    +---- PostgreSQL container and private database volume
    |
    +---- private attachment volume
```

The included `docker-compose.mac-mini.yml` file publishes only the Django container to the Mac's
loopback address. It does not publish PostgreSQL. The repository's Nginx proxy is not used in this
topology because Cloudflare terminates public HTTPS and forwards traffic through the tunnel.

## 1. Instructions for the browser-based support agent

When an agent is helping a nontechnical customer, the agent must follow these rules:

1. Explain what each step will change before asking the customer to run it.
2. Give one short command block at a time, then ask for the non-secret output.
3. Never claim that a command succeeded until the customer has returned its output or shown the
   resulting screen.
4. Never ask the customer to paste passwords, secret keys, tunnel tokens, `.env.production`,
   beneficiary information, or private attachments into chat.
5. Use placeholders such as `REPOSITORY_URL` and `cases.example.org`. Confirm replacements before
   the customer runs a command.
6. Stop when output contains an error. Diagnose that error before continuing.
7. Do not use `docker compose down --volumes`, `docker volume rm`, `docker system prune`, database
   drop commands, broad file deletion, or any other destructive command.
8. Do not run `seed_demo_data` with production settings. If demonstration records are wanted, use
   the separate development workflow in [Local setup](LOCAL_SETUP.md).
9. Keep a checklist of completed steps, unresolved warnings, the deployed Git commit, and the
   customer's feedback. Do not record secrets in the checklist.
10. Treat Cloudflare Access as an additional outer access check. It does not replace the
    application's roles, center assignments, authorization checks, or audit trail.

Before starting, the agent should ask only for:

- the public Git repository URL;
- the planned hostname, such as `cases.example.org`;
- whether the Mac has an Apple or Intel processor;
- whether the domain is active in the customer's Cloudflare account;
- the exact email addresses that should be allowed through Cloudflare Access; and
- confirmation that the evaluation will use synthetic data only.

If the agent cannot see the customer's directory, it should ask the customer to run `pwd`,
`git status --short`, and the relevant verification command, then return the output with secrets
removed.

### Repository-owner checklist before making the repository public

The repository owner should complete this review before sending the clone URL to the customer:

- Review the complete Git history, not only the current files, for credentials, `.env` files,
  database dumps, private attachments, production exports, TLS keys, access tokens, and real
  personal data. Removing a file in the latest commit does not remove it from Git history.
- Confirm that `.env.production`, private media, backups, database files, logs, and TLS material are
  ignored by both Git and the Docker build context.
- Enable the source host's secret scanning, dependency alerts, branch protection, and multi-factor
  authentication where available.
- Add an appropriate license and a private security-reporting contact before inviting outside
  contributors.
- Publish a reviewed release tag or commit for the customer. Do not ask the customer to deploy an
  unreviewed development branch.
- Tell testers never to attach real records, exports, secrets, or private screenshots to a public
  issue. Give them a private channel for security and privacy reports.

## 2. What the customer needs

- A Mac mini running a currently supported macOS version, preferably with at least 8 GB RAM and
  40 GB of free storage.
- A wired Ethernet connection when possible.
- A reliable power supply. A UPS is strongly recommended.
- A Cloudflare account protected by multi-factor authentication.
- A registered domain active on Cloudflare DNS.
- A GitHub account protected by multi-factor authentication if the repository requires sign-in.
- An approved password manager.
- Docker Desktop for Mac and its required license.
- Homebrew, used to install `cloudflared`.

Docker currently supports the current and two previous major macOS releases and requires at least
4 GB RAM. Confirm the current requirements and Docker Desktop license before installation in the
[official Docker installation guide](https://docs.docker.com/desktop/setup/install/mac-install/).

## 3. Prepare the Mac mini

Complete these steps before putting the application online:

1. Install all macOS updates and restart.
2. Enable FileVault and store its recovery key in the approved password manager.
3. Enable the macOS firewall.
4. Use a dedicated named administrator account. Do not use a shared account.
5. Enable automatic security updates.
6. In System Settings, prevent automatic sleep while connected to power. The display may sleep.
7. Configure the Mac to restart after a power failure if this is acceptable to the customer.
8. Disable services that are not required, including File Sharing, Screen Sharing, Remote Login,
   and Remote Management. If remote administration is required, document and secure it separately.
9. Do not configure router port forwarding for 80, 443, 5432, 8000, or SSH.
10. Connect the Mac and router to a UPS when possible.

Important limitation: Docker Desktop normally depends on a logged-in macOS user session. FileVault
can also require a person to unlock the Mac after a restart. Test a complete power-off and restart
before relying on the service. A home Mac, home Internet connection, and Docker Desktop remain
single points of failure even after this test.

## 4. Install the required software

Install Docker Desktop from the official Docker guide. Choose the correct Apple silicon or Intel
download. Open Docker Desktop, finish its setup, and enable its option to start at login.

Install Homebrew from its official site, then install Git and Cloudflare's tunnel client:

```bash
brew update
brew install git cloudflared
```

Verify the tools:

```bash
git --version
docker version
docker compose version
cloudflared --version
```

All four commands must return versions. Docker commands must show a running server, not only a
client.

## 5. Download the public repository

Choose a stable location owned by the dedicated macOS account. The examples use
`$HOME/ssk-case-management`.

```bash
cd "$HOME"
git clone REPOSITORY_URL ssk-case-management
cd "$HOME/ssk-case-management"
git status --short
git rev-parse HEAD
```

Replace `REPOSITORY_URL` with the public HTTPS clone URL before running the command. The status
output should be empty. Record the commit hash returned by `git rev-parse HEAD` in the deployment
record.

Confirm that the required files exist:

```bash
test -f docker-compose.prod.yml
test -f docker-compose.mac-mini.yml
test -f .env.example
test -f manage.py
echo "Required repository files are present"
```

Do not continue if a `test` command fails or the final message is not shown.

## 6. Create production configuration and secrets

Choose the final hostname first. The examples use `cases.example.org`. Use only lowercase letters,
numbers, dots, and hyphens in the hostname.

Generate a database password and a Django secret locally:

```bash
openssl rand -hex 32
openssl rand -hex 64
```

Save the first value as `SSK database password` and the second as `SSK Django secret` in the
approved password manager. Do not send them to the support agent and do not reuse them.

Create the configuration file with restrictive permissions:

```bash
cd "$HOME/ssk-case-management"
umask 077
touch .env.production
chmod 600 .env.production
nano .env.production
```

Paste the following template into `nano`. Replace all three `REPLACE_...` placeholders locally.
The database password occurs twice and must be identical both times. The generated hexadecimal
password needs no URL encoding.

```text
POSTGRES_DB=ssk
POSTGRES_USER=ssk
POSTGRES_PASSWORD=REPLACE_WITH_DATABASE_PASSWORD
DATABASE_URL=postgresql://ssk:REPLACE_WITH_DATABASE_PASSWORD@db:5432/ssk
DATABASE_SSLMODE=prefer

DJANGO_SECRET_KEY=REPLACE_WITH_DJANGO_SECRET
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=REPLACE_WITH_HOSTNAME
DJANGO_CSRF_TRUSTED_ORIGINS=https://REPLACE_WITH_HOSTNAME
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_TRUST_X_FORWARDED_FOR=1
DJANGO_TIME_ZONE=Asia/Tbilisi

PRIVATE_MEDIA_ROOT=/app/media/private
MAX_UPLOAD_SIZE=10485760
LOGIN_RATE_LIMIT_ATTEMPTS=5
LOGIN_RATE_LIMIT_WINDOW_SECONDS=900
```

In `nano`, press Control+O, Return, then Control+X to save and exit.

Verify the file without printing its contents:

```bash
cd "$HOME/ssk-case-management"
test "$(stat -f '%Lp' .env.production)" = "600"
grep -q '^DJANGO_DEBUG=0$' .env.production
if grep -q 'REPLACE_WITH' .env.production; then
  echo "ERROR: configuration still contains a placeholder"
else
  echo "Configuration has no placeholders"
fi
git check-ignore .env.production
```

The expected results are `Configuration has no placeholders` and `.env.production`. Never run a
command that prints this file to the terminal or chat.

## 7. Validate and start PostgreSQL and Django

Every command in this guide uses the fixed Compose project name `ssk`. This makes the database and
private-file volume names predictable for backup and recovery.

First render and validate the combined configuration:

```bash
cd "$HOME/ssk-case-management"
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  config --quiet
```

Build the application image and start PostgreSQL:

```bash
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  build --pull web
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  up -d db
```

Apply database migrations and run deployment checks:

```bash
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  run --rm web python manage.py migrate --noinput
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  run --rm web python manage.py check --deploy
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  run --rm web python manage.py makemigrations --check --dry-run
```

Warnings from `check --deploy` must be reviewed. Errors must be fixed before continuing. Start the
web service, without starting the repository's Nginx proxy:

```bash
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  up -d db web
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  ps
```

Wait until `db` and `web` show healthy. Confirm that the only published application port is the
loopback address and that PostgreSQL has no published port:

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Expected web binding:

```text
127.0.0.1:8000->8000/tcp
```

There must be no `0.0.0.0:8000`, no public `5432`, and no public database binding.

## 8. Test locally before Cloudflare

The production application redirects HTTP to HTTPS because it expects the trusted tunnel. Test the
origin with the same headers that the tunnel will send:

```bash
curl --fail --silent --show-error \
  -H 'Host: cases.example.org' \
  -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8000/en/health/
```

Replace `cases.example.org` with the configured hostname. Expected output:

```json
{"status": "ok"}
```

If it fails, inspect only recent container logs. Review output for accidental personal data before
sending it to an agent:

```bash
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  logs --tail=100 db web
```

## 9. Publish the site through Cloudflare Tunnel

Cloudflare recommends a remotely managed tunnel for most cases. Current dashboard labels may move,
so compare these steps with the
[official Cloudflare Tunnel setup guide](https://developers.cloudflare.com/tunnel/setup/).

1. Sign in to Cloudflare and confirm multi-factor authentication is enabled.
2. Confirm the domain is active in Cloudflare DNS.
3. Open **Networking > Tunnels**.
4. Select **Create Tunnel** and choose Cloudflared.
5. Name it `ssk-mac-mini` and create it.
6. Choose macOS as the connector environment.
7. Cloudflare will display an installation command containing a tunnel token. Do not paste that
   token into chat or store it in the repository.

Install the token without placing it in shell history. Paste it only at the hidden prompt:

```bash
read -s "CLOUDFLARE_TUNNEL_TOKEN?Paste the Cloudflare tunnel token: "
echo
sudo cloudflared service install "$CLOUDFLARE_TUNNEL_TOKEN"
unset CLOUDFLARE_TUNNEL_TOKEN
```

Return to the dashboard and wait for the connector status to become healthy. Then add a
**Published application** route:

| Field | Value |
| --- | --- |
| Subdomain | `cases` or the approved subdomain |
| Domain | the approved Cloudflare domain |
| Path | leave empty |
| Service type | `HTTP` |
| Service URL | `http://localhost:8000` |

Under additional HTTP settings, set **HTTP Host Header** to the full application hostname, such as
`cases.example.org`. Save the route. Cloudflare creates the tunnel DNS record automatically.

Cloudflare Tunnel uses outbound connections, so the customer does not need a static home IP and
must not open inbound router ports. If the connector cannot connect, confirm that outbound traffic
to Cloudflare is permitted, including the requirements described in the official setup guide.

## 10. Protect the site with Cloudflare Access

A tunnel route can publish a site without limiting who may reach its login page. Add Cloudflare
Access before inviting testers. Follow the current
[self-hosted application guide](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/).

1. In Cloudflare Zero Trust, open **Access controls > Applications**.
2. Create a **Self-hosted** application for the exact hostname, with no path restriction.
3. Create an **Allow** policy whose Include rule lists the exact approved email addresses. An
   approved organization email domain may be used only if every account in that domain is trusted.
4. Configure the organization's identity provider and require its MFA signal. If no identity
   provider is available during evaluation, configure Cloudflare One-Time PIN and still restrict
   the policy to the exact approved email addresses.
5. Set a short, approved session duration.
6. Test an approved user, an unapproved email address, sign-out, and session expiry.

Never use **Include Everyone**. Never use **Login Methods: One-time PIN** as the only Include rule,
because that can allow any valid email address. Cloudflare documents this risk in its
[Access policy guide](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/).

Cloudflare Access is valuable because the application does not currently provide application-level
multi-factor authentication. For real use, the organization must decide whether Access MFA is an
approved compensating control and document how Cloudflare identity access is removed when an
employee leaves.

## 11. Create the first application administrator

Create one named superuser. In this application a superuser is treated as a System Manager.

```bash
cd "$HOME/ssk-case-management"
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  exec web python manage.py createsuperuser
```

Use a unique username, a real organization-controlled email address, and a unique password stored
in the approved password manager. Do not create a shared administrator account and do not send the
password to the support agent.

Open `https://cases.example.org/en/accounts/login/`, pass Cloudflare Access, and sign in. A System
Manager should then:

1. create the required center records;
2. create named employee accounts through the application's staff workflow;
3. assign only the required role and center memberships;
4. deliver each one-time temporary access code directly through an approved channel; and
5. confirm that each employee is required to set a private password on first login.

Do not use Django's raw admin site as the normal account-management workflow. Do not share accounts.
Test with synthetic staff and case data first.

## 12. Acceptance test for the customer

Run the customer test from a device on a different network, such as a phone with Wi-Fi disabled.
Record missing features and confusing steps without recording beneficiary data.

- [ ] An approved email can pass Cloudflare Access.
- [ ] An unapproved email is denied before the Django login page.
- [ ] The Django login page loads in English and Georgian as expected.
- [ ] The System Manager can create a center and a synthetic employee.
- [ ] A temporary access code forces the employee to choose a new password.
- [ ] Each role sees only its permitted navigation and actions.
- [ ] A user assigned to one center cannot open another center's URLs or records.
- [ ] Private attachments require authorization and are not available through a public media URL.
- [ ] Create, update, sensitive read, download, export, login, and denial events are audited as
      expected.
- [ ] CSV exports open correctly and do not expose fields forbidden for the role.
- [ ] Restarting the containers preserves PostgreSQL data and private attachments.
- [ ] Restarting the Mac restores Docker, the application, and the Cloudflare connector after the
      designated operator logs in.
- [ ] The customer has written down missing workflows, wording, reports, fields, and usability
      problems with screenshots containing synthetic data only.

## 13. Normal operation and troubleshooting

Show service status:

```bash
cd "$HOME/ssk-case-management"
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  ps
curl --fail --silent --show-error https://cases.example.org/en/health/
```

Show recent application logs:

```bash
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  logs --tail=100 db web
```

Restart only the application containers:

```bash
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  restart db web
```

Stop the application without deleting data:

```bash
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  stop web db
```

Start it again:

```bash
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  up -d db web
```

If the public site is unavailable, check in this order:

1. Mac power, Ethernet, Internet connection, and logged-in operator session.
2. Docker Desktop is running.
3. `db` and `web` container health.
4. Local origin health using the command in section 8.
5. Cloudflare tunnel connector health.
6. Cloudflare Access policy and identity provider status.
7. Public `/en/health/` response.

## 14. Backups and restore evidence

For evaluation with synthetic data, create a backup before every update and after useful test-data
changes. A complete recovery point includes both PostgreSQL and the private attachment volume.

Create a local staging directory with restrictive permissions:

```bash
BACKUP_DIR="$HOME/SSK Backups/$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
mkdir -p "$BACKUP_DIR"
```

Pause web writes, dump PostgreSQL, and archive private attachments:

```bash
cd "$HOME/ssk-case-management"
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  stop web
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  exec -T db sh -c \
  'pg_dump --format=custom --no-owner --username="$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$BACKUP_DIR/ssk-db.dump"
docker run --rm \
  --volume ssk_private_media:/source:ro \
  --volume "$BACKUP_DIR":/backup \
  alpine:3.21 \
  tar -C /source -czf /backup/ssk-private-files.tar.gz .
shasum -a 256 \
  "$BACKUP_DIR/ssk-db.dump" \
  "$BACKUP_DIR/ssk-private-files.tar.gz" \
  > "$BACKUP_DIR/SHA256SUMS"
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  up -d web
```

Confirm that all three files exist and are nonempty. These files can contain sensitive data. A
local unencrypted folder is not a production backup. Before real data is permitted, automate
encrypted off-site backups, set retention and recovery objectives, alert on failures, separate
backup credentials from the Mac, and complete a documented restore rehearsal on an isolated
system. Follow [Backup and restore](BACKUP_AND_RESTORE.md) and the detailed
[VPS operations runbook](VPS_OPERATIONS_RUNBOOK.md).

Never test restoration over the live database or live private-file volume.

## 15. Safe application updates

Use a reviewed tag or commit, not an arbitrary moving branch. Schedule downtime and create a
verified backup first.

```bash
cd "$HOME/ssk-case-management"
git status --short
git fetch --tags
git pull --ff-only
git rev-parse HEAD
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  build --pull web
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  stop web
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  run --rm web python manage.py migrate --noinput
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  run --rm web python manage.py check --deploy
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  run --rm web python manage.py makemigrations --check --dry-run
docker compose -p ssk \
  -f docker-compose.prod.yml \
  -f docker-compose.mac-mini.yml \
  up -d db web
```

The first `git status --short` must be empty. Stop if it is not empty. After updating, repeat the
health, login, authorization, attachment, audit, and role tests. Record the new commit hash.

Docker Desktop, `cloudflared`, macOS, and the application image all need separate updates. Assign a
person to review them on a defined schedule. Do not allow a support agent to update them silently.

## 16. Production readiness gate

The agent must not describe this deployment as ready for real beneficiary data until the service
owner approves every applicable item below:

- [ ] The customer has documented the lawful basis, privacy notices, retention, correction,
      export, erasure, legal hold, and incident-notification processes.
- [ ] Hosting at a private home, the home jurisdiction, Cloudflare processing, and every backup
      location are approved by the organization's privacy and security owners.
- [ ] Cloudflare, source hosting, backup storage, monitoring, and any other processor agreements
      are approved.
- [ ] An external security review and threat model are complete.
- [ ] PostgreSQL integration, migration, concurrency, capacity, backup, and restore tests passed.
- [ ] The application, Cloudflare, GitHub, Mac, router, and backup administrator accounts use MFA
      where available and have named recovery owners.
- [ ] Cloudflare Access uses a reviewed allowlist and approved MFA policy. Joiner, role-change, and
      leaver procedures have been tested in Cloudflare and Django.
- [ ] System Manager, Central HR, Coordinator, and Specialist permissions have been reviewed with
      direct URL and cross-center denial tests.
- [ ] There are no shared user or administrator accounts.
- [ ] Secure delivery and expiry of temporary access codes are approved.
- [ ] The private attachment malware-scanning decision is documented and implemented if required.
- [ ] Encrypted off-site backups run automatically, failures alert a named person, retention is
      enforced, and a full isolated restore has succeeded.
- [ ] External monitoring covers the application health endpoint, tunnel availability, database
      health, disk capacity, container health, certificate path, and backup age.
- [ ] A tested incident runbook names technical, privacy, customer, and management contacts.
- [ ] The Mac restart, FileVault unlock, Docker startup, tunnel startup, router failure, home power
      failure, and Internet failure procedures have been rehearsed.
- [ ] Full business user acceptance testing used synthetic data and all blocking gaps were closed.
- [ ] Georgian content received native-speaker review, and accessibility testing is complete.
- [ ] The organization accepts the availability limitations of a home Mac or has moved the system
      to an approved managed production platform.
- [ ] A service owner has signed and dated the production approval.

Relevant project references:

- [Production deployment](PRODUCTION_DEPLOYMENT.md)
- [VPS operations runbook](VPS_OPERATIONS_RUNBOOK.md)
- [Security and privacy](SECURITY_AND_PRIVACY.md)
- [Permission matrix](PERMISSION_MATRIX.md)
- [Backup and restore](BACKUP_AND_RESTORE.md)
- [Acceptance criteria](ACCEPTANCE_CRITERIA.md)

## 17. Customer feedback record

After the evaluation, ask the customer to return a report using this structure:

```text
Deployment commit:
Evaluation dates:
Tester roles:
Devices and browsers:

What worked:

Missing workflows or fields:

Confusing wording or steps:

Incorrect permissions or visibility:

Reports or exports needed:

Performance or reliability problems:

Screenshots using synthetic data only:

Priority for each issue: blocking, high, normal, or low
```

Do not put secrets, access tokens, passwords, real personal information, or production exports in
the feedback report or an issue tracker.
