@echo off
cd /d "%~dp0"
rem Camera do celular por QR code: o PC mostra um QR, o celular abre a pagina e envia a camera.
.venv\Scripts\python -m olhar --camera celular %*
pause
