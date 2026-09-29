#!/usr/bin/env bash
# MySQL 백업 실패를 Slack으로 알린다. orderrun-mysql-backup-alert@<env>.service가 호출한다.
# webhook URL은 ~/orderrun-db/backup-alert.env(600)에서만 받는다.
set -euo pipefail

env_name="${1:-unknown}"
url="${BACKUP_ALERT_WEBHOOK_URL:?BACKUP_ALERT_WEBHOOK_URL is required}"
text="[orderrun] MySQL ${env_name} 백업 실패 ($(hostname), $(date -u +%Y-%m-%dT%H:%M:%SZ)). journalctl -u orderrun-mysql-backup@${env_name} 확인"

curl -fsS -m 10 -H 'Content-Type: application/json' --data "{\"text\":\"${text}\"}" "$url" > /dev/null
