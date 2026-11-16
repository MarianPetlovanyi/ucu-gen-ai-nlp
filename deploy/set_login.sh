#!/usr/bin/env bash
# Create or change the demo login (HTTP basic auth in Caddy, covers the UI and /api/*).
# Usage: deploy/set_login.sh [user]          password from NDA_PASSWORD, otherwise a random one
# Writes deploy/.credentials (plain text, local only, git-ignored, never synced) and
#        deploy/auth.caddy   (bcrypt hash only, synced to the server). Then run deploy/deploy.sh.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LOGIN="${1:-ucu}"
PASSWORD="${NDA_PASSWORD:-$(python3 -I -c 'import secrets; print(secrets.token_urlsafe(12))')}"
HASH="$(printf '%s' "$PASSWORD" | uv run --quiet --no-project --with bcrypt python -I -c \
  'import sys, bcrypt; print(bcrypt.hashpw(sys.stdin.buffer.read(), bcrypt.gensalt(12)).decode())')"

umask 077
printf '%s:%s\n' "$LOGIN" "$PASSWORD" > "$DIR/.credentials"
printf 'basic_auth {\n\t%s %s\n}\n' "$LOGIN" "$HASH" > "$DIR/auth.caddy"
echo "login set for user '$LOGIN' (password in deploy/.credentials); run deploy/deploy.sh to apply it"
