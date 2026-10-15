#!/bin/bash
# Daily backup of every site on this server, copied OFF the server.
#
# What it does:
#   1. backs up each site (database + public files + private files + site config)
#   2. copies today's backup files to a remote storage with rclone
#   3. deletes local backups older than 7 days (the remote keeps its own history)
#   4. if HEALTHCHECK_URL is set, pings it (with /fail on any error), so a
#      backup that silently stopped working sends you an e-mail
#
# Install (see docs/DEPLOY.md, step 9):
#   cp ~/frappe-bench/apps/dz_cod/scripts/backup_offsite.sh ~/backup_offsite.sh
#   chmod +x ~/backup_offsite.sh
#   crontab -e   ->   30 2 * * * /home/frappe/backup_offsite.sh >> /home/frappe/backup_offsite.log 2>&1
#
# Needs: rclone configured with a remote called "offsite" (rclone config).
# Settings can be changed without editing the script, e.g. in the crontab line:
#   BENCH_DIR=... REMOTE=... KEEP_LOCAL_DAYS=... HEALTHCHECK_URL=... /home/frappe/backup_offsite.sh

set -uo pipefail   # unset variables are errors; a failed site does NOT stop the others

# cron starts with a minimal PATH: bench and rclone live in ~/.local/bin
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

BENCH_DIR="${BENCH_DIR:-$HOME/frappe-bench}"
REMOTE="${REMOTE:-offsite:erp-backups/$(hostname)}"   # remote name and folder in rclone
KEEP_LOCAL_DAYS="${KEEP_LOCAL_DAYS:-7}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-}"                  # e.g. https://hc-ping.com/<uuid> (optional)

failed=()

cd "$BENCH_DIR" || { echo "No bench at $BENCH_DIR"; exit 1; }
echo "=== Backup started $(date) ==="

for site_dir in sites/*/; do
	site=$(basename "$site_dir")
	# A real site has a site_config.json; skip "assets" and other folders
	[ -f "sites/$site/site_config.json" ] || continue
	# Throwaway sites made by restore_test.sh are not worth keeping
	[[ "$site" == restore-test.* ]] && continue

	echo "--- $site"
	if ! bench --site "$site" backup --with-files --compress; then
		echo "!!! backup FAILED for $site"
		failed+=("$site (backup)")
		continue
	fi

	# Copy only the files of the last 24 hours to the remote folder of this site
	if ! rclone copy "sites/$site/private/backups" "$REMOTE/$site" --max-age 24h; then
		echo "!!! off-site copy FAILED for $site (the local backup is still there)"
		failed+=("$site (copy)")
		continue
	fi

	# Free disk space: local backups older than KEEP_LOCAL_DAYS days
	# (only after a successful copy, so a broken remote never costs us backups)
	find "sites/$site/private/backups" -type f -mtime +"$KEEP_LOCAL_DAYS" -delete
done

if [ ${#failed[@]} -gt 0 ]; then
	echo "=== Backup finished with ERRORS $(date): ${failed[*]} ==="
	[ -n "$HEALTHCHECK_URL" ] && curl -fsS -m 10 --retry 3 "$HEALTHCHECK_URL/fail" > /dev/null
	exit 1
fi

echo "=== Backup finished $(date) ==="
[ -n "$HEALTHCHECK_URL" ] && curl -fsS -m 10 --retry 3 "$HEALTHCHECK_URL" > /dev/null
exit 0
