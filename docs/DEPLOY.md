# Deployment runbook

How to run ERPNext v16 + dz_cod for several clients on one Ubuntu server,
one site (one database) per client.

Status of this guide: the bench, ERPNext, dz_cod, the demo and the tests were
installed and run for real on Ubuntu 24.04 (Python 3.14, Node 24, MariaDB
10.11). Backup and restore were also run for real (step 10). The parts that
need a public server — nginx/supervisor production mode, DNS, Let's Encrypt,
firewall, rclone to a real remote — are **standard Frappe procedure but were
not executed** while writing this (no public server available); they are
marked *(not run here)*. Do your first run on a cheap test VPS.

Conventions: `$` lines run as the `frappe` user, `#` comments explain.
Replace `erp.client1.com` with the real domain and `SERVER_IP` with the
server's IP.

---

## 0. What you need

- A VPS with **Ubuntu 24.04 LTS**, 64-bit. Size: 2 vCPU / 4 GB RAM / 60 GB SSD
  is comfortable for 5–8 small shops; 8 GB RAM for 10–20.
- A domain per client (or sub-domains of your own domain, e.g.
  `client1.yourdomain.dz`), with DNS you can edit.
- An off-site storage for backups that rclone supports (Backblaze B2,
  Hetzner Storage Box, Google Drive, any S3, another server over SFTP...).
- On your Fedora laptop: an SSH key (`ssh-keygen -t ed25519` if you have none).

## 1. First login, admin user, SSH keys *(not run here)*

```bash
ssh root@SERVER_IP                        # first login, with the password from the VPS provider
adduser frappe                            # the user that will own and run ERPNext (choose a strong password)
usermod -aG sudo frappe                   # allow it to use sudo
exit
```

From your laptop:

```bash
ssh-copy-id frappe@SERVER_IP              # copy your public key to the server
ssh frappe@SERVER_IP                      # must log in WITHOUT asking the password
```

Now forbid passwords and root login over SSH (only do this once the key login works):

```bash
sudo tee /etc/ssh/sshd_config.d/99-hardening.conf > /dev/null <<'EOF'
PasswordAuthentication no
PermitRootLogin no
EOF
sudo systemctl restart ssh                # apply; keep your current session open and test a new one first
```

## 2. System basics *(not run here)*

```bash
sudo apt update && sudo apt upgrade -y               # latest security fixes
sudo timedatectl set-timezone Africa/Algiers         # server clock in Algerian time (logs, cron)
sudo apt install -y unattended-upgrades              # install security updates automatically
sudo ufw allow OpenSSH                               # firewall: keep SSH open...
sudo ufw allow 80,443/tcp                            # ...and the web (HTTP/HTTPS)
sudo ufw enable                                      # switch the firewall on (everything else is closed)
```

If the server has 4 GB RAM or less, add swap so a big build does not crash:

```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile   # reserve a 4 GB file, readable by root only
sudo mkswap /swapfile && sudo swapon /swapfile                # turn it into swap and use it now
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab    # keep it after reboot
```

## 3. Packages

```bash
sudo apt install -y git curl build-essential pkg-config \
  libmariadb-dev mariadb-server mariadb-client redis-server \
  nginx supervisor fail2ban cron xvfb libfontconfig1 wkhtmltopdf \
  certbot python3-certbot-nginx rclone
```

One line each: `git` fetches the apps; `build-essential`, `pkg-config` and
`libmariadb-dev` compile the MariaDB driver; `mariadb-*` is the database;
`redis-server` is the cache and job queue; `nginx` is the web server;
`supervisor` keeps the processes running; `fail2ban` blocks brute-force
attempts; `xvfb libfontconfig1 wkhtmltopdf` make PDFs; `certbot` makes free
SSL certificates; `rclone` copies backups off the server.

> PDFs: if headers/footers look wrong with Ubuntu's wkhtmltopdf, set
> **Print Settings → PDF Generator → chrome** in ERPNext (v16 downloads its own
> Chromium).

Node.js 24 (Frappe v16 needs ≥ 24; Ubuntu's own is too old):

```bash
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -   # add the NodeSource repository for Node 24
sudo apt install -y nodejs                                           # install Node 24
sudo npm install -g yarn                                             # yarn builds the JavaScript assets
```

Python 3.14 (Frappe v16 needs exactly 3.14) and bench, with `uv`, as `frappe`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # install uv (Python manager) into ~/.local/bin
source ~/.bashrc                                     # reload PATH so "uv" is found
uv python install 3.14                               # download Python 3.14 just for us
uv tool install frappe-bench                         # install the "bench" command
bench --version                                      # check: prints 5.x
```

## 4. MariaDB

```bash
sudo tee /etc/mysql/mariadb.conf.d/99-frappe.cnf > /dev/null <<'EOF'
[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

[mysql]
default-character-set = utf8mb4
EOF
sudo systemctl restart mariadb                       # Frappe needs utf8mb4 (accents, Arabic, emoji)
```

Give the MariaDB `root` user a password (bench needs it to create one database
per site) while keeping the passwordless `sudo mariadb` access:

```bash
DBPASS=$(openssl rand -base64 24)                    # generate a strong password
echo "MariaDB root password: $DBPASS"                # WRITE IT in your password manager now
sudo mariadb -e "ALTER USER root@localhost IDENTIFIED VIA unix_socket OR mysql_native_password USING PASSWORD('$DBPASS'); FLUSH PRIVILEGES;"
```

## 5. The bench (one per server)

```bash
cd ~
bench init frappe-bench --frappe-branch version-16 --python "$(uv python find 3.14)"
                                                     # creates ~/frappe-bench with Frappe v16 (5-10 min)
cd ~/frappe-bench
bench get-app --branch version-16 https://github.com/frappe/erpnext
                                                     # downloads ERPNext v16 (use the full URL; the short name can fail)
bench get-app https://github.com/adem-max/dz-cod     # downloads our app
```

If the dz-cod repository is **private**, create a read-only *deploy key* on
GitHub (repo → Settings → Deploy keys) with a key generated on the server
(`ssh-keygen -t ed25519 -f ~/.ssh/dzcod`), then use
`bench get-app git@github.com:adem-max/dz-cod.git`.

## 6. Production mode (nginx + supervisor) *(not run here)*

```bash
bench config dns_multitenant on                      # one bench, many sites, chosen by domain name
sudo $(which bench) setup production frappe          # writes nginx + supervisor configs and starts everything
                                                     # (answer "y" to the questions)
sudo supervisorctl status                            # all lines must say RUNNING
```

`setup production` installs nginx/supervisor/fail2ban with Ansible only if
they are missing; we installed them with apt in step 3, which is quicker.

## 7. A site for a client

DNS first: at the domain registrar, create an **A record**
`erp.client1.com → SERVER_IP` and wait until `ping erp.client1.com` shows the
server IP.

```bash
cd ~/frappe-bench
ADMINPASS=$(openssl rand -base64 18); echo "Admin password: $ADMINPASS"   # store it in your password manager
bench new-site erp.client1.com --mariadb-root-password "$DBPASS" \
      --admin-password "$ADMINPASS" --install-app erpnext                  # new database + ERPNext (2-3 min)
bench --site erp.client1.com install-app dz_cod                            # COD app: fields, workflow, 69 wilayas
bench --site erp.client1.com enable-scheduler                              # turn on background jobs for this site
bench setup nginx && sudo systemctl reload nginx                           # publish the new domain *(not run here)*
```

SSL (HTTPS) with Let's Encrypt *(not run here)*:

```bash
sudo $(which bench) setup lets-encrypt erp.client1.com   # stops nginx ~30 s, gets the certificate, adds auto-renewal
```

Then open `https://erp.client1.com`, log in as `Administrator`, complete the
setup wizard (language **Français**, country **Algeria**, currency **DZD**,
time zone **Africa/Algiers**, the client's company name) and continue with
the checklist in section 13.

## 8. Moving a site to another domain

```bash
bench setup add-domain shop.client1.dz --site erp.client1.com    # extra domain for the same site
bench setup nginx && sudo systemctl reload nginx
```

## 9. Automated daily backups, copied off the server *(script tested with a local rclone remote; a cloud remote was not run here)*

1. Configure the remote storage once (interactive; name it **offsite**):

   ```bash
   rclone config            # n (new) -> name: offsite -> choose the provider -> follow the questions
   rclone lsd offsite:      # check: lists the buckets/folders of the remote
   ```

   For extra safety choose an rclone **crypt** remote on top: backups are then
   encrypted before they leave the server.

2. Install the script shipped with dz_cod and schedule it at 02:30 every night:

   ```bash
   cp ~/frappe-bench/apps/dz_cod/scripts/backup_offsite.sh ~/backup_offsite.sh
   chmod +x ~/backup_offsite.sh
   ~/backup_offsite.sh                                  # run once by hand and read the output
   (crontab -l 2>/dev/null; echo "30 2 * * * /home/frappe/backup_offsite.sh >> /home/frappe/backup_offsite.log 2>&1") | crontab -
   crontab -l                                           # check the line is there
   ```

   For each site it makes 4 files: `…-database.sql.gz`, `…-files.tgz`,
   `…-private-files.tgz` and `…-site_config_backup.json`.

3. **The `…-site_config_backup.json` file holds the site's `encryption_key`**
   (ERPNext creates it the first time a password is stored). Without it,
   passwords stored in ERPNext (email accounts, couriers' API tokens) cannot be
   decrypted after a restore. Keep it, and keep the backups private.

## 10. Restore (tested)

This exact procedure was run while writing this guide: backup of the demo
site (with a courier API token stored encrypted), restore into a new empty
site, then check. Result: the same 200 orders, and the API token could still
be decrypted.

```bash
cd ~/frappe-bench
ls -t sites/erp.client1.com/private/backups/ | head -4      # the latest 4 files of that site
# (after losing the server: rclone copy offsite:erp-backups/<server>/erp.client1.com/ /tmp/restore/ --max-age 48h)
B=sites/erp.client1.com/private/backups/20261009_023000-erp_client1_com    # the common beginning of the 4 file names

# Restore INTO A TEST SITE FIRST, never directly over the live site
bench new-site restore-test.localhost --mariadb-root-password "$DBPASS" --admin-password test1234
                                                            # an empty site to receive the backup
bench --site restore-test.localhost restore "$B-database.sql.gz" \
      --with-public-files "$B-files.tgz" --with-private-files "$B-private-files.tgz" \
      --mariadb-root-password "$DBPASS"                     # replaces its database and files with the backup

# Give the restored site the original encryption key, so stored passwords
# (courier API tokens, email accounts) can still be read
KEY=$(python3 -c "import json;print(json.load(open('$B-site_config_backup.json')).get('encryption_key',''))")
[ -n "$KEY" ] && bench --site restore-test.localhost set-config encryption_key "$KEY"

bench --site restore-test.localhost migrate                 # brings the restored data to the installed app versions
```

(`bench restore` also has an `--encryption-key` option: that one is only for
backups made *encrypted* with `backup_encryption_key`, which this guide does
not use. Do not confuse it with the site's `encryption_key`.)

Check in the test site: number of orders, last order date, a PDF with an
image, a courier's API token. When satisfied, either drop the test site
(`bench drop-site restore-test.localhost --force`) or, for a real disaster,
run the same `restore` (and `set-config encryption_key`) on the live site name.

**Do a test restore every month** — a backup you never restored is only a hope.

## 11. Updates

Minor updates of ERPNext/Frappe v16 and of dz_cod, once a month, outside
working hours:

```bash
cd ~/frappe-bench
~/backup_offsite.sh                          # fresh backup of every site, copied off the server
bench update                                 # pulls frappe, erpnext, dz_cod; installs requirements; migrates every site;
                                             # rebuilds assets; restarts the processes
bench --site all list-apps                   # check the versions
```

Only dz_cod changed (a fix you pushed):

```bash
cd ~/frappe-bench/apps/dz_cod && git pull && cd ~/frappe-bench   # get the new code
bench --site all migrate                                         # update doctypes, fields, workflow on every site
bench build --app dz_cod                                         # rebuild JavaScript if it changed
sudo supervisorctl restart all                                   # restart web and workers
```

If something breaks after an update: `bench --site <site> migrate` again and
read the error; worst case, restore last night's backup (section 10).

Major upgrades (v16 → v17) are a project: test on a copy of each site first.

## 12. Security checklist

- [ ] SSH: key only, no password, no root login (section 1).
- [ ] Firewall `ufw` on: only 22, 80, 443 open (`sudo ufw status`).
- [ ] fail2ban running (`sudo systemctl status fail2ban`).
- [ ] Automatic security updates on (`unattended-upgrades`).
- [ ] One **unique strong Administrator password per site**, stored in a password manager; do not use Administrator for daily work.
- [ ] Each client user has their own login with only the roles they need (Sales User / Stock User / Accounts User); only you are System Manager.
- [ ] Two-factor authentication for System Managers (System Settings → Login → Enable Two Factor Auth).
- [ ] `developer_mode` and `allow_tests` are **off** in production (`bench --site all show-config`; dev and test settings belong to your laptop).
- [ ] MariaDB and Redis listen on localhost only (default on Ubuntu; check `sudo ss -tlnp`).
- [ ] HTTPS on every site; renewal cron in place (`sudo crontab -l`).
- [ ] Backups run every night, are copied off the server, and a restore was tested this month.
- [ ] **No client data in git**: never commit `sites/`, `site_config.json`, backups, exports or screenshots with client data. The repo's `.gitignore` blocks the usual files; check `git status` before each commit.
- [ ] Courier API tokens are stored in the Supplier's *API Token* field (encrypted), never in code.
- [ ] Webhook secrets set when the n8n webhooks are enabled.

## 13. New client in under 2 hours

**Shortcut:** steps 0:25 to 0:45 (wizard, warehouses, delivery-fee account, COD Settings, courier, no VAT) are one command:

```bash
bench --site erp.client1.com execute dz_cod.setup.new_client.prepare \
  --kwargs "{'company': 'Client One', 'abbr': 'C1', 'courier': 'Yalidine'}"
```

| Time | Step |
|------|------|
| 0:00 | Client sends: company name, logo, domain, list of products with prices and stock, courier(s) and their rate card, users (names, emails, roles). |
| 0:10 | DNS A record for the client domain → server (section 7). |
| 0:15 | `bench new-site … --install-app erpnext`, `install-app dz_cod`, `enable-scheduler`, `setup nginx`, `setup lets-encrypt` (section 7). |
| 0:25 | Setup wizard: Français / Algeria / DZD / Africa/Algiers, company name and abbreviation. |
| 0:28 | **No VAT**: the wizard makes *Algeria TVA 19%* the default sales tax template, and the order form then adds 19 % to every order typed by hand. Search *Sales Taxes and Charges Template* → open *Algeria TVA 19% - XX* → untick **Default** → save. (Skip only if the client is VAT-registered.) |
| 0:30 | Warehouses: create **Stock principal** and **Retours** (Stock → Warehouse). |
| 0:35 | Account for delivery fees: Accounting → Chart of Accounts → under income accounts, add **Frais de livraison facturés**. |
| 0:40 | **Paramètres COD**: company, main warehouse, returns warehouse, delivery-fee account, max calls (3), stock blocking (on/off), tolerance. |
| 0:45 | Couriers: Supplier → new, tick **Is Transporter**, *Connecteur* = Manuel. Set it as default courier in Paramètres COD. |
| 0:50 | **Wilayas et tarifs**: list view → edit *Tarif domicile*, *Tarif stop desk* and the courier costs from the client's rate card; untick *Livrable* where the courier does not go. (Report view allows editing many rows quickly.) |
| 1:05 | Products: Item Attributes Taille/Couleur exist? create them; import items with Data Import (Item, then Item Price), or create templates + variants. |
| 1:25 | Opening stock: Stock Reconciliation (or Stock Entry "Material Receipt") into Stock principal. |
| 1:35 | Users: one per person, roles Sales User / Stock User / Accounts User; language Français. |
| 1:45 | Webhooks: if the client uses n8n, paste the URLs and enable (docs/WEBHOOKS.md). |
| 1:50 | Smoke test with the client: one order Nouvelle → Confirmer → Préparer → Expédier → Marquer livrée, then cancel/delete it. Check the delivery note and stock. |
| 1:55 | Add the site to the backup check (it is automatic: the script backs up every site) and note the admin password in your password manager. |

## 14. Useful commands when something goes wrong

```bash
sudo supervisorctl status                        # is everything running?
sudo supervisorctl restart all                   # restart web + workers + scheduler
tail -f ~/frappe-bench/logs/web.error.log        # Python errors of the web server
tail -f ~/frappe-bench/logs/worker.error.log     # errors in background jobs (webhooks, emails)
bench --site erp.client1.com console             # Python console on a site (careful: real data)
bench --site erp.client1.com mariadb             # SQL console on a site's database
bench doctor                                     # scheduler and workers health
```

In the browser: **Error Log** (search bar) lists server errors, **Webhook
Request Log** lists every webhook call and its answer, **Scheduled Job Log**
shows the hourly courier sync.
