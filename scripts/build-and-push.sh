#!/usr/bin/env bash
# Builds our two own images and pushes them to the registry (GHCR or Docker Hub).
#
# Usage:
#   export IMAGE_PREFIX=ghcr.io/<github-username>   # or: docker.io/<dockerhub-username>
#   export TAG=1.0.0
#   ./scripts/build-and-push.sh
#
# Log in once beforehand:
#   GHCR:       echo <GITHUB_TOKEN> | docker login ghcr.io -u <github-username> --password-stdin
#   Docker Hub: docker login
set -euo pipefail
cd "$(dirname "$0")/.."

: "${IMAGE_PREFIX:?Set it first: export IMAGE_PREFIX=ghcr.io/<username>}"
: "${TAG:=1.0.0}"
export IMAGE_PREFIX TAG

echo ">> Build: ${IMAGE_PREFIX}/task-manager-{frontend,api}:${TAG}"
docker compose build frontend api

echo ">> Push"
docker compose push frontend api

echo ">> Done. stack.yml refers to exactly these image names."
