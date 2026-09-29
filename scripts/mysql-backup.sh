#!/usr/bin/env bash
# EC2 내부 MySQL 논리 백업: mysqldump → gzip → S3.
# systemd 템플릿 유닛 orderrun-mysql-backup@<env>.service가 환경별로 호출한다.
# 설정은 ~/orderrun-db/backup.env(공통)와 backup-<env>.env(대상 DB)로 받는다.
# DB 자격증명은 컨테이너 안의 secret 파일만 쓰고, 오래된 S3 객체는 버킷 수명주기 규칙이 지운다.
set -euo pipefail
umask 077

env_name="${1:?usage: mysql-backup.sh <env>}"
container="${MYSQL_CONTAINER:-orderrun-mysql}"
database="${BACKUP_DATABASE:?BACKUP_DATABASE is required}"
s3_uri="${BACKUP_S3_URI:?BACKUP_S3_URI is required}"
backup_dir="${BACKUP_DIR:-/home/ubuntu/orderrun-db/backups}/${env_name}"
local_retention_days="${LOCAL_RETENTION_DAYS:-3}"
disk_alert_percent="${DISK_ALERT_PERCENT:-85}"

ts="$(date -u +%Y%m%dT%H%M%SZ)"
# 파일명과 S3 키에는 DB 이름 대신 환경 이름을 쓴다.
out="${backup_dir}/${env_name}-${ts}.sql.gz"
partial="${out}.partial"
mkdir -p "$backup_dir"
trap 'rm -f "$partial"' EXIT

# pipefail이라 mysqldump가 실패하면 파이프 전체가 실패한다.
docker exec "$container" mysqldump \
  --defaults-extra-file=/run/secrets/mysql_backup_cnf \
  --single-transaction --quick \
  --routines --triggers --events \
  --hex-blob --no-tablespaces --set-gtid-purged=OFF \
  --default-character-set=utf8mb4 \
  "$database" | gzip -c > "$partial"

# 잘린 덤프를 정상 백업으로 올리지 않는다. mysqldump는 끝까지 썼을 때만 마지막 줄을 남긴다.
gzip -t "$partial"
if ! zcat "$partial" | tail -n 1 | grep -q '^-- Dump completed'; then
  echo "덤프가 끝까지 쓰이지 않았다: ${env_name}" >&2
  exit 1
fi
mv "$partial" "$out"

aws s3 cp "$out" "${s3_uri%/}/${env_name}/$(basename "$out")" --only-show-errors
echo "backup ok: ${env_name} $(du -h "$out" | cut -f1)"

find "$backup_dir" -name '*.sql.gz' -mtime "+${local_retention_days}" -delete

# 디스크가 차면 MySQL이 멈춘다. 백업은 끝났어도 실패로 끝내 OnFailure 알림을 태운다.
usage="$(df --output=pcent / | tail -1 | tr -dc '0-9')"
if (( usage >= disk_alert_percent )); then
  echo "디스크 사용률 ${usage}% (기준 ${disk_alert_percent}%)" >&2
  exit 1
fi
