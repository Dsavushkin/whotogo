#!/usr/bin/env bash
# Первая установка на чистый сервер Ubuntu 22/24. Запускать от root из папки проекта:
#   bash deploy/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if ! docker compose version >/dev/null 2>&1; then
  echo "== Ставлю Docker"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q
  # Пакеты Ubuntu доступны всегда; официальный установщик Docker — запасной вариант.
  apt-get install -y -q docker.io docker-compose-v2 || curl -fsSL https://get.docker.com | sh
fi
if [ ! -f /etc/docker/daemon.json ]; then
  # Зеркало на случай, если Docker Hub недоступен или режет скорость.
  echo '{"registry-mirrors": ["https://mirror.gcr.io"]}' > /etc/docker/daemon.json
  systemctl restart docker
fi

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  read -r -p "Токен бота от @BotFather: " token
  read -r -p "Ваш Telegram ID (Enter — пропустить, добавите позже): " admin
  read -r -p "Токен Timepad (Enter — пропустить): " timepad
  sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=${token}|; s|^ADMIN_IDS=.*|ADMIN_IDS=${admin}|; s|^TIMEPAD_TOKEN=.*|TIMEPAD_TOKEN=${timepad}|" .env
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 16)|" .env
fi

if ! grep -q '^DOMAIN=.\+' .env; then
  ip=$(curl -fsS4 https://api.ipify.org || curl -fsS4 https://ifconfig.me)
  sed -i "s|^DOMAIN=.*|DOMAIN=${ip//./-}.sslip.io|" .env
fi

echo "== Собираю и запускаю"
docker compose up -d --build

# Автообновление: раз в 2 минуты сервер проверяет GitHub и пересобирает проект, если код изменился.
cat > /etc/cron.d/whotogo <<CRON
*/2 * * * * root cd $(pwd) && flock -n /tmp/whotogo.lock bash deploy/update.sh >> /var/log/whotogo-update.log 2>&1
CRON

domain=$(grep '^DOMAIN=' .env | cut -d= -f2)
echo
echo "Готово. Адрес приложения: https://${domain}"
echo "Откройте бота и отправьте /start. Сертификат https выпускается 1–2 минуты."
