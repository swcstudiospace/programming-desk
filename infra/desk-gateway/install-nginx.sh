#!/usr/bin/env bash
# Install the desk.swcstudio.space nginx vhosts. Safe to rerun. Prints the certbot command
# instead of running it: issuing a certificate is a one-time operator step, and the run is
# recorded in the INFRA receipt.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "install-nginx.sh: must run as root" >&2; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST=desk.swcstudio.space
AVAIL=/etc/nginx/sites-available
ENABLED=/etc/nginx/sites-enabled
CERT="/etc/letsencrypt/live/$HOST/fullchain.pem"

install -d -m 0755 /var/www/certbot
install -m 0644 "$HERE/nginx-$HOST.conf"     "$AVAIL/$HOST.conf"
install -m 0644 "$HERE/nginx-$HOST-ssl.conf" "$AVAIL/$HOST-ssl.conf"
ln -sfn "$AVAIL/$HOST.conf" "$ENABLED/$HOST.conf"

# The SSL vhost names the certificate files, so nginx -t fails while they are absent.
# Enable it only once certbot has issued them; a rerun after certbot completes the job.
if [[ -f "$CERT" ]]; then
  ln -sfn "$AVAIL/$HOST-ssl.conf" "$ENABLED/$HOST-ssl.conf"
else
  rm -f "$ENABLED/$HOST-ssl.conf"
  echo "install-nginx.sh: no certificate at $CERT yet — HTTPS vhost left disabled."
fi

nginx -t
systemctl reload nginx

if [[ -f "$CERT" ]]; then
  echo "install-nginx.sh: HTTPS enabled. Renewal is certbot's timer; re-issue only if the cert is lost:"
else
  echo "install-nginx.sh: DNS for $HOST must point at 187.77.130.10, then issue the certificate and rerun this script:"
fi
echo "  certbot certonly --webroot -w /var/www/certbot -d $HOST"
