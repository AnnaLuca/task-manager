#!/usr/bin/env bash
# The MANDATORY tests for the demo, step by step (press Enter to continue).
# Useful as a cheat sheet and for collecting evidence; during the live demo it is
# better to TYPE the commands by hand, since the instructor asks for live, independent execution.
#
#   ./scripts/demo.sh | tee docs/test-output.txt
set -uo pipefail
STACK=project
URL=${URL:-http://localhost:8080}

step() { echo; echo "================ $* ================"; read -rp "[Enter] " _; }
run()  { echo "\$ $*"; eval "$@"; }

step "0. Overview: nodes, services, tasks"
run docker node ls
run docker stack services $STACK
run docker stack ps $STACK --filter desired-state=running

step "1. FUNCTIONAL TEST - write data and read it back (through the frontend to the API)"
run "curl -s -X POST $URL/api/tasks -H 'Content-Type: application/json' -d '{\"title\":\"Demo task $(date +%H:%M:%S)\"}'"
echo
run "curl -s $URL/api/tasks | head -c 400"
echo

step "2. LOAD BALANCING - 10 requests, which API replica answers?"
run "for i in \$(seq 10); do curl -s $URL/api/info | grep -o '\"served_by\":\"[^\"]*\"'; done | sort | uniq -c"

step "3. SCALING - api: 2 -> 3 replicas"
run docker service scale ${STACK}_api=3
run docker service ps ${STACK}_api --filter desired-state=running
run "for i in \$(seq 12); do curl -s $URL/api/info | grep -o '\"served_by\":\"[^\"]*\"'; done | sort | uniq -c"

step "4. SELF-HEALING - kill one API container"
VICTIM=$(docker ps -q --filter "label=com.docker.swarm.service.name=${STACK}_api" | head -1)
run docker ps --filter "label=com.docker.swarm.service.name=${STACK}_api"
run docker kill "$VICTIM"
echo "... waiting 15 s for Swarm to replace it"; sleep 15
run docker service ps ${STACK}_api
run docker service ls --filter name=${STACK}_api

step "5. PERSISTENCE - recreate the database container"
run "curl -s $URL/api/tasks | grep -o '\"id\":[0-9]*' | wc -l"
run docker service update --force ${STACK}_db
echo "... waiting for the DB and the API to reconnect"; sleep 15
run docker volume ls --filter name=${STACK}_db-data
run "curl -s $URL/api/tasks | grep -o '\"id\":[0-9]*' | wc -l"
echo "(the two numbers match -> the data survived)"

step "6. SCALE BACK TO 2"
run docker service scale ${STACK}_api=2

step "7. EXTERNAL ACCESS - open it on your phone, over mobile data"
docker service logs ${STACK}_tunnel 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
echo "Done."
