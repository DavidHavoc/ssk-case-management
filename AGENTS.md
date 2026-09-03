# Repository instructions

- Never use em dashes.
- Do not add real beneficiary data, credentials, or production exports.
- Keep authorization checks in server-side selectors, forms, and views.
- Run tests, Ruff, Django checks, and migration checks before handoff.

## Current VPS status

Last verified: 2026-09-03.

- An IONOS VPS exists with Ubuntu 24.04.4 LTS, 4 GB RAM, and a 120 GB disk. It had approximately 114 GB free when checked.
- From this desktop host, SSH works through the `ssk-production` host alias as the `sskadmin` user. Do not request, reveal, copy, or modify SSH private keys or passwords.
- The server has a temporary IONOS hostname that resolves to its VPS address. Use a domain controlled by the organization before any real deployment.
- Docker, the application, TLS, backups, monitoring, and production data have not been deployed.
- A temporary passwordless-sudo rule used for connection testing was removed. Do not recreate it unless the user explicitly authorizes temporary remote administrator access.
- The last read-only check found that root SSH login and SSH password authentication were still enabled, and UFW was inactive. Treat the server as not production-ready until those settings are corrected and the full production runbook is completed.
- Do not deploy or place real beneficiary data on the VPS without an explicit user request. When deployment is requested, follow `docs/VPS_OPERATIONS_RUNBOOK.md` and `docs/PRODUCTION_DEPLOYMENT.md`, beginning with fresh security and readiness checks.
