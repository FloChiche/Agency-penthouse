@echo off
rem Ouvre Agent Tower ; lance le serveur seulement s'il ne tourne pas déjà en arrière-plan.
cd /d "%~dp0"
curl -s -o nul http://localhost:4317/api/state && (start "" http://localhost:4317 & exit /b)
start "" http://localhost:4317
node server\server.js %*
