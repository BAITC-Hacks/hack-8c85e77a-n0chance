@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "MOST_NODE=node"
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" set "MOST_NODE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
if not exist node_modules (
  echo Сначала установите Node.js 24 и выполните npm ci в этой папке.
  pause
  exit /b 1
)
echo Собираем МОСТ...
"%MOST_NODE%" scripts/run-framework.mjs build
if errorlevel 1 (
  pause
  exit /b 1
)
"%MOST_NODE%" scripts/demo-server.mjs
pause
