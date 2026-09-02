# Runbook: Restore PostgreSQL from S3 Backup

| Field | Value |
|-------|-------|
| Service | Velobits-Projects backend |
| RPO | 24 hours (daily cron backup) |
| RTO | ~2 hours |
| Last reviewed | — |
| Owner | Backend on-call |

---

## Overview

Backups are created daily by `scripts/backup-postgres.sh` and stored in S3
under the prefix `backups/fixmytext/` as gzip-compressed pg_dump files named
`fixmytext-<YYYYMMDDTHHMMSSZ>.sql.gz`.

This runbook covers a full point-in-time restore to a scratch database,
verification, and promotion to production.

Production runs on a **remote managed Postgres** (see
[octopus-setup.md](../octopus-setup.md) Stage B1) and the application
runs on the Oracle VM, deployed by Octopus. Promotion therefore means pointing
`DATABASE_URL` at the restored database and redeploying — the VM holds no
product data, so there is nothing to restore *on* the host.

---

## Prerequisites

- **AWS CLI** configured with read access to `S3_BUCKET`
- **psql** (v16 recommended) — or Docker available to run `postgres:16`
- **alembic** installed in your local virtualenv (`pip install alembic`)
- Access to the managed-database console (to create the scratch database and
  read connection URIs) and to the Octopus portal (to change `DATABASE_URL` and
  redeploy)
- Environment variables set locally:
  ```
  export S3_BUCKET=<your-bucket-name>
  export S3_PREFIX=backups/fixmytext   # or your configured prefix
  ```

---

## Step 1 — List Available Backups

```bash
aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" --human-readable --summarize \
  | sort
```

Identify the backup file you want to restore. Copy the exact filename, e.g.:

```
fixmytext-20260614T020000Z.sql.gz
```

---

## Step 2 — Download the Chosen Backup

```bash
BACKUP_FILE="fixmytext-20260614T020000Z.sql.gz"   # replace with target file

aws s3 cp "s3://${S3_BUCKET}/${S3_PREFIX}/${BACKUP_FILE}" "/tmp/${BACKUP_FILE}"

echo "Download complete: /tmp/${BACKUP_FILE}"
ls -lh "/tmp/${BACKUP_FILE}"
```

---

## Step 3 — Spin Up a Scratch Postgres Instance

> Skip if you already have a spare Postgres 16 instance available and jump to
> Step 4, substituting your connection details.

```bash
docker run --rm -d \
  --name pg-restore-scratch \
  -e POSTGRES_PASSWORD=restorepass \
  -e POSTGRES_DB=fixmytext_restore \
  -p 5433:5432 \
  postgres:16

# Wait for Postgres to be ready (up to 30 s)
for i in $(seq 1 30); do
  docker exec pg-restore-scratch pg_isready -U postgres && break
  sleep 1
done

echo "Scratch DB ready."
```

Scratch `DATABASE_URL` for subsequent steps:

```
export SCRATCH_DB_URL="postgresql://postgres:restorepass@localhost:5433/fixmytext_restore"
```

---

## Step 4 — Restore the Backup

```bash
BACKUP_FILE="fixmytext-20260614T020000Z.sql.gz"   # same file as Step 2

gunzip -c "/tmp/${BACKUP_FILE}" | psql "${SCRATCH_DB_URL}"

echo "Restore complete."
```

Expected output: a stream of `CREATE TABLE`, `COPY`, `ALTER TABLE`, `CREATE INDEX`
lines with no `ERROR:` lines. A few `WARNING:` lines about existing objects are
acceptable when restoring into a pre-initialised schema; errors are not.

---

## Step 5 — Verify Migrations

Run alembic against the scratch DB and confirm the revision matches HEAD.

```bash
# From the backend/ repo root
cd /home/dev/Documents/ME/Velobits-Projects/FixMyText-backend

DATABASE_URL="${SCRATCH_DB_URL}" alembic current
DATABASE_URL="${SCRATCH_DB_URL}" alembic heads
```

Both commands must report the same revision hash.  If `current` is behind
`heads`, the backup predates a migration; apply pending migrations before
promoting:

```bash
DATABASE_URL="${SCRATCH_DB_URL}" alembic upgrade head
```

Confirm again:

```bash
DATABASE_URL="${SCRATCH_DB_URL}" alembic current
```

---

## Step 6 — Smoke Test Service Health Endpoints

Start each service locally (or in Docker) pointed at the scratch DB and hit
its health endpoint.  All must return HTTP 200.

```bash
# Example: run the API against the scratch DB
DATABASE_URL="${SCRATCH_DB_URL}" uvicorn app.main:app --port 8001 &
API_PID=$!
sleep 3

curl -sf http://localhost:8001/health && echo "API: OK" || echo "API: FAILED"
curl -sf http://localhost:8001/api/v1/health && echo "v1 health: OK" || echo "v1 health: FAILED"

kill "${API_PID}"
```

Repeat for any additional services (worker, scheduler, etc.) that share the
same database.  Do not proceed to Step 7 until all health checks pass.

---

## Step 7 — Promote

> **Warning**: this step cuts production over to the restored data. Confirm the
> restore and smoke tests passed before continuing.

### 7a. Point DATABASE_URL at the restored database

1. Octopus → project `fixmytext-backend` → **Variables**.
2. Edit `DATABASE_URL`, scoped to the **Production** environment, to the
   restored database's connection string.
3. Keep the SQLAlchemy + asyncpg form, and note asyncpg spells TLS `ssl=`, not
   libpq's `sslmode=`:
   ```
   postgresql+asyncpg://<user>:<pass>@<host>:<port>/<restored_db>?ssl=require
   ```
4. Restrict the new database's allowed IP addresses to the VM's public IP if it
   is a newly provisioned service.

### 7b. Redeploy

Octopus → project → **Releases** → the currently deployed release →
**Deploy to Production**. Redeploying the *same* release is deliberate: it
changes only the rendered `.env`, not the application version.

`octopus/deploy.sh` will run `alembic upgrade head` against the restored
database before starting any service. If the dump predates the current code, the
outstanding migrations apply here — which is the intended path, but means the
deploy fails (before serving traffic) if any of them cannot apply.

### 7c. Monitor

The deploy gates on health itself: it waits for every service to report healthy
and then proves Kong routes a live request, so a green Octopus task already
means the stack serves. To watch it directly on the VM:

```bash
docker compose -f docker-compose-prod.yml logs -f --tail 100
```

Then confirm from outside:

```bash
curl -sf https://api.fixmytext.velobits.dev/health && echo "Production: OK"
```

If the deploy fails, the previous containers are still running against the OLD
`DATABASE_URL` only if compose did not recreate them — assume it did, and treat
a failed promotion as an outage: revert the variable and redeploy.

### 7d. Clean Up Scratch Resources

```bash
docker stop pg-restore-scratch   # container auto-removes due to --rm
rm "/tmp/${BACKUP_FILE}"
```

---

## Monthly Verification Cadence

On the first Tuesday of each month, perform a dry-run restore to confirm
backup integrity:

1. Complete Steps 1-5 against the most recent backup.
2. Record the alembic revision and row counts for the three largest tables:
   ```sql
   SELECT relname, n_live_tup
   FROM pg_stat_user_tables
   ORDER BY n_live_tup DESC
   LIMIT 5;
   ```
3. Log the result in the team's on-call notes with the date and backup filename.
4. Tear down the scratch container (Step 7d).

No promotion to production is required for the monthly drill.
