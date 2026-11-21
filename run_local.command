#!/bin/bash
# Предпросмотр на Mac: двойной клик. Откроется http://localhost:8000 с демо-данными (без Telegram).
cd "$(dirname "$0")" || exit 1
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done
if [ -z "$PY" ]; then echo "Не найден Python 3. Установите: brew install python"; read -r; exit 1; fi
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt || { echo "Не удалось поставить зависимости"; read -r; exit 1; }
export DEV=1 RUN_BOT=0 RUN_JOBS=0 ADMIN_IDS=1001 DATABASE_URL="sqlite+aiosqlite:///./preview.db"
.venv/bin/python -m app.seed
(sleep 2; open "http://localhost:8000/?dev=1001") &
.venv/bin/python -m uvicorn app.main:app --port 8000
