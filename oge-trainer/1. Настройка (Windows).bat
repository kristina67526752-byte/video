@echo off
chcp 65001 >nul
cd /d "%~dp0"
where npm >nul 2>nul || (echo Не найден Node.js. Установите его с сайта nodejs.org ^(версия LTS^) и запустите этот файл снова. & start https://nodejs.org/ & pause & exit /b 1)
if not exist node_modules (echo Устанавливаю нужные программы, около минуты... & call npm install --no-audit --no-fund)
call npm run setup
pause
