#!/usr/bin/env bash
# Create the production .env on the server. Generates secrets and asks only for the
# Anthropic API key. The site address defaults to <public-ip>.sslip.io, which resolves to
# this server and gets a free HTTPS certificate; pass a domain to use your own instead.
#
#   ./deploy/make-env.sh                 # e.g. https://3-112-45-67.sslip.io
#   ./deploy/make-env.sh app.example.com
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  echo ".env already exists; edit it instead of regenerating." >&2
  exit 1
fi

ip=$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')
domain="${1:-${ip//./-}.sslip.io}"

# -s keeps the key off the screen and out of shell history.
read -rsp "Anthropic API key: " api_key
echo

umask 077  # .env readable by this user only
cat > .env <<EOF
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=$(openssl rand -hex 32)
DJANGO_ALLOWED_HOSTS=${domain},localhost
DJANGO_CSRF_TRUSTED_ORIGINS=https://${domain}
ANTHROPIC_API_KEY=${api_key}
LLM_MODEL=claude-opus-5-5
LLM_EFFORT=medium
SITE_ADDRESS=${domain}
POSTGRES_DB=rhombus
POSTGRES_USER=rhombus
POSTGRES_PASSWORD=$(openssl rand -hex 24)
EOF

echo "Wrote .env for https://${domain}"
