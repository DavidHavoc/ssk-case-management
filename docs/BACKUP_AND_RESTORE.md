# Backup and Restore

Backups contain sensitive beneficiary data. Encrypt backup storage and transport, separate archive access from encryption-key custody, and document every recovery operation.

## Backup contents

A recoverable point requires:

- a PostgreSQL logical or physical backup;
- the complete private-file volume;
- the deployed application revision and migration state;
- non-secret configuration inventory;
- encryption-key recovery instructions stored separately.

Do not place `.env.production`, passwords, or raw secret keys inside the application repository.

## Example logical backup

Create an operator-controlled work directory with restrictive permissions. Replace placeholders with explicit approved paths. Avoid broad recursive commands.

```bash
umask 077
pg_dump --format=custom --no-owner --file=/approved/backup/ssk-db.dump "$DATABASE_URL"
tar -C /approved/private-volume -czf /approved/backup/ssk-private-files.tar.gz .
sha256sum /approved/backup/ssk-db.dump /approved/backup/ssk-private-files.tar.gz \
  > /approved/backup/SHA256SUMS
```

Encrypt the database dump, file archive, and checksum manifest with an approved tool such as age, GPG, or a cloud key-management service. Copy only encrypted artifacts to off-host storage. Verify checksums after transfer.

The organization must define frequency, retention, geographic location, immutable-copy policy, owners, key custodians, recovery point objective, and recovery time objective.

## Restore rehearsal

Use an isolated network and a new empty PostgreSQL database. Do not restore over a running production database.

```bash
createdb <isolated-restore-database>
pg_restore --exit-on-error --no-owner --dbname=<isolated-restore-database> \
  /approved/restore/ssk-db.dump
mkdir -p /approved/restore/private-files
tar -C /approved/restore/private-files -xzf /approved/restore/ssk-private-files.tar.gz
```

Point a staging Django instance at the restored database and private-file directory. Then:

1. keep all external user access blocked;
2. verify artifact checksums and backup timestamps;
3. run `manage.py check` and pending migration review;
4. verify User roles, staff center memberships, and specialist assignments;
5. test cross-center URLs, reports, exports, and private downloads;
6. reconcile privacy corrections or removals that occurred after the backup timestamp;
7. verify audit continuity and document any unavoidable gap;
8. obtain business, security, and operational approval before any production cutover.

## Restoration caveats

Restoring an older backup can reintroduce identifiers or files that were corrected or removed later. Automated retention, erasure replay, and privacy-request reconciliation are not implemented in the MVP. Maintain a controlled reconciliation record outside the backup until an approved in-application workflow exists.

## Disposal

Expired encrypted archives, temporary decrypted files, restore databases, and restore volumes must be disposed of through the approved secure process. Verify scope before deletion and record evidence without copying sensitive values.
