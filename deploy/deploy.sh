#!/usr/bin/env bash
# Sync the app to the droplet and (re)start it with Docker Compose.
# Usage: deploy/deploy.sh [host]     (default host: the reserved IP from terraform output)
# Env:   SSH_KEY (default ~/.ssh/mlops_do), DOMAIN (default ucu.nlp.justsolution.co)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${1:-$(terraform -chdir="$ROOT/deploy/terraform" output -raw ip)}"
KEY="${SSH_KEY:-$HOME/.ssh/mlops_do}"
DOMAIN="${DOMAIN:-ucu.nlp.justsolution.co}"
REMOTE="root@$HOST"
[ -f "$ROOT/deploy/auth.caddy" ] || { echo "no login yet: run deploy/set_login.sh first" >&2; exit 1; }
# Own known_hosts file: a re-created droplet behind the same reserved IP gets a new host key.
RSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$ROOT/deploy/.known_hosts -o ConnectTimeout=10"

echo "waiting for SSH on $HOST ..."
for _ in $(seq 1 30); do $RSH "$REMOTE" true 2>/dev/null && break; sleep 10; done
$RSH "$REMOTE" "cloud-init status --wait >/dev/null; docker compose version"

echo "syncing code and data ..."
rsync -az --delete --exclude-from="$ROOT/deploy/rsync-exclude.txt" -e "$RSH" "$ROOT/" "$REMOTE:/srv/nda/"
# The LLM cache is merged, never deleted: the server adds entries for contracts reviewed there.
rsync -az -e "$RSH" "$ROOT/.cache/" "$REMOTE:/srv/nda/.cache/"
# The Groq key travels as a file and is only read by python-dotenv on the server.
rsync -az --chmod=F600 -e "$RSH" "$ROOT/.env" "$REMOTE:/srv/nda/.env"

echo "building and starting ..."
$RSH "$REMOTE" "cd /srv/nda/deploy && DOMAIN=$DOMAIN docker compose up -d --build --remove-orphans && docker compose ps"
echo "done: http://$HOST  (https://$DOMAIN once the DNS record points to $HOST)"
