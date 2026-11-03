@echo off
rem Lance Agent Tower en mode démo (activité simulée).
cd /d "%~dp0"
start "" http://localhost:4317
node server\server.js --demo
