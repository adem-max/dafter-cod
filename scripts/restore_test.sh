#!/bin/bash
# Monthly restore drill: restore the latest backup of a site into a throwaway
# site, compare it with the live site, then delete the throwaway site.
#
#   DBPASS='mariadb root password' ~/restore_test.sh erp.client1.com [backup folder]
#
# The backup folder defaults to the site's local backups. To test the OFF-SITE
# copy (the real disaster case), download it first and pass that folder:
#   rclone copy offsite:erp-backups/<server>/erp.client1.com/ /tmp/restore/ --max-age 48h
#   DBPASS=... ~/restore_test.sh erp.client1.com /tmp/restore
#
# Set KEEP=1 to keep the restored site (restore-test.localhost) for a look.
# Needs bench running (Frappe v16 needs its Redis to create a site).

set -euo pipefail
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

SITE="${1:?usage: restore_test.sh <site> [backup folder]}"
BENCH_DIR="${BENCH_DIR:-$HOME/frappe-bench}"
: "${DBPASS:?set DBPASS to the MariaDB root password}"
TEST_SITE="restore-test.localhost"

cd "$BENCH_DIR"
BACKUP_DIR="$(realpath "${2:-sites/$SITE/private/backups}")"

# The 4 files of the latest backup share one prefix: <date>_<time>-<site>
latest_db=$(ls -t "$BACKUP_DIR"/*-database.sql.gz 2>/dev/null | head -1)
[ -n "$latest_db" ] || { echo "No *-database.sql.gz in $BACKUP_DIR"; exit 1; }
B="${latest_db%-database.sql.gz}"
for part in files.tgz private-files.tgz site_config_backup.json; do
	[ -f "$B-$part" ] || { echo "Missing $B-$part: the backup is incomplete"; exit 1; }
done
echo "=== Restoring $(basename "$B") into $TEST_SITE"

if [ -d "sites/$TEST_SITE" ]; then
	bench drop-site "$TEST_SITE" --force --no-backup --mariadb-root-password "$DBPASS"
fi
bench new-site "$TEST_SITE" --mariadb-root-password "$DBPASS" \
	--admin-password "$(head -c 18 /dev/urandom | base64)" > /dev/null
bench --site "$TEST_SITE" restore "$B-database.sql.gz" \
	--with-public-files "$B-files.tgz" --with-private-files "$B-private-files.tgz" \
	--mariadb-root-password "$DBPASS"

# The original encryption key, so stored passwords (couriers' API tokens,
# e-mail accounts) can still be read
KEY=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('encryption_key',''))" \
	"$B-site_config_backup.json")
[ -n "$KEY" ] && bench --site "$TEST_SITE" set-config encryption_key "$KEY"
bench --site "$TEST_SITE" migrate > /dev/null

echo "=== Comparing live site and restored copy"
check() { bench --site "$1" execute dz_cod.setup.restore_check.summary 2>/dev/null | tail -1; }
LIVE=$(check "$SITE")
RESTORED=$(check "$TEST_SITE")

status=0
python3 - "$LIVE" "$RESTORED" <<'EOF' || status=$?
import json, sys
live, restored = json.loads(sys.argv[1]), json.loads(sys.argv[2])
problems = []
print(f"{'':22}{'live':>28}{'restored':>28}")
for key in live:
	print(f"{key:22}{str(live[key]):>28}{str(restored.get(key)):>28}")
	if isinstance(live[key], int) and key != "passwords_unreadable":
		# The live site keeps working after the backup: it may have more, never less
		if restored.get(key, 0) > live[key] or (live[key] and not restored.get(key)):
			problems.append(key)
if restored["passwords_unreadable"]:
	problems.append("passwords cannot be decrypted (wrong encryption_key)")
if problems:
	print("RESTORE TEST FAILED:", ", ".join(problems))
	sys.exit(1)
print("RESTORE TEST OK")
EOF

if [ "${KEEP:-0}" = "1" ]; then
	echo "Kept $TEST_SITE (drop it with: bench drop-site $TEST_SITE --force)"
else
	bench drop-site "$TEST_SITE" --force --no-backup --mariadb-root-password "$DBPASS" > /dev/null
	echo "Dropped $TEST_SITE"
fi
exit $status
