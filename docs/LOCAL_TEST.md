# Run it on your Fedora laptop

Goal: a local copy of the whole stack (Frappe v16 + ERPNext v16 + dz_cod +
demo shop) to practise, break things and test changes before they go to a
client server.

**Approach: an Ubuntu 24.04 container with distrobox.** Everything in this
repo was built and tested on Ubuntu 24.04. Inside a distrobox you run the
*same* commands, so you avoid Fedora-specific package differences. Your home
folder is shared with the container, so you edit code with your usual editor
on Fedora.

> Honesty note: the commands *inside* the Ubuntu container are the ones that
> were run while building this kit. The two Fedora commands at the start
> (installing distrobox, creating the box) were not run on a Fedora machine.

## 1. Create the Ubuntu box (Fedora side)

```bash
sudo dnf install -y distrobox podman          # distrobox runs other Linux distributions in containers
distrobox create --name erp --image ubuntu:24.04
distrobox enter erp                           # you are now in Ubuntu; the prompt changes
```

Every command below runs **inside** the box (`distrobox enter erp` first).

## 2. Packages

```bash
sudo apt update
sudo apt install -y git curl build-essential pkg-config libmariadb-dev \
  mariadb-server mariadb-client redis-server xvfb libfontconfig1 wkhtmltopdf cron
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -   # Node 24 repository
sudo apt install -y nodejs && sudo npm install -g yarn
curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.bashrc  # uv
uv python install 3.14                                               # Python 3.14
uv tool install frappe-bench                                         # bench
```

## 3. MariaDB (no systemd inside a box: start it by hand)

```bash
sudo tee /etc/mysql/mariadb.conf.d/99-frappe.cnf > /dev/null <<'EOF'
[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
[mysql]
default-character-set = utf8mb4
EOF
sudo mkdir -p /run/mysqld && sudo chown mysql:mysql /run/mysqld
sudo mysqld_safe > /dev/null 2>&1 &          # start MariaDB in the background
sleep 5 && sudo mariadb -e "select version()" # check it answers
sudo mariadb -e "ALTER USER root@localhost IDENTIFIED VIA unix_socket OR mysql_native_password USING PASSWORD('root'); FLUSH PRIVILEGES;"
                                              # local password "root" (fine on a laptop, NEVER on a server)
```

After a reboot of the laptop, re-enter the box and run the `mkdir`, `chown`
and `mysqld_safe` lines again.

## 4. Bench, apps, sites

```bash
cd ~
bench init frappe-bench --frappe-branch version-16 --python "$(uv python find 3.14)"
cd ~/frappe-bench
bench get-app --branch version-16 https://github.com/frappe/erpnext
bench get-app https://github.com/adem-max/dz-cod

# Demo site (see docs/DEMO.md)
bench new-site demo.localhost --mariadb-root-password root --admin-password admin --install-app erpnext
bench --site demo.localhost install-app dz_cod
bench --site demo.localhost set-config developer_mode 1     # lets you edit doctypes from the browser (laptop only)
bench --site demo.localhost execute dz_cod.demo.loader.load

# Test site (kept separate from the demo)
bench new-site test.localhost --mariadb-root-password root --admin-password admin --install-app erpnext
bench --site test.localhost install-app dz_cod
bench --site test.localhost set-config allow_tests 1
```

## 5. Start and open

```bash
cd ~/frappe-bench
bench use demo.localhost                      # choose WHICH site the development server shows
bench start                                   # web server, workers, scheduler, redis; Ctrl+C to stop
```

Open http://demo.localhost:8000 in Firefox on Fedora. Log in as
`Administrator` / `admin`.

**Important: on your laptop, `bench start` shows only one site, the one
chosen with `bench use`, whatever name you type in the address bar.**
(In production, nginx picks the site from the domain name; the development
server does not.) To show another site, for example your friend's:

```bash
# Ctrl+C in the bench start terminal, then:
bench use friend.localhost
bench start
```

Check which site is shown: `grep default_site sites/common_site_config.json`.

## 6. Run the tests

In a second terminal (`distrobox enter erp`, `cd ~/frappe-bench`):

```bash
bench --site test.localhost run-tests --app dz_cod                         # all 85 tests (~40 s)
bench --site test.localhost run-tests --module dz_cod.tests.test_rules     # only the fast rule tests
bench --site test.localhost run-tests --module dz_cod.tests.test_order_flow --test test_confirm_reserves_stock
                                                                           # one single test
```

Expected end of output: `OK` after "Ran 25 tests" and after "Ran 60 tests".

## 7. Change the code and see the result

The app's code is in `~/frappe-bench/apps/dz_cod` (a normal git clone of
this repository). Open that folder in VS Code on Fedora.

| You changed | Then run |
|-------------|----------|
| a Python file | nothing (`bench start` reloads it); for `hooks.py` restart `bench start` |
| a JavaScript file | `bench build --app dz_cod`, then Ctrl+Shift+R in the browser |
| a doctype JSON, `setup/custom_fields.py`, `setup/workflow.py` | `bench --site demo.localhost migrate` |
| `translations/fr.csv` | `bench --site demo.localhost clear-cache` |

Commit and push from `~/frappe-bench/apps/dz_cod` like any git repository.

## 8. If something fails

- `Access denied for user 'root'` → MariaDB password not set (step 3).
- `Can't connect to local server through socket` → MariaDB not started (step 3, `mysqld_safe`).
- `bench: command not found` → `source ~/.bashrc` or open a new terminal in the box.
- `erpnext not found under frappe or erpnext GitHub accounts` → use the full URL `https://github.com/frappe/erpnext`.
- `Too many queued background jobs` → `bench start` was not running during a big load; run `bench worker --queue default,short,long --burst` once to empty the queue.
- The page is blank after a JS change → `bench build --app dz_cod` and hard-refresh.
- You see the wrong data (other company, other orders) → the development server shows the `bench use` site, not the one in the address bar (section 5).
