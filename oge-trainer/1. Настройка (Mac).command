#!/bin/bash
# Двойной щелчок: спросит адрес проекта и ключи Supabase, сохранит их и загрузит задания.
cd "$(dirname "$0")" || exit 1
if ! command -v npm >/dev/null 2>&1; then
  echo "Не найден Node.js. Установите его с сайта nodejs.org (версия LTS) и запустите этот файл снова."
  open "https://nodejs.org/"
  read -n 1 -s -r -p "Нажмите любую клавишу, чтобы закрыть окно…"
  exit 1
fi
if [ ! -d node_modules ]; then
  echo "Устанавливаю нужные программы (один раз, около минуты)…"
  npm install --no-audit --no-fund || { read -n 1 -s -r -p "Ошибка установки. Нажмите любую клавишу…"; exit 1; }
fi
npm run setup
read -n 1 -s -r -p "Готово. Нажмите любую клавишу, чтобы закрыть окно…"
