#!/usr/bin/env bash
#
# setup-nginx.sh — secure, fast reverse proxy for Paroll.
#
# Fronts gunicorn (127.0.0.1:8000, HTTP app) and daphne (127.0.0.1:8001,
# WebSockets) with a hardened, performance-tuned nginx. Stock-nginx
# compatible (no third-party modules required).
#
# What you get:
#   * HTTP/2 + TLS 1.2/1.3 only, strong ciphers, OCSP stapling, HSTS
#   * Security headers (nosniff, CSP, COOP, Permissions-Policy, HSTS)
#   * Short client timeouts + reset_timedout_connection so half-open /
#     scanner connections can never park sync workers (the WORKER TIMEOUT
#     killer: gunicorn --timeout 60 with parked recv()).
#   * Proxy buffering ON for the app (frees gunicorn workers fast),
#     OFF for /ws/ (long-lived frames).
#   * Upstream keepalive pools (no TCP+reconnect per request).
#   * gzip + gzip_static (WhiteNoise already ships *.gz), static/media
#     served directly by nginx with sane cache lifetimes.
#   * Rate limits: strict for /admin/, /oauth/, login endpoints;
#     generous for general traffic. DRF throttles still apply in-app.
#   * Let's Encrypt via webroot (no nginx plugin needed), ACME path kept
#     working on :80.
#
# Usage:
#   sudo ./scripts/setup-nginx.sh --email ops@example.com [--domain zayadev.xyz]
#   sudo ./scripts/setup-nginx.sh --email ops@example.com --staging   # test first
#   ./scripts/setup-nginx.sh --dry-run                                # render + nginx -t only
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN=""
EXTRA_DOMAINS=""
EMAIL=""
STAGING=0
SKIP_CERT=0
DRY_RUN=0
CLIENT_MAX_BODY="20m"
ROOT="" # filesystem prefix (used by --dry-run)

usage() {
  sed -n '2,30p' "$0"
  echo "Flags: --domain D --extra-domains 'a b' --email E --staging --skip-cert"
  echo "       --client-max-body 20m --dry-run --root / (prefix for /etc/nginx)"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="${2:?}"; shift 2 ;;
    --extra-domains) EXTRA_DOMAINS="${2:?}"; shift 2 ;;
    --email) EMAIL="${2:?}"; shift 2 ;;
    --staging) STAGING=1; shift ;;
    --skip-cert) SKIP_CERT=1; shift ;;
    --client-max-body) CLIENT_MAX_BODY="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --root) ROOT="${2:?}"; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) echo "Unknown flag: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# --- defaults from .env -------------------------------------------------------
if [[ -z "$DOMAIN" && -f "$APP_DIR/.env" ]]; then
  # shellcheck disable=SC1090
  DOMAIN="$(grep -E '^ALLOWED_HOSTS=' "$APP_DIR/.env" | cut -d= -f2- | tr ',' '\n' \
    | grep -vE '^(localhost|127\.0\.0\.1)$' | head -n 1 | xargs || true)"
fi
DOMAIN="${DOMAIN:-zayadev.xyz}"
if [[ -z "$EXTRA_DOMAINS" ]]; then
  case "$DOMAIN" in
    www.*) EXTRA_DOMAINS="${DOMAIN#www.}" ;;
    *) EXTRA_DOMAINS="www.${DOMAIN}" ;;
  esac
fi
ALL_DOMAINS="$DOMAIN $EXTRA_DOMAINS"

if [[ $SKIP_CERT -eq 0 && $DRY_RUN -eq 0 && -z "$EMAIL" ]]; then
  echo "ERROR: --email is required (Let's Encrypt account/renewal notices)." >&2
  exit 2
fi

ETC_NGINX="$ROOT/etc/nginx"
SITES_AVAILABLE="$ETC_NGINX/sites-available"
SITES_ENABLED="$ETC_NGINX/sites-enabled"
CONF_D="$ETC_NGINX/conf.d"
SNIPPETS="$ETC_NGINX/snippets"
SITE_NAME="paroll"

log() { printf '[setup-nginx] %s\n' "$*"; }
warn() { printf '[setup-nginx] WARN: %s\n' "$*" >&2; }

render() { # render <template-var-content> : replaces __TOKENS__
  sed -e "s#__DOMAINS__#${ALL_DOMAINS}#g" \
      -e "s#__DOMAIN__#${DOMAIN}#g" \
      -e "s#__APP_DIR__#${APP_DIR}#g" \
      -e "s#__CLIENT_MAX_BODY__#${CLIENT_MAX_BODY}#g" \
      -e "s#__CERT_DIR__#${CERT_DIR}#g"
}

# --- file contents ------------------------------------------------------------
write_http_conf() {
  cat >"$CONF_D/paroll-http.conf" <<'EOF'
# Paroll: http-context pieces (managed by scripts/setup-nginx.sh).
limit_req_zone $binary_remote_addr zone=paroll_auth:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=paroll_general:10m rate=25r/s;
limit_conn_zone $binary_remote_addr zone=paroll_conn:10m;

map $http_upgrade $connection_upgrade {
  default upgrade;
  ''      close;
}

upstream paroll_gunicorn {
  server 127.0.0.1:8000 max_fails=3 fail_timeout=30s;
  keepalive 32;
  keepalive_requests 1000;
  keepalive_timeout 30s;
}

upstream paroll_daphne {
  server 127.0.0.1:8001 max_fails=3 fail_timeout=30s;
  keepalive 16;
}
EOF
}

write_security_snippet() {
  cat >"$SNIPPETS/paroll-security-headers.conf" <<'EOF'
# Paroll security headers (managed by scripts/setup-nginx.sh).
# NOTE: X-Frame-Options and Referrer-Policy are intentionally NOT set here:
# Django already emits X-Frame-Options: DENY and Referrer-Policy: same-origin.
# (CSP frame-ancestors covers static files for modern browsers.)
add_header X-Content-Type-Options "nosniff" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: https:; connect-src 'self' https: wss:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'; upgrade-insecure-requests" always;
add_header Cross-Origin-Opener-Policy "same-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), interest-cohort=()" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
EOF
}

write_proxy_snippet() {
  cat >"$SNIPPETS/paroll-proxy.conf" <<'EOF'
# Paroll common proxy headers (managed by scripts/setup-nginx.sh).
proxy_http_version 1.1;
proxy_set_header Connection "";
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Port $server_port;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Request-ID $request_id;
EOF
}

write_site_http_bootstrap() {
  render >"$SITES_AVAILABLE/$SITE_NAME" <<'EOF'
# Paroll BOOTSTRAP (HTTP only, managed by scripts/setup-nginx.sh).
# The installer replaces this with the full HTTPS site once certificates exist.
server {
  listen 80;
  listen [::]:80;
  server_name __DOMAINS__;

  access_log /var/log/nginx/paroll-access.log combined buffer=512k flush=1m;
  error_log /var/log/nginx/paroll-error.log warn;

  location ^~ /.well-known/acme-challenge/ {
    root /var/www/html;
    default_type text/plain;
  }

  location / {
    include snippets/paroll-proxy.conf;
    proxy_connect_timeout 5s;
    proxy_send_timeout 15s;
    proxy_read_timeout 65s;
    proxy_buffering on;
    proxy_buffers 8 16k;
    proxy_buffer_size 16k;
    proxy_busy_buffers_size 32k;
    proxy_pass http://paroll_gunicorn;
  }
}
EOF
}

write_site_full() {
  render >"$SITES_AVAILABLE/$SITE_NAME" <<'EOF'
# Paroll production site (managed by scripts/setup-nginx.sh).
# Gunicorn :8000 = HTTP app. Daphne :8001 = WebSockets (/ws/*).

server {
  listen 80;
  listen [::]:80;
  server_name __DOMAINS__;

  access_log /var/log/nginx/paroll-access.log combined buffer=512k flush=1m;
  error_log /var/log/nginx/paroll-error.log warn;

  location ^~ /.well-known/acme-challenge/ {
    root /var/www/html;
    default_type text/plain;
  }

  location / {
    return 301 https://$host$request_uri;
  }
}

server {
  listen 443 ssl http2;
  listen [::]:443 ssl http2;
  server_name __DOMAINS__;

  server_tokens off;

  ssl_certificate __CERT_DIR__/fullchain.pem;
  ssl_certificate_key __CERT_DIR__/privkey.pem;
  ssl_trusted_certificate __CERT_DIR__/chain.pem;
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
  ssl_prefer_server_ciphers off;
  ssl_ecdh_curve X25519:prime256v1:secp384r1;
  ssl_session_cache shared:SSL:10m;
  ssl_session_timeout 10m;
  ssl_session_tickets off;
  ssl_stapling on;
  ssl_stapling_verify on;
  resolver 1.1.1.1 8.8.8.8 valid=300s;
  resolver_timeout 5s;

  include snippets/paroll-security-headers.conf;

  access_log /var/log/nginx/paroll-access.log combined buffer=512k flush=1m;
  error_log /var/log/nginx/paroll-error.log warn;

  # --- speed ---
  sendfile on;
  tcp_nopush on;
  tcp_nodelay on;
  keepalive_timeout 20s;
  keepalive_requests 1000;
  open_file_cache max=10000 inactive=30s;
  open_file_cache_valid 30s;
  open_file_cache_min_uses 2;
  open_file_cache_errors on;

  gzip on;
  gzip_vary on;
  gzip_proxied any;
  gzip_http_version 1.1;
  gzip_comp_level 5;
  gzip_min_length 1024;
  gzip_types text/plain text/css application/json application/javascript
    application/xml application/xml+rss text/xml text/javascript
    image/svg+xml application/vnd.ms-fontobject font/ttf font/opentype;

  # --- slow-client / scanner protection ---
  # Never let a half-open connection park an upstream sync worker.
  client_max_body_size __CLIENT_MAX_BODY__;
  client_body_buffer_size 32k;
  client_header_timeout 10s;
  client_body_timeout 12s;
  send_timeout 15s;
  reset_timedout_connection on;
  limit_conn paroll_conn 20;

  # --- static / media straight from disk (no Django, no WhiteNoise hop) ---
  location ^~ /static/ {
    alias __APP_DIR__/staticfiles/;
    include snippets/paroll-security-headers.conf;
    gzip_static on;
    gunzip on;
    expires 1d;
    access_log off;
  }

  location ^~ /media/ {
    alias __APP_DIR__/media/;
    include snippets/paroll-security-headers.conf;
    expires 7d;
    access_log off;
  }

  # --- brute-force-sensitive endpoints ---
  location ^~ /admin/ {
    limit_req zone=paroll_auth burst=8 nodelay;
    limit_req_status 429;
    include snippets/paroll-proxy.conf;
    proxy_connect_timeout 5s;
    proxy_send_timeout 15s;
    proxy_read_timeout 65s;
    proxy_buffering on;
    proxy_buffers 8 16k;
    proxy_buffer_size 16k;
    proxy_busy_buffers_size 32k;
    proxy_pass http://paroll_gunicorn;
  }

  location ^~ /oauth/ {
    limit_req zone=paroll_auth burst=8 nodelay;
    limit_req_status 429;
    include snippets/paroll-proxy.conf;
    proxy_connect_timeout 5s;
    proxy_send_timeout 15s;
    proxy_read_timeout 65s;
    proxy_buffering on;
    proxy_buffers 8 16k;
    proxy_buffer_size 16k;
    proxy_busy_buffers_size 32k;
    proxy_pass http://paroll_gunicorn;
  }

  location ^~ /users/login {
    limit_req zone=paroll_auth burst=8 nodelay;
    limit_req_status 429;
    include snippets/paroll-proxy.conf;
    proxy_connect_timeout 5s;
    proxy_send_timeout 15s;
    proxy_read_timeout 65s;
    proxy_buffering on;
    proxy_buffers 8 16k;
    proxy_buffer_size 16k;
    proxy_busy_buffers_size 32k;
    proxy_pass http://paroll_gunicorn;
  }

  location ^~ /users/socials {
    limit_req zone=paroll_auth burst=8 nodelay;
    limit_req_status 429;
    include snippets/paroll-proxy.conf;
    proxy_connect_timeout 5s;
    proxy_send_timeout 15s;
    proxy_read_timeout 65s;
    proxy_buffering on;
    proxy_buffers 8 16k;
    proxy_buffer_size 16k;
    proxy_busy_buffers_size 32k;
    proxy_pass http://paroll_gunicorn;
  }

  # --- WebSockets (daphne). Long-lived: buffering off, long read timeout ---
  location ^~ /ws/ {
    include snippets/paroll-proxy.conf;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_connect_timeout 5s;
    proxy_send_timeout 60s;
    proxy_read_timeout 86400s;
    proxy_buffering off;
    proxy_pass http://paroll_daphne;
  }

  # --- liveness probe: quiet logs, fail fast ---
  location = /health/ {
    access_log off;
    include snippets/paroll-proxy.conf;
    proxy_connect_timeout 3s;
    proxy_send_timeout 5s;
    proxy_read_timeout 5s;
    proxy_buffering on;
    proxy_pass http://paroll_gunicorn;
  }

  location = /nginx-status {
    stub_status;
    allow 127.0.0.1;
    deny all;
    access_log off;
  }

  location ~ /\. {
    deny all;
    access_log off;
    log_not_found off;
  }

  location / {
    limit_req zone=paroll_general burst=50 nodelay;
    limit_req_status 429;
    include snippets/paroll-proxy.conf;
    proxy_connect_timeout 5s;
    proxy_send_timeout 15s;
    proxy_read_timeout 65s;
    proxy_buffering on;
    proxy_buffers 8 16k;
    proxy_buffer_size 16k;
    proxy_busy_buffers_size 32k;
    proxy_next_upstream error timeout http_502 http_503;
    proxy_pass http://paroll_gunicorn;
  }
}
EOF
}

CERT_DIR="/etc/letsencrypt/live/$DOMAIN"

# --- dry run: render to tmp, self-signed cert, nginx -t -----------------------
if [[ $DRY_RUN -eq 1 ]]; then
  # shellcheck disable=SC2155
  export TMPD="$(mktemp -d /tmp/opencode/nginx-test.XXXXXX)"
  ROOT="$TMPD"
  ETC_NGINX="$ROOT/etc/nginx"
  SITES_AVAILABLE="$ETC_NGINX/sites-available"
  SITES_ENABLED="$ETC_NGINX/sites-enabled"
  CONF_D="$ETC_NGINX/conf.d"
  SNIPPETS="$ETC_NGINX/snippets"
  CERT_DIR="$TMPD/cert"
  mkdir -p "$SITES_AVAILABLE" "$SITES_ENABLED" "$CONF_D" "$SNIPPETS" "$CERT_DIR" \
    "$TMPD/logs" "$TMPD/www"
  openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
    -keyout "$CERT_DIR/privkey.pem" -out "$CERT_DIR/fullchain.pem" \
    -subj "/CN=$DOMAIN" >/dev/null 2>&1
  cp "$CERT_DIR/fullchain.pem" "$CERT_DIR/chain.pem"
  write_http_conf
  write_security_snippet
  write_proxy_snippet
  write_site_full
  # nginx include paths in the rendered files are absolute (/etc/nginx/...);
  # rewrite them to the tmp tree for the test.
  grep -rl "snippets/" "$SITES_AVAILABLE" "$CONF_D" \
    | xargs sed -i "s#snippets/#$SNIPPETS/#g"
  sed -i "s#/var/log/nginx/#$TMPD/logs/#g" "$SITES_AVAILABLE/$SITE_NAME"
  # Unprivileged test run: remap privileged ports (syntax check only).
  sed -i -E "s/listen (\[::\]:)?80([^0-9]|$)/listen \118080\2/g; s/listen (\[::\]:)?443([^0-9]|$)/listen \118443\2/g" \
    "$SITES_AVAILABLE/$SITE_NAME"
  cat >"$TMPD/test.conf" <<EOF2
worker_processes 1;
error_log $TMPD/logs/error.log;
pid $TMPD/nginx.pid;
events { worker_connections 64; }
http {
  include /etc/nginx/mime.types;
  access_log $TMPD/logs/access.log;
  include $CONF_D/paroll-http.conf;
  include $SITES_ENABLED/$SITE_NAME;
}
EOF2
  ln -sfn "$SITES_AVAILABLE/$SITE_NAME" "$SITES_ENABLED/$SITE_NAME"
  log "rendered to $TMPD"
  nginx -t -c "$TMPD/test.conf" -p "$TMPD/"
  log "dry-run OK: $TMPD"
  exit 0
fi

# --- real install --------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  echo "ERROR: run as root (sudo)." >&2
  exit 1
fi

log "domain(s): $ALL_DOMAINS"
log "app dir:   $APP_DIR"

if ! command -v nginx >/dev/null 2>&1; then
  log "installing nginx + certbot ..."
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y nginx certbot
fi

for d in "$APP_DIR/staticfiles" "$APP_DIR/media"; do
  [[ -d "$d" ]] || warn "missing $d — run collectstatic / check mounts."
done
if command -v sudo >/dev/null 2>&1; then
  sudo -u www-data test -r "$APP_DIR/staticfiles" \
    || warn "www-data cannot read $APP_DIR/staticfiles (static will 403)."
fi

mkdir -p "$SITES_AVAILABLE" "$SITES_ENABLED" "$CONF_D" "$SNIPPETS" /var/www/html
if [[ -f "$SITES_AVAILABLE/$SITE_NAME" ]]; then
  cp -a "$SITES_AVAILABLE/$SITE_NAME" "$SITES_AVAILABLE/$SITE_NAME.bak.$(date +%F-%T)"
  log "backed up existing site file"
fi

write_http_conf
write_security_snippet
write_proxy_snippet
ln -sfn "$SITES_AVAILABLE/$SITE_NAME" "$SITES_ENABLED/$SITE_NAME"

CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
NEED_CERT=1
if [[ -f "$CERT_DIR/fullchain.pem" && -f "$CERT_DIR/privkey.pem" ]]; then
  # valid for >24h?
  if openssl x509 -checkend 86400 -noout -in "$CERT_DIR/fullchain.pem" 2>/dev/null; then
    NEED_CERT=0
    log "existing certificate is valid, reuse it"
  fi
fi

if [[ $NEED_CERT -eq 1 && $SKIP_CERT -eq 0 ]]; then
  write_site_http_bootstrap
  nginx -t
  if pgrep -x nginx >/dev/null 2>&1; then nginx -s reload; else nginx; fi
  CERT_ARGS=()
  for d in $ALL_DOMAINS; do CERT_ARGS+=(-d "$d"); done
  [[ $STAGING -eq 1 ]] && CERT_ARGS+=(--staging)
  log "requesting certificate for: $ALL_DOMAINS"
  certbot certonly --non-interactive --agree-tos --email "$EMAIL" \
    --webroot -w /var/www/html "${CERT_ARGS[@]}"
elif [[ $NEED_CERT -eq 1 && $SKIP_CERT -eq 0 ]]; then
  : # unreachable guard
elif [[ $NEED_CERT -eq 1 ]]; then
  warn "--skip-cert with no certificate: installing HTTP-only bootstrap site."
  write_site_http_bootstrap
  nginx -t
  if pgrep -x nginx >/dev/null 2>&1; then nginx -s reload; else nginx; fi
  log "done (HTTP only). Re-run without --skip-cert once DNS/port 80 is ready."
  exit 0
fi

write_site_full
nginx -t
if pgrep -x nginx >/dev/null 2>&1; then nginx -s reload; else nginx; fi
log "nginx reloaded with HTTPS site"

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null 2>&1 || true
  ufw allow 443/tcp >/dev/null 2>&1 || true
  log "ufw: allowed 80, 443"
fi

# --- verify --------------------------------------------------------------------
echo
log "verify:"
curl -sS -m 10 -o /dev/null -w "  http://%s/health/ -> canonical redirect expected\n" "$DOMAIN" || warn "port 80 probe failed"
if curl -sk -m 10 -o /dev/null -w "  https://$DOMAIN/health/ -> %{http_code} (want 200)\n" "https://$DOMAIN/health/"; then
  CODE="$(curl -sk -m 10 -o /dev/null -w '%{http_code}' "https://$DOMAIN/health/")"
  [[ "$CODE" == "200" ]] || warn "health returned $CODE (want 200)"
else
  warn "https probe failed (DNS not pointed yet?)"
fi

cat <<EOF

Next steps:
  1. DNS: A/AAAA for $ALL_DOMAINS -> this host. (Re-run script once set.)
  2. Renewal is automatic via the certbot systemd timer ('systemctl list-timers | grep certbot').
  3. REQUIRED companion fix (container HEALTHCHECK still uses plain HTTP
     without X-Forwarded-Proto, so /health/ 301-loops inside the container):
       # core/settings.py (and core/settings_saas.py if it overrides SecurityMiddleware)
       SECURE_REDIRECT_EXEMPT = [r"^health/", r"^ready/"]
     Without this, gunicorn WORKER TIMEOUTs continue on the container's own probes.
  4. Optional: set SECURE_HSTS_SECONDS=0 in .env — nginx already sends HSTS,
     so Django's duplicate header is redundant.
  5. Watch: 'tail -f /var/log/nginx/paroll-*.log' and
     'curl http://127.0.0.1/nginx-status' (localhost only).
EOF
