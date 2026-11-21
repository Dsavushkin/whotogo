#!/usr/bin/env bash
# Связь бота с Telegram через ваш зарубежный сервер (SSH-туннель). Запускать на российском сервере:
#   cd /opt/whotogo && bash deploy/tunnel.sh
set -euo pipefail
cd "$(dirname "$0")/.."
KEYS=deploy/tunnel
mkdir -p "$KEYS" && chmod 700 "$KEYS"

read -r -p "IP зарубежного сервера: " HOST
read -r -p "SSH-порт на нём [22]: " PORT
PORT=${PORT:-22}
[ -n "$HOST" ] || { echo "Нужен IP."; exit 1; }

[ -f "$KEYS/id_ed25519" ] || ssh-keygen -q -t ed25519 -N "" -C whotogo-tunnel -f "$KEYS/id_ed25519"
MYIP=$(curl -fsS4 --max-time 8 https://api.ipify.org || curl -fsS4 --max-time 8 https://ifconfig.me || true)
FROM=""
[ -n "$MYIP" ] && FROM="from=\"$MYIP\","
LINE="${FROM}restrict,port-forwarding $(cat "$KEYS/id_ed25519.pub")"

echo
echo "================ Скопируйте и выполните на ЗАРУБЕЖНОМ сервере ($HOST) под root ================"
echo
echo "id tgproxy >/dev/null 2>&1 || useradd -m -s /usr/sbin/nologin tgproxy; mkdir -p /home/tgproxy/.ssh && echo '$LINE' > /home/tgproxy/.ssh/authorized_keys && chown -R tgproxy: /home/tgproxy/.ssh && chmod 700 /home/tgproxy/.ssh && chmod 600 /home/tgproxy/.ssh/authorized_keys && echo ГОТОВО"
echo
echo "============================================================================================="
echo "Это только добавляет пользователя tgproxy, который может работать как туннель и только с IP ${MYIP:-этого сервера}."
read -r -p "Выполнили и увидели ГОТОВО? Нажмите Enter… " _

ssh-keyscan -p "$PORT" -T 10 "$HOST" > "$KEYS/known_hosts" 2>/dev/null
[ -s "$KEYS/known_hosts" ] || { echo "❌ Не достучался до $HOST:$PORT по SSH. Проверьте IP и порт."; exit 1; }

echo "== Проверяю туннель"
ssh -N -D 127.0.0.1:1081 -p "$PORT" -i "$KEYS/id_ed25519" -o UserKnownHostsFile="$KEYS/known_hosts" \
  -o StrictHostKeyChecking=yes -o BatchMode=yes -o ExitOnForwardFailure=yes "tgproxy@$HOST" &
SSH_PID=$!
sleep 5
CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 --socks5-hostname 127.0.0.1:1081 https://api.telegram.org/ || true)
kill $SSH_PID 2>/dev/null || true
if [ "$CODE" = "000" ] || [ -z "$CODE" ]; then
  echo "❌ Туннель не заработал. Частые причины: команда на зарубежном сервере не выполнена,"
  echo "   или там в /etc/ssh/sshd_config стоит AllowTcpForwarding no либо AllowUsers без tgproxy."
  exit 1
fi
echo "   ✓ Telegram отвечает через $HOST (код $CODE)"

set_env() { grep -q "^$1=" .env && sed -i "s|^$1=.*|$1=$2|" .env || echo "$1=$2" >> .env; }
set_env TELEGRAM_PROXY "socks5://tgtunnel:1080"
set_env TUNNEL_HOST "$HOST"
set_env TUNNEL_PORT "$PORT"
set_env COMPOSE_PROFILES "tunnel"

echo "== Перезапускаю сервис"
docker compose up -d --build
sleep 25
DOMAIN=$(grep '^DOMAIN=' .env | cut -d= -f2)
curl -s "https://$DOMAIN/api/diag" | grep -o '"bot":"[^"]*"\|"telegram_via_proxy":[^,}]*' || true
echo
echo "✅ Готово. Напишите боту /start."
