#!/usr/bin/env sh
# Creates .env from .env.example with freshly generated secrets (Linux/macOS).
set -eu
cd "$(dirname "$0")/.."
[ -f .env ] && { echo ".env already exists - leaving it alone."; exit 0; }
hex() { od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'; }
fernet() { head -c 32 /dev/urandom | base64 | tr '+/' '-_'; }
admin_pw="Strata-$(hex 6)!"
sed -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(hex 24)|" \
    -e "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=$(hex 24)|" \
    -e "s|^JWT_SECRET=.*|JWT_SECRET=$(hex 32)|" \
    -e "s|^FILE_ENCRYPTION_KEY=.*|FILE_ENCRYPTION_KEY=$(fernet)|" \
    -e "s|^BOOTSTRAP_ADMIN_PASSWORD=.*|BOOTSTRAP_ADMIN_PASSWORD=$admin_pw|" \
    .env.example > .env
echo "Created .env"
echo "  First admin:    admin@example.com"
echo "  Admin password: $admin_pw   (change it after first sign-in)"
echo "Next: docker compose --profile local-llm up -d --build"
