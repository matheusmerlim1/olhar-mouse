@echo off
rem Olhar-mouse com a webcam do computador.
cd /d "%~dp0"
call iniciar.bat --camera 0 %*
