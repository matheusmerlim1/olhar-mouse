@echo off
rem Olhar-mouse com a camera do celular: o PC mostra um QR code, o celular abre a pagina.
cd /d "%~dp0"
call iniciar.bat --camera celular %*
