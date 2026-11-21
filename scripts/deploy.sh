#!/usr/bin/env bash
# Initialises Swarm (if needed), creates the secret (if needed), deploys the stack.
#
#   export IMAGE_PREFIX=ghcr.io/<username>
#   export TAG=1.0.0
#   ./scripts/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

: "${IMAGE_PREFIX:?Set it first: export IMAGE_PREFIX=ghcr.io/<username>}"
: "${TAG:=1.0.0}"
export IMAGE_PREFIX TAG
STACK=project

if [ "$(docker info --format '{{.Swarm.LocalNodeState}}')" != "active" ]; then
  echo ">> docker swarm init"
  docker swarm init
fi
docker node ls

if ! docker secret inspect db_password >/dev/null 2>&1; then
  echo ">> The db_password secret does not exist yet. Enter the password (it will not be shown):"
  read -rs PW
  printf '%s' "$PW" | docker secret create db_password -
fi

echo ">> docker stack deploy"
docker stack deploy -c stack.yml --with-registry-auth "$STACK"

sleep 5
docker stack services "$STACK"
echo
echo ">> In a few seconds: docker stack ps $STACK"
echo ">> Public URL: docker service logs ${STACK}_tunnel 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1"
