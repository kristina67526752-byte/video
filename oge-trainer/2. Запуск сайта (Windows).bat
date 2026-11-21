@echo off
chcp 65001 >nul
cd /d "%~dp0"
where npm >nul 2>nul || (echo Не найден Node.js. Установите его с сайта nodejs.org ^(версия LTS^) и запустите этот файл снова. & start https://nodejs.org/ & pause & exit /b 1)
if not exist node_modules call npm install --no-audit --no-fund
if not exist .env.local call npm run setup
echo Запускаю сайт... Чтобы остановить, закройте это окно.
call npm run dev -- --open
