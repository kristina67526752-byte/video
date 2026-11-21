#!/bin/bash
# Двойной щелчок: запускает сайт и открывает его в браузере. Чтобы остановить — закройте окно терминала.
cd "$(dirname "$0")" || exit 1
if ! command -v npm >/dev/null 2>&1; then
  echo "Не найден Node.js. Установите его с сайта nodejs.org (версия LTS) и запустите этот файл снова."
  open "https://nodejs.org/"
  read -n 1 -s -r -p "Нажмите любую клавишу, чтобы закрыть окно…"
  exit 1
fi
if [ ! -d node_modules ]; then npm install --no-audit --no-fund || exit 1; fi
if [ ! -f .env.local ]; then npm run setup || exit 1; fi
echo "Запускаю сайт… Он откроется в браузере. Чтобы остановить — закройте это окно."
npm run dev -- --open
