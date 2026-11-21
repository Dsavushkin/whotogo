#!/usr/bin/env bash
# Подтягивает новый код из GitHub и перезапускает сервис, если что-то изменилось.
set -euo pipefail
cd "$(dirname "$0")/.."
git fetch -q origin main
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
  echo "$(date '+%F %T') обновляю до $(git rev-parse --short origin/main)"
  git reset -q --hard origin/main
  docker compose up -d --build
  docker image prune -f >/dev/null
fi
