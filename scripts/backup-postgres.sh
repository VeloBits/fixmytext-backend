#!/usr/bin/env bash
# backup-postgres.sh - Production pg_dump to S3 for Velobits-Projects backend
#
# Usage:
#   ./scripts/backup-postgres.sh
#
# Required environment variables:
#   DATABASE_URL   Full PostgreSQL connection string, e.g.
#                  postgresql://user:pass@host:5432/dbname
#   S3_BUCKET      Destination S3 bucket name, e.g. my-company-backups
#
# Optional environment variables:
#   AWS_PROFILE    AWS credentials profile (default: the environment default)
#   S3_PREFIX      Key prefix inside the bucket (default: backups/fixmytext)
#
# Railway cron setup note:
#   Add a Railway cron service pointing at this script.
#   Set DATABASE_URL and S3_BUCKET as Railway service variables.
#   Recommended schedule: 0 2 * * *  (daily at 02:00 UTC)
#   Ensure the Railway service image includes pg_dump (postgres-client) and
#   the AWS CLI.  A minimal Dockerfile FROM debian:bookworm-slim works well:
#     RUN apt-get update && apt-get install -y postgresql-client awscli

set -euo pipefail

# ---------------------------------------------------------------------------
# Validate required env vars
# ---------------------------------------------------------------------------
if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is not set." >&2
  exit 1
fi

if [ -z "${S3_BUCKET:-}" ]; then
  echo "ERROR: S3_BUCKET is not set." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
S3_PREFIX="${S3_PREFIX:-backups/fixmytext}"
RETENTION_DAYS=30

# ---------------------------------------------------------------------------
# Derive a timestamp-based filename
# ---------------------------------------------------------------------------
TIMESTAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
FILENAME="fixmytext-${TIMESTAMP}.sql.gz"
S3_KEY="${S3_PREFIX}/${FILENAME}"
S3_URI="s3://${S3_BUCKET}/${S3_KEY}"

# ---------------------------------------------------------------------------
# Run backup
# ---------------------------------------------------------------------------
echo "INFO: Starting backup - ${TIMESTAMP}"
echo "INFO: Destination: ${S3_URI}"

pg_dump "${DATABASE_URL}" \
  | gzip \
  | aws s3 cp - "${S3_URI}" \
      --content-type "application/gzip" \
      --storage-class STANDARD_IA

echo "INFO: Backup complete - ${S3_URI}"

# ---------------------------------------------------------------------------
# Prune backups older than RETENTION_DAYS days
# ---------------------------------------------------------------------------
echo "INFO: Pruning backups older than ${RETENTION_DAYS} days from s3://${S3_BUCKET}/${S3_PREFIX}/"

CUTOFF="$(date -u -d "${RETENTION_DAYS} days ago" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
  || date -u -v "-${RETENTION_DAYS}d" '+%Y-%m-%dT%H:%M:%SZ')"

echo "INFO: Cutoff date: ${CUTOFF}"

aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" \
  | while read -r DATE TIME SIZE KEY; do
      OBJECT_DATE="${DATE}T${TIME}Z"
      if [ "${OBJECT_DATE}" \< "${CUTOFF}" ]; then
        echo "INFO: Deleting old backup: ${KEY}"
        aws s3 rm "s3://${S3_BUCKET}/${S3_PREFIX}/${KEY}"
      fi
    done

echo "INFO: Prune complete."
echo "INFO: Done."
