# Repository instructions

- Never use em dashes.
- Do not add real beneficiary data, credentials, or production exports.
- Keep authorization checks in server-side selectors, forms, and views.
- Run tests, Ruff, Django checks, and migration checks before handoff.

## Current VPS status

Last verified: 2026-09-03.

- The IONOS VPS runs Ubuntu 24.04.4 LTS with 4 GB RAM and a 120 GB disk. It had approximately 112 GB free after deployment checks.
- From this desktop host, SSH works through the `ssk-production` host alias as the `sskadmin` user. Do not request, reveal, copy, or modify SSH private keys or passwords.
- The staged application is available at `https://0ufkrzj.cserverhost.cloud` using a trusted temporary TLS certificate. Replace this provider hostname with an organization-controlled domain before real use.
- Docker Engine and Compose are installed. The application runs from `/opt/ssk-case-management` with Nginx, Django and Gunicorn, and PostgreSQL 16. PostgreSQL and Gunicorn have no public host ports.
- Root SSH login, SSH password authentication, interactive authentication, and SSH forwarding are disabled. UFW allows SSH only from the administrator address used during deployment and allows public HTTP and HTTPS.
- The PostgreSQL production database contains migrations and reference catalogs but no users or beneficiaries. Do not run `seed_demo_data`, create users, or add beneficiary data until every readiness gate is complete.
- The certificate-renewal service and timer are installed and passed a staging renewal test. The ACME account currently has no operational contact email.
- An empty-database backup and restore rehearsal passed in an isolated temporary container. Encrypted off-host backups, retention, backup monitoring, and a restore on a separate host are not configured.
- External uptime and alert monitoring and the provider firewall configuration are not verified. Treat the server as a staged deployment that is not approved for real data or users.
- The temporary passwordless-sudo deployment rule was removed after deployment. Do not recreate it unless the user explicitly authorizes temporary remote administrator access.
