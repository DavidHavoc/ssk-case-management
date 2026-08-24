# VPS Deployment and System Administration Runbook

This runbook describes how to operate SSK Case Management on one small virtual private
server (VPS). It is written for a designated system administrator and covers the complete
server lifecycle from procurement through retirement.

The target deployment is a small organization with approximately 10 employees. The expected
application load is low, but the confidentiality and recoverability requirements are high
because the system can hold beneficiary and case information.

This is technical guidance, not legal advice. The organization remains responsible for its
lawful basis, privacy notices, processor agreements, retention rules, incident notification,
and any country-specific requirements.

## 1. Scope and target architecture

Use this runbook with:

- Ubuntu Server 24.04 LTS, 64-bit;
- 2 virtual CPUs, 4 GB RAM, and at least 60 GB SSD storage;
- one static IPv4 address;
- a domain such as `cases.example.org`;
- Docker Engine and the Docker Compose plugin;
- the repository's `docker-compose.prod.yml` file;
- PostgreSQL in a private Docker network;
- Django and Gunicorn in a private Docker network;
- Nginx as the only public application container;
- an approved secure process for administrators to deliver temporary access codes directly to employees;
- encrypted, automated, off-host backups; and
- an external uptime monitor and an operational alert recipient.

The resulting network path is:

```text
Employee browser
    |
    | HTTPS on TCP 443
    v
Provider firewall
    |
    v
Nginx container
    |
    v
Django and Gunicorn container
    |
    +---- PostgreSQL container and private database volume
    |
    +---- private attachment volume
```

PostgreSQL must not have a public port. Private attachments must not be mounted into Nginx
or exposed as a public media directory.

### 1.1 What this architecture does not provide

A single VPS is a single point of failure. It does not provide automatic failover, a managed
database, geographic redundancy, or zero-downtime maintenance. It is appropriate for a small
deployment only when the organization accepts that recovery may require restoring onto a new
server.

For higher availability, move PostgreSQL, private files, secrets, and deployment into approved
managed services after reviewing the application's authorization boundary and storage behavior.

## 2. Responsibilities

Assign named people to these roles before production launch. One person may hold more than one
role, but every role needs a backup person.

- **Service owner:** approves production use, maintenance windows, and user access.
- **System administrator:** maintains the VPS, Docker, TLS, backups, monitoring, and releases.
- **Application administrator:** manages application users, roles, centers, and assignments.
- **Privacy or security contact:** decides incident escalation and notification actions.
- **Backup custodian:** controls backup credentials and performs restore tests.

Do not let a hosting provider, volunteer, or developer become the only person able to recover
the service. Store the following in the organization's approved password manager:

- VPS provider account and recovery codes;
- domain registrar and DNS account;
- SSH emergency access procedure;
- backup repository credentials;
- backup encryption password;
- Django secret key;
- database password; and
- current administrator contact list.

Require multi-factor authentication on the VPS provider, registrar, source host, monitoring
service, and backup provider accounts.

## 3. Production readiness gate

Do not enter real beneficiary data until all of the following are complete:

- [ ] The organization has signed the hosting provider's required data-processing agreement.
- [ ] The approved server location and backup locations are documented.
- [ ] External security review and threat modeling are complete.
- [ ] User acceptance testing used synthetic data only.
- [ ] PostgreSQL integration and concurrency tests passed.
- [ ] Account creation, removal, and periodic role review procedures are approved.
- [ ] The private attachment malware-scanning decision is recorded.
- [ ] Data retention, correction, export, deletion, and backup reconciliation policies exist.
- [ ] Monitoring and incident contacts have been tested.
- [ ] A complete backup restore has succeeded in an isolated environment.
- [ ] The service owner has signed off on production use.

Also review [Security and privacy](SECURITY_AND_PRIVACY.md),
[Backup and restore](BACKUP_AND_RESTORE.md), and the
[permission matrix](PERMISSION_MATRIX.md).

## 4. Purchase and configure the VPS

### 4.1 Provider requirements

Select a provider that offers:

- the approved country or region;
- a data-processing agreement when required;
- account multi-factor authentication;
- a provider-level firewall;
- console or rescue access;
- snapshots or server backups;
- security and abuse notifications; and
- a documented process for secure server deletion.

Provider snapshots are useful, but they are not the application backup. They may be stored in
the same provider account, have short retention, and may omit separately attached volumes.

### 4.2 Create the server

Create a server with these starting values:

| Setting | Recommended value |
| --- | --- |
| Operating system | Ubuntu Server 24.04 LTS, 64-bit |
| CPU | 2 vCPU |
| Memory | 4 GB |
| Root disk | 60 to 100 GB SSD |
| Region | Organization-approved location |
| IPv4 | Static public address |
| IPv6 | Optional, only if it will be configured and monitored |
| Backups | Enable provider backups in addition to application backups |
| Server name | `ssk-production-01` |

Upload an administrator SSH public key during creation. Do not enable password-based root login.

### 4.3 Configure the provider firewall first

Create the firewall before placing production data on the server.

| Direction | Protocol and port | Source | Purpose |
| --- | --- | --- | --- |
| Inbound | TCP 22 | Named administrator IPs only | SSH administration |
| Inbound | TCP 80 | Anywhere | HTTP redirect and certificate validation |
| Inbound | TCP 443 | Anywhere | HTTPS application access |
| Outbound | TCP 53 and UDP 53 | Provider or approved DNS | DNS resolution |
| Outbound | TCP 80 and 443 | Anywhere | Package, image, and certificate updates |
| Outbound | Backup protocol port | Backup provider | Off-host backups |
| Outbound | UDP 123 | Approved time source | Time synchronization |

If administrator IP addresses are not stable, use the provider's private network, a managed
VPN, or an approved access gateway. Do not permanently expose SSH to all addresses unless the
risk is explicitly accepted and additional controls are implemented.

Do not allow inbound TCP 5432. The database must remain private.

Docker creates host firewall rules for published container ports. UFW alone is not a reliable
control for those ports. Keep the provider firewall as the primary perimeter, publish only the
ports required by `docker-compose.prod.yml`, and verify the effective rules after every Compose
change.

### 4.4 Decide how employees reach the application

The application currently uses passwords and does not implement application-level multi-factor
authentication. Before launch, choose and document one of these access models:

- Restrict TCP 443 to office addresses and an approved remote-access VPN. This is preferred when
  all 10 employees can reliably use the VPN.
- Put the application behind an approved identity-aware access gateway that requires
  multi-factor authentication. Confirm that it preserves the trusted proxy headers described in
  this repository and does not replace the application's own authorization checks.
- Permit public HTTPS access only after the security owner accepts password-only application
  authentication and the remaining controls have been reviewed.

Keep TCP 80 available for the certificate-validation method in this runbook. If policy prohibits
public HTTP, use an approved DNS-based certificate-validation process instead and document its
credential and renewal controls.

## 5. DNS and naming

Choose one production hostname, for example `cases.example.org`.

1. Create an `A` record pointing the hostname to the VPS IPv4 address.
2. Create an `AAAA` record only if IPv6 is deliberately configured and filtered.
3. Use a short DNS TTL, such as 300 seconds, during initial deployment.
4. After the deployment is stable, increase the TTL according to organizational policy.
5. Verify from a different network:

   ```bash
   dig +short A cases.example.org
   dig +short AAAA cases.example.org
   ```

Do not continue to TLS issuance until DNS returns the correct address. Replace
`cases.example.org` in every command below with the real approved hostname.

## 6. First login and administrator account

Connect with the initial account supplied by the provider:

```bash
ssh root@SERVER_IPV4
```

Immediately confirm the operating system and time:

```bash
cat /etc/os-release
timedatectl status
ip address show
```

Create a named administrator. Replace `sskadmin` if the organization has a standard naming
scheme:

```bash
adduser --disabled-password --gecos "" sskadmin
usermod -aG sudo sskadmin
install -d -m 700 -o sskadmin -g sskadmin /home/sskadmin/.ssh
cp /root/.ssh/authorized_keys /home/sskadmin/.ssh/authorized_keys
chown sskadmin:sskadmin /home/sskadmin/.ssh/authorized_keys
chmod 600 /home/sskadmin/.ssh/authorized_keys
```

Open a second terminal and verify the new login before changing SSH settings:

```bash
ssh sskadmin@SERVER_IPV4
sudo -v
```

Keep the first root session open until the second session has succeeded.

## 7. Base operating-system hardening

### 7.1 Update the operating system

Run as `sskadmin`:

```bash
sudo apt update
sudo apt full-upgrade
sudo apt install ca-certificates curl git age restic unattended-upgrades apt-listchanges
sudo systemctl enable --now systemd-timesyncd
```

If `/var/run/reboot-required` exists, reboot and reconnect:

```bash
test ! -f /var/run/reboot-required || sudo reboot
```

After reconnecting:

```bash
timedatectl status
systemctl is-active systemd-timesyncd
```

All application timestamps use Django's configured timezone, while the server should normally
remain on UTC:

```bash
sudo timedatectl set-timezone UTC
```

### 7.2 Harden SSH

Create `/etc/ssh/sshd_config.d/00-ssk-hardening.conf` with:

```text
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
PermitEmptyPasswords no
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
MaxAuthTries 3
LoginGraceTime 30
AllowUsers sskadmin
```

Apply restrictive permissions and validate before reloading:

```bash
sudo chmod 600 /etc/ssh/sshd_config.d/00-ssk-hardening.conf
sudo sshd -t
sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication|kbdinteractiveauthentication|allowusers'
sudo systemctl reload ssh
```

Open another new SSH session and confirm access again. If validation fails, do not close the
existing session. Correct the configuration and rerun `sudo sshd -t`.

If SSH forwarding is needed for an approved administrative workflow, document the need and
enable only the minimum required feature.

### 7.3 Enable host firewall rules

UFW provides defense in depth for host services. The provider firewall remains authoritative
for Docker-published ports.

Replace `ADMIN_PUBLIC_IP` with a single approved address followed by `/32`:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from ADMIN_PUBLIC_IP/32 to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Never enable UFW until the correct SSH allow rule exists and a working second session is open.

### 7.4 Configure automatic security updates

Verify that unattended upgrades are enabled:

```bash
sudo dpkg-reconfigure --priority=low unattended-upgrades
systemctl status unattended-upgrades --no-pager
```

Review `/etc/apt/apt.conf.d/50unattended-upgrades`. Keep Ubuntu security updates enabled. Decide
whether automatic reboots are acceptable. A small production service should normally use a
scheduled maintenance window rather than an unannounced reboot.

Test configuration without changing packages:

```bash
sudo unattended-upgrade --dry-run --debug
```

The system administrator must still review pending updates weekly. Automatic updates do not
update application container images or Python dependencies.

### 7.5 Optional swap for a 4 GB server

Swap can reduce the chance of an abrupt out-of-memory termination, but it is not a substitute
for adequate RAM. First check whether swap already exists:

```bash
swapon --show
free -h
```

If no swap exists, create a 2 GB swap file:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
sudo sysctl vm.swappiness=10
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/60-ssk-swap.conf
```

Verify:

```bash
swapon --show
free -h
```

Do not place unencrypted secrets into swap if the provider and organizational threat model
require encrypted storage. Confirm the provider's storage controls before production approval.

## 8. Install Docker Engine

Use Docker's official Ubuntu repository. Do not use the convenience installation script in
production.

Remove conflicting packages if present:

```bash
for package in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  sudo apt remove -y "$package"
done
```

Add Docker's signing key and repository:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Configure bounded local container logs before starting production containers. Create
`/etc/docker/daemon.json`:

```json
{
  "log-driver": "local",
  "log-opts": {
    "max-size": "10m",
    "max-file": "5"
  }
}
```

Validate the JSON and restart Docker:

```bash
python3 -m json.tool /etc/docker/daemon.json >/dev/null
sudo systemctl enable docker
sudo systemctl restart docker
sudo docker version
sudo docker compose version
sudo docker info --format '{{.LoggingDriver}}'
```

Do not expose the Docker socket or daemon TCP port. Membership in the `docker` group is
effectively root-level access. This runbook uses `sudo docker` and does not add the administrator
to that group.

## 9. Place the application on the server

The recommended path is `/opt/ssk-case-management`.

For a public repository:

```bash
sudo git clone https://github.com/ORGANIZATION/REPOSITORY.git /opt/ssk-case-management
sudo chown -R root:root /opt/ssk-case-management
sudo chmod 755 /opt/ssk-case-management
cd /opt/ssk-case-management
sudo git status --short
```

For a private repository, use a read-only deploy key or an approved release artifact. Do not
store a developer's personal GitHub credential on the VPS. Restrict a deploy key to this one
repository and store its private half with mode `0600`.

Before deployment, record the exact revision:

```bash
cd /opt/ssk-case-management
sudo git rev-parse HEAD
```

Production should deploy a reviewed tag or commit, not an arbitrary working branch. The server
working tree must remain clean.

## 10. Create production secrets and configuration

Change to the application directory:

```bash
cd /opt/ssk-case-management
```

Generate a database password and Django secret on an administrator workstation or directly in
the protected server session:

```bash
openssl rand -hex 32
openssl rand -base64 64
```

Store both values in the approved password manager. Do not paste them into tickets, chat,
screenshots, shell history, or source control.

Create an empty `/opt/ssk-case-management/.env.production` with restrictive permissions before
opening it in an editor:

```bash
sudo install -m 600 -o root -g root /dev/null /opt/ssk-case-management/.env.production
sudoedit /opt/ssk-case-management/.env.production
```

Replace every placeholder with its approved value:

```text
POSTGRES_DB=ssk
POSTGRES_USER=ssk
POSTGRES_PASSWORD=REPLACE_WITH_GENERATED_HEX_DATABASE_PASSWORD
DATABASE_URL=postgresql://ssk:REPLACE_WITH_THE_SAME_DATABASE_PASSWORD@db:5432/ssk
DATABASE_SSLMODE=prefer

DJANGO_SECRET_KEY=REPLACE_WITH_GENERATED_DJANGO_SECRET
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=cases.example.org
DJANGO_CSRF_TRUSTED_ORIGINS=https://cases.example.org
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_TRUST_X_FORWARDED_FOR=1
DJANGO_TIME_ZONE=Asia/Tbilisi

PRIVATE_MEDIA_ROOT=/app/media/private
MAX_UPLOAD_SIZE=10485760
LOGIN_RATE_LIMIT_ATTEMPTS=5
LOGIN_RATE_LIMIT_WINDOW_SECONDS=900
```

Apply ownership and permissions:

```bash
sudo chown root:root /opt/ssk-case-management/.env.production
sudo chmod 600 /opt/ssk-case-management/.env.production
sudo stat -c '%A %U:%G %n' /opt/ssk-case-management/.env.production
```

The hexadecimal database password avoids URL-encoding mistakes in `DATABASE_URL`. If another
password format is used, its username and password components must be URL encoded.

Do not use the console, dummy, or in-memory email backend in production. Test real password
reset delivery before launch.

## 11. Obtain the initial TLS certificate

The included Nginx configuration expects these files:

```text
/opt/ssk-case-management/deploy/tls/fullchain.pem
/opt/ssk-case-management/deploy/tls/privkey.pem
```

Install Certbot using the organization's approved Ubuntu package or Snap packaging process. The
following uses the Ubuntu package:

```bash
sudo apt install certbot
sudo systemctl disable --now certbot.timer 2>/dev/null || true
```

Confirm that DNS points to the VPS, port 80 is open, and no service currently occupies port 80:

```bash
getent ahostsv4 cases.example.org
sudo ss -lntp | grep -E ':80\s' || true
```

Obtain a certificate with the standalone authenticator. Replace the email and hostname:

```bash
sudo certbot certonly --standalone --non-interactive --agree-tos \
  --email sysadmin@example.org \
  --cert-name cases.example.org \
  -d cases.example.org
```

Install a protected copy for the container:

```bash
sudo install -d -m 750 -o root -g root /opt/ssk-case-management/deploy/tls
sudo install -m 640 -o root -g root \
  /etc/letsencrypt/live/cases.example.org/fullchain.pem \
  /opt/ssk-case-management/deploy/tls/fullchain.pem
sudo install -m 640 -o root -g root \
  /etc/letsencrypt/live/cases.example.org/privkey.pem \
  /opt/ssk-case-management/deploy/tls/privkey.pem
```

Never commit `deploy/tls` or copy the private key to an administrator laptop.

### 11.1 Automate certificate renewal

Because the standalone authenticator needs port 80, renewal must briefly stop the Nginx
container. Create `/usr/local/sbin/ssk-cert-renew` owned by root:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR=/opt/ssk-case-management
DOMAIN=cases.example.org

start_proxy() {
  cd "$APP_DIR"
  docker compose -p ssk -f docker-compose.prod.yml start proxy >/dev/null 2>&1 || true
}

trap start_proxy EXIT

cd "$APP_DIR"
docker compose -p ssk -f docker-compose.prod.yml stop proxy
certbot renew --cert-name "$DOMAIN" --standalone --quiet "$@"
install -m 640 -o root -g root \
  "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" \
  "$APP_DIR/deploy/tls/fullchain.pem"
install -m 640 -o root -g root \
  "/etc/letsencrypt/live/$DOMAIN/privkey.pem" \
  "$APP_DIR/deploy/tls/privkey.pem"
```

Then:

```bash
sudo chown root:root /usr/local/sbin/ssk-cert-renew
sudo chmod 750 /usr/local/sbin/ssk-cert-renew
```

Create `/etc/systemd/system/ssk-cert-renew.service`:

```ini
[Unit]
Description=Renew and install the SSK TLS certificate
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/ssk-cert-renew
```

Create `/etc/systemd/system/ssk-cert-renew.timer`:

```ini
[Unit]
Description=Daily SSK TLS renewal check

[Timer]
OnCalendar=*-*-* 03:25:00
RandomizedDelaySec=30m
Persistent=true

[Install]
WantedBy=timers.target
```

Enable the timer after the first application deployment:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ssk-cert-renew.timer
systemctl list-timers ssk-cert-renew.timer
```

Test renewal after the application is running. The wrapper safely stops and restarts the proxy so
that Certbot can use port 80:

```bash
sudo /usr/local/sbin/ssk-cert-renew --dry-run
```

Also perform a controlled test of `/usr/local/sbin/ssk-cert-renew` during a maintenance window.
The external monitor should report the brief HTTPS interruption.

## 12. First application deployment

All Compose commands in this runbook use the project name `ssk`. This makes Docker volume names
predictable for backup and recovery.

Build the image:

```bash
cd /opt/ssk-case-management
sudo docker compose -p ssk -f docker-compose.prod.yml build --pull
```

Start only PostgreSQL:

```bash
sudo docker compose -p ssk -f docker-compose.prod.yml up -d db
sudo docker compose -p ssk -f docker-compose.prod.yml ps
```

Run migrations as a one-time release operation:

```bash
sudo docker compose -p ssk -f docker-compose.prod.yml run --rm web \
  python manage.py migrate --noinput
```

Run deployment checks:

```bash
sudo docker compose -p ssk -f docker-compose.prod.yml run --rm web \
  python manage.py check --deploy
sudo docker compose -p ssk -f docker-compose.prod.yml run --rm web \
  python manage.py makemigrations --check --dry-run
```

Start all services:

```bash
sudo docker compose -p ssk -f docker-compose.prod.yml up -d
sudo docker compose -p ssk -f docker-compose.prod.yml ps
```

Do not run `seed_demo_data` in production.

### 12.1 Create the first application administrator

Create one named System Manager account:

```bash
sudo docker compose -p ssk -f docker-compose.prod.yml exec web \
  python manage.py createsuperuser
```

Use a real, organization-controlled email address and a unique password stored in the approved
password manager. Do not create shared accounts. Create other users through the approved
application administration workflow and grant only the required role and center memberships.

## 13. Verify the production deployment

### 13.1 Server-side checks

```bash
cd /opt/ssk-case-management
sudo docker compose -p ssk -f docker-compose.prod.yml ps
sudo docker compose -p ssk -f docker-compose.prod.yml logs --tail=100 web proxy db
curl --fail --silent --show-error https://cases.example.org/en/health/
curl --head https://cases.example.org/en/login/
```

Confirm that PostgreSQL is not listening on a public host port:

```bash
sudo ss -lntup
sudo docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Expected public ports are TCP 80 and 443 on the proxy only. Port 5432 must not appear as a host
binding.

### 13.2 External checks

From a workstation on a different network:

```bash
curl --fail --silent --show-error https://cases.example.org/en/health/
curl --head http://cases.example.org/
openssl s_client -connect cases.example.org:443 -servername cases.example.org </dev/null
```

Confirm:

- HTTP redirects to HTTPS;
- the TLS certificate matches the hostname and is trusted;
- the login page loads without mixed content;
- debug error pages are disabled;
- cookies are Secure, HttpOnly, and use the expected SameSite policy;
- temporary-code login requires the employee to choose a private password before application access;
- an authorized administrator can generate a replacement code from the employee record;
- the health check returns successfully;
- unauthorized users cannot access records or private files;
- direct cross-center and unassigned URLs fail;
- audit events appear for sensitive actions; and
- logs do not contain beneficiary values, form bodies, credentials, or private filenames.

Do not submit the domain to browser HSTS preload lists during initial deployment. HSTS preload
has long-lived effects and requires a separate organizational decision.

## 14. Backups

Back up both PostgreSQL and private attachments. A database-only backup is incomplete, and a
provider snapshot is not a replacement for an application-level backup.

### 14.1 Backup objectives

The organization must define:

- recovery point objective, such as no more than 24 hours of data loss;
- recovery time objective, such as service restoration within one business day;
- retention periods, such as 7 daily, 5 weekly, and 12 monthly copies;
- the approved off-host storage region;
- backup and restore owners;
- backup encryption-key custody; and
- immutable or separately controlled backup requirements.

For a small deployment, run an encrypted off-host backup every night and before every release.

### 14.2 Configure an encrypted Restic repository

Restic encrypts repository content. Configure an approved S3-compatible bucket, SFTP target, or
other supported off-host repository. The backup must not rely on the VPS root disk.

Create `/etc/ssk-backup.env` with mode `0600`. The exact variables depend on the selected backend.
An S3-compatible example is:

```text
RESTIC_REPOSITORY=s3:https://OBJECT_STORAGE_ENDPOINT/ssk-production-backups
RESTIC_PASSWORD_FILE=/etc/ssk-restic-password
AWS_ACCESS_KEY_ID=REPLACE_WITH_BACKUP_ONLY_ACCESS_KEY
AWS_SECRET_ACCESS_KEY=REPLACE_WITH_BACKUP_ONLY_SECRET
```

Create a unique Restic repository password and store it in the password manager and
`/etc/ssk-restic-password`:

```bash
sudo chown root:root /etc/ssk-backup.env /etc/ssk-restic-password
sudo chmod 600 /etc/ssk-backup.env /etc/ssk-restic-password
```

Initialize once:

```bash
sudo bash -c 'set -a; source /etc/ssk-backup.env; set +a; restic init'
```

Grant the storage credential access only to the dedicated backup bucket or path. Where the
provider supports it, use object lock, immutable retention, or a second credential that the VPS
cannot use to delete backups.

### 14.3 Create the backup script

Create `/usr/local/sbin/ssk-backup`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

APP_DIR=/opt/ssk-case-management
STAGING_DIR=/var/backups/ssk/staging
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DB_FILE="$STAGING_DIR/ssk-db-$STAMP.dump"
MEDIA_FILE="$STAGING_DIR/ssk-private-media-$STAMP.tar.gz"
MANIFEST_FILE="$STAGING_DIR/SHA256SUMS-$STAMP"

restart_application() {
  cd "$APP_DIR"
  docker compose -p ssk -f docker-compose.prod.yml up -d web proxy >/dev/null 2>&1 || true
}

cleanup() {
  find "$STAGING_DIR" -maxdepth 1 -type f -delete
}

trap 'restart_application; cleanup' EXIT

install -d -m 700 -o root -g root "$STAGING_DIR"
cd "$APP_DIR"

docker compose -p ssk -f docker-compose.prod.yml stop proxy web

docker compose -p ssk -f docker-compose.prod.yml exec -T db sh -c \
  'pg_dump --format=custom --no-owner --username="$POSTGRES_USER" "$POSTGRES_DB"' \
  >"$DB_FILE"

docker run --rm \
  --volume ssk_private_media:/source:ro \
  --volume "$STAGING_DIR":/backup \
  alpine:3.22 \
  tar -C /source -czf "/backup/$(basename "$MEDIA_FILE")" .

sha256sum "$DB_FILE" "$MEDIA_FILE" >"$MANIFEST_FILE"

set -a
source /etc/ssk-backup.env
set +a
restic backup --tag ssk-production "$STAGING_DIR"
restic check --read-data-subset=1/20

restart_application
trap cleanup EXIT

curl --fail --silent --show-error https://cases.example.org/en/health/ >/dev/null
```

Replace the hostname in the final health check. Then:

```bash
sudo chown root:root /usr/local/sbin/ssk-backup
sudo chmod 750 /usr/local/sbin/ssk-backup
sudo install -d -m 700 -o root -g root /var/backups/ssk/staging
```

The backup pauses the web and proxy containers to keep the database and attachment archive close
to one recovery point. PostgreSQL remains running. Expect a short maintenance interruption.

The cleanup command is intentionally limited to regular files immediately inside the explicit
staging directory. Do not broaden its path or depth.

### 14.4 Schedule and retain backups

Create `/etc/systemd/system/ssk-backup.service`:

```ini
[Unit]
Description=Encrypted off-host backup of SSK Case Management
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/ssk-backup
```

Create `/etc/systemd/system/ssk-backup.timer`:

```ini
[Unit]
Description=Nightly SSK backup

[Timer]
OnCalendar=*-*-* 01:30:00
RandomizedDelaySec=20m
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and test:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ssk-backup.timer
sudo systemctl start ssk-backup.service
sudo systemctl status ssk-backup.service --no-pager
sudo journalctl -u ssk-backup.service --since today --no-pager
systemctl list-timers ssk-backup.timer
```

Configure retention as a separate scheduled and monitored command, for example:

```bash
sudo bash -c 'set -a; source /etc/ssk-backup.env; set +a; restic forget --keep-daily 7 --keep-weekly 5 --keep-monthly 12 --prune'
```

Approve retention values before enabling deletion. Repository pruning can be expensive and must
not overlap the normal backup window.

### 14.5 Backup monitoring

An administrator must receive an alert if:

- the backup service exits nonzero;
- no new snapshot appears within the recovery point objective;
- the repository fails `restic check`;
- storage quota is close to full; or
- credentials are near expiry.

At least weekly, list snapshots:

```bash
sudo bash -c 'set -a; source /etc/ssk-backup.env; set +a; restic snapshots --tag ssk-production'
```

A successful timer invocation is not sufficient evidence. Confirm that a new, readable off-host
snapshot exists.

## 15. Restore procedure

Perform a restore rehearsal at least quarterly and after major storage or database changes.
Never test a restore over the running production database.

### 15.1 Prepare an isolated restore server

1. Create a new temporary VPS on an isolated firewall or private network.
2. Install the same major Docker and Compose versions.
3. Deploy the exact application revision recorded with the backup.
4. Block all employee access.
5. Create an empty production-shaped Compose environment with new temporary secrets.

### 15.2 Retrieve one recovery point

On the isolated server, configure read-only backup credentials where possible, then:

```bash
sudo install -d -m 700 /var/restore/ssk
sudo bash -c 'set -a; source /etc/ssk-backup.env; set +a; restic snapshots --tag ssk-production'
sudo bash -c 'set -a; source /etc/ssk-backup.env; set +a; restic restore SNAPSHOT_ID --target /var/restore/ssk'
```

Locate the database dump, media archive, and checksum manifest under the restored staging path.
Verify checksums from that directory:

```bash
sha256sum --check SHA256SUMS-TIMESTAMP
```

### 15.3 Restore PostgreSQL and private files

Start only the empty database:

```bash
cd /opt/ssk-case-management
sudo docker compose -p ssk -f docker-compose.prod.yml up -d db
```

Restore the database dump into the empty database:

```bash
sudo docker compose -p ssk -f docker-compose.prod.yml exec -T db sh -c \
  'pg_restore --exit-on-error --no-owner --clean --if-exists --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  </var/restore/ssk/PATH/ssk-db-TIMESTAMP.dump
```

Restore private files only into the empty restore volume:

```bash
sudo docker run --rm \
  --volume ssk_private_media:/destination \
  --volume /var/restore/ssk/PATH:/backup:ro \
  alpine:3.22 \
  tar -C /destination -xzf /backup/ssk-private-media-TIMESTAMP.tar.gz
```

Start the web container without exposing the service publicly, run migrations for the restored
revision, and perform the checks in [Backup and restore](BACKUP_AND_RESTORE.md).

Before any real disaster-recovery cutover:

- reconcile privacy corrections and removals that occurred after the backup timestamp;
- verify users, groups, center memberships, and specialist assignments;
- verify reports, exports, audit continuity, and authorized downloads;
- record the unavoidable audit or data gap;
- update DNS only after security and business approval; and
- securely dispose of temporary decrypted restore files.

## 16. Monitoring and alerting

### 16.1 External monitoring

Monitor this URL from outside the VPS:

```text
https://cases.example.org/en/health/
```

Use at least two alert recipients. Configure checks every one to five minutes and alert after a
small number of consecutive failures. Also monitor certificate expiry and DNS resolution.

The health endpoint proves that the web application can respond. It does not replace login,
database, email, authorization, attachment, backup, or restore tests.

### 16.2 Host and container monitoring

Alert on:

- root disk usage above 80 percent;
- sustained memory pressure or swapping;
- repeated container restarts;
- unhealthy containers;
- high HTTP 500, 403, or login-block rates;
- backup failure or age;
- certificate expiry within 21 days;
- time synchronization failure; and
- provider security or abuse notifications.

Useful commands:

```bash
df -h
df -i
free -h
uptime
systemctl --failed
sudo docker compose -p ssk -f /opt/ssk-case-management/docker-compose.prod.yml ps
sudo docker stats --no-stream
sudo journalctl -p warning --since '24 hours ago' --no-pager
sudo docker system df
```

Do not send beneficiary values, request bodies, private filenames, credentials, session cookies,
or database contents to the monitoring system.

### 16.3 Log review

Review logs without copying sensitive content into general tickets:

```bash
cd /opt/ssk-case-management
sudo docker compose -p ssk -f docker-compose.prod.yml logs --since=24h web proxy db
sudo journalctl -u ssh --since=24h --no-pager
sudo journalctl -u unattended-upgrades --since='7 days ago' --no-pager
```

The included proxy logging format omits query strings. Preserve this property when changing log
collection.

## 17. Routine system administration schedule

### Daily automated tasks

- Encrypted off-host backup.
- Certificate renewal check.
- External health and certificate monitoring.
- Provider and operating-system security notifications.

### Weekly administrator tasks

- [ ] Confirm the most recent backup snapshot exists and is within the recovery point objective.
- [ ] Review failed systemd services and container health.
- [ ] Review disk, inode, memory, and swap usage.
- [ ] Review pending Ubuntu, Docker, and application dependency security updates.
- [ ] Review authentication failures and unusual 403, 404, and 500 patterns.
- [ ] Confirm time synchronization.
- [ ] Check that PostgreSQL still has no published host port.
- [ ] Confirm provider firewall rules have not drifted.

### Monthly tasks

- [ ] Apply reviewed operating-system and Docker updates in a maintenance window.
- [ ] Pull and rebuild approved base images.
- [ ] Run application tests and security scans before deploying dependency changes.
- [ ] Test temporary access-code creation, required password change, and administrator reset.
- [ ] Review application administrator accounts and provider account access.
- [ ] Review storage growth and forecast capacity.
- [ ] Test monitoring alerts and escalation contacts.
- [ ] Review certificate timer and backup timer history.
- [ ] Record the deployed revision and image identifiers.

### Quarterly tasks

- [ ] Perform and document a complete isolated restore rehearsal.
- [ ] Review all application users, roles, center memberships, and specialist assignments.
- [ ] Review SSH keys, deploy keys, service credentials, and recovery contacts.
- [ ] Review retention and securely remove approved expired data and backups.
- [ ] Review the incident-response exercise and update the runbook.
- [ ] Confirm data-processing agreements and server and backup locations remain approved.

### Annual tasks

- [ ] Commission the required security and privacy review.
- [ ] Review the threat model and malware-scanning decision.
- [ ] Review capacity, availability, recovery objectives, and whether a single VPS remains suitable.
- [ ] Review Ubuntu LTS and PostgreSQL support timelines.
- [ ] Exercise total VPS loss and rebuild from source plus off-host backup.

## 18. Application release procedure

Use a planned maintenance window. Never deploy directly from an unreviewed developer working
tree.

### 18.1 Before the window

In development or CI, run:

```bash
pytest
ruff check .
ruff format --check .
python manage.py check
python manage.py makemigrations --check --dry-run
```

Also run PostgreSQL-backed acceptance tests and the approved image and dependency security scans.
Review migrations, release notes, configuration changes, storage changes, and rollback limits.

Record:

- old and new Git revisions;
- image digest or build record;
- migration plan;
- backup snapshot ID;
- deployment owner;
- rollback decision owner; and
- expected user-visible interruption.

### 18.2 Deploy

On the server:

```bash
cd /opt/ssk-case-management
sudo git status --short
sudo git fetch --tags --prune
sudo git checkout REVIEWED_TAG_OR_COMMIT
sudo git rev-parse HEAD
```

Stop if the working tree is not clean or the revision is not the reviewed revision.

Run a pre-release backup and confirm that it succeeded:

```bash
sudo systemctl start ssk-backup.service
sudo systemctl status ssk-backup.service --no-pager
```

Build the new image without stopping the current service:

```bash
sudo docker compose -p ssk -f docker-compose.prod.yml build --pull web
```

Run release checks and migrations:

```bash
sudo docker compose -p ssk -f docker-compose.prod.yml run --rm web \
  python manage.py check --deploy
sudo docker compose -p ssk -f docker-compose.prod.yml run --rm web \
  python manage.py makemigrations --check --dry-run
sudo docker compose -p ssk -f docker-compose.prod.yml run --rm web \
  python manage.py migrate --noinput
```

Recreate services and verify:

```bash
sudo docker compose -p ssk -f docker-compose.prod.yml up -d
sudo docker compose -p ssk -f docker-compose.prod.yml ps
curl --fail --silent --show-error https://cases.example.org/en/health/
sudo docker compose -p ssk -f docker-compose.prod.yml logs --tail=100 web proxy
```

Complete role-specific smoke tests using approved test records. Confirm temporary-code login,
required password change, administrator access-code reset, center selection, cross-center denial,
private downloads, reports, CSV safeguards, and audit events.

### 18.3 Rollback

Database migrations may make an old application image incompatible with the new schema. Prefer a
forward fix. Do not automatically restore an old database over production.

If the migration is backward compatible and the rollback owner approves:

1. Check out the recorded old revision.
2. Rebuild its image.
3. Recreate the web service.
4. Re-run health and authorization checks.

If database restoration is required, isolate the application, preserve the failed state, and
restore both database and private files from the same approved recovery point. Reconcile later
privacy changes before reopening access.

## 19. Patch and reboot procedure

Schedule a maintenance window and confirm a current off-host backup.

```bash
sudo apt update
apt list --upgradable
sudo apt full-upgrade
```

If Docker was updated, restart it during the window and verify all containers:

```bash
sudo systemctl restart docker
sudo docker compose -p ssk -f /opt/ssk-case-management/docker-compose.prod.yml ps
```

If a reboot is required:

```bash
test -f /var/run/reboot-required && cat /var/run/reboot-required.pkgs
sudo reboot
```

After reconnecting:

```bash
uptime
systemctl --failed
sudo docker compose -p ssk -f /opt/ssk-case-management/docker-compose.prod.yml ps
curl --fail --silent --show-error https://cases.example.org/en/health/
sudo systemctl status ssk-backup.timer ssk-cert-renew.timer --no-pager
```

Docker restart policies should restart the containers after boot. Do not assume this worked
without verification.

## 20. Account and key administration

### Employee onboarding

1. Confirm written authorization from the service owner.
2. Create an individual account, never a shared account.
3. Grant only the required group, center memberships, and specialist assignments.
4. Deliver the initial access method through an approved channel.
5. Require a unique password.
6. Verify access with synthetic or approved training data.
7. Record the approver and date without copying passwords.

### Employee role change

Update center memberships, specialist assignments, and groups immediately after approval. Test
that removed access no longer works through lists, direct URLs, reports, exports, and private
downloads.

### Employee departure

1. Disable the application account at the agreed effective time.
2. Remove active sessions according to the approved procedure.
3. Remove provider, source, monitoring, and backup access if applicable.
4. Remove or rotate SSH and deploy keys.
5. Rotate shared secrets if the person knew them.
6. Preserve required audit evidence.
7. Record completion and reviewer approval.

### Secret rotation

Rotate credentials after suspected exposure, administrator departure, provider compromise, or
the organization's scheduled interval. Changing the Django secret key invalidates signed values
and can affect active sessions. Changing the database password requires coordinated PostgreSQL
and `DATABASE_URL` updates. Take a backup, use a maintenance window, and test before reopening.

## 21. Incident response

For suspected unauthorized access, malware, credential exposure, or data loss:

1. Notify the named security or privacy contact immediately.
2. Restrict access using the provider firewall or stop the proxy container.
3. Do not destroy the server, logs, volumes, or snapshots before evidence decisions are made.
4. Revoke exposed sessions, SSH keys, API tokens, and passwords as directed.
5. Identify affected users, records, files, integrations, backups, and time range.
6. Keep beneficiary information out of ordinary tickets, email, and chat.
7. Preserve authorized evidence with timestamps and access controls.
8. Restore or rebuild in an isolated environment when required.
9. Perform legal and contractual notification decisions through the approved owner.
10. Document containment, investigation, remediation, recovery, and approval to reopen.

To take the application offline while retaining SSH access:

```bash
cd /opt/ssk-case-management
sudo docker compose -p ssk -f docker-compose.prod.yml stop proxy
```

Do not run destructive cleanup commands during an incident unless the incident lead has approved
the exact targets and evidence has been preserved.

## 22. Capacity management

Ten users should fit comfortably on the recommended server, but attachment growth and reports
can change resource needs. Review:

```bash
df -h
free -h
sudo docker stats --no-stream
sudo docker system df
sudo docker compose -p ssk -f /opt/ssk-case-management/docker-compose.prod.yml exec -T db \
  sh -c 'psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" -c "SELECT pg_size_pretty(pg_database_size(current_database()));"'
```

Upgrade or redesign before sustained usage reaches these operational thresholds:

- root disk above 80 percent;
- recurring out-of-memory events or significant swap use;
- sustained high CPU during normal work;
- backup duration approaching the available maintenance window; or
- restore duration exceeding the approved recovery time objective.

Do not use `docker system prune --volumes`. It can remove data-bearing volumes. Clean up only
specific, verified unused images after confirming current backups and active references.

## 23. Decommissioning

Decommission only with written approval from the service owner and privacy or security owner.

1. Disable employee access and place the application offline.
2. Create the required final encrypted backup and verify it.
3. Record the final application revision, migration state, and backup snapshot ID.
4. Apply the approved data-retention decision to the final backup.
5. Export only approved records through authorized workflows.
6. Revoke backup, source, DNS, monitoring, and infrastructure credentials.
7. Remove DNS records after the approved notice period.
8. Delete the VPS and attached volumes through the provider's documented process.
9. Delete unneeded provider snapshots and backups after retention approval.
10. Remove administrator SSH keys and deploy keys.
11. Record deletion evidence without copying beneficiary data.
12. Confirm that billing and monitoring have stopped.

Never delete the production VPS until the final backup has been restored successfully or the
authorized owner has explicitly approved destruction without retention.

## 24. Command reference

Run application commands from `/opt/ssk-case-management`:

```bash
# Service status
sudo docker compose -p ssk -f docker-compose.prod.yml ps

# Recent logs
sudo docker compose -p ssk -f docker-compose.prod.yml logs --tail=200 web proxy db

# Follow logs temporarily
sudo docker compose -p ssk -f docker-compose.prod.yml logs --follow web proxy

# Restart the web application
sudo docker compose -p ssk -f docker-compose.prod.yml restart web

# Stop public access
sudo docker compose -p ssk -f docker-compose.prod.yml stop proxy

# Restore public access
sudo docker compose -p ssk -f docker-compose.prod.yml up -d proxy

# Django production check
sudo docker compose -p ssk -f docker-compose.prod.yml exec web python manage.py check --deploy

# Migration status
sudo docker compose -p ssk -f docker-compose.prod.yml exec web python manage.py showmigrations

# Health check
curl --fail --silent --show-error https://cases.example.org/en/health/

# Timer status
systemctl list-timers ssk-backup.timer ssk-cert-renew.timer

# Backup logs
sudo journalctl -u ssk-backup.service --since='7 days ago' --no-pager

# Certificate information
sudo certbot certificates
openssl s_client -connect cases.example.org:443 -servername cases.example.org </dev/null 2>/dev/null \
  | openssl x509 -noout -issuer -subject -dates
```

## 25. Handover record

Complete and store this record in the approved administrative system:

```text
Service owner:
Primary system administrator:
Backup system administrator:
Privacy or security contact:
Production hostname:
VPS provider and account owner:
Server ID and approved region:
Domain registrar and account owner:
Monitoring provider and alert recipients:
Backup provider, bucket or path, and region:
Password manager record locations:
Current deployed Git revision:
Last successful backup timestamp and snapshot ID:
Last successful restore rehearsal date:
Recovery point objective:
Recovery time objective:
Normal maintenance window:
Next access review date:
Next restore test date:
Next security review date:
```

## 26. Authoritative technical references

- [Docker Engine installation on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Docker packet filtering and firewall behavior](https://docs.docker.com/engine/network/packet-filtering-firewalls/)
- [Ubuntu OpenSSH server guidance](https://ubuntu.com/server/docs/how-to/security/openssh-server/)
- [Ubuntu automatic update guidance](https://ubuntu.com/server/docs/how-to/software/automatic-updates/)
- [Certbot usage and automated renewal](https://eff-certbot.readthedocs.io/en/stable/using.html)
- [Restic documentation](https://restic.readthedocs.io/en/stable/)
- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)

Provider-specific instructions change over time. Verify the current provider documentation before
creating firewall rules, backup storage, snapshots, or data-processing agreements.
