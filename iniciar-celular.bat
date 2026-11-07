@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  Camera do celular
echo  -----------------
echo  IP Webcam (Android): abra o app, toque em "Iniciar servidor" e digite o
echo  endereco que aparece na tela, ex.: 192.168.0.10:8080
echo  DroidCam: digite apenas o numero da webcam virtual (normalmente 1).
echo  PC e celular precisam estar na mesma rede Wi-Fi.
echo.
set ULTIMO=
if exist dados\celular.txt set /p ULTIMO=<dados\celular.txt
if defined ULTIMO echo  Ultimo usado: %ULTIMO%  (Enter para usar de novo)
set ENDERECO=
set /p ENDERECO= Endereco: 
if not defined ENDERECO set ENDERECO=%ULTIMO%
if not defined ENDERECO (echo Nenhum endereco informado.& pause & exit /b 1)
if not exist dados mkdir dados
>dados\celular.txt echo %ENDERECO%
set FONTE=%ENDERECO%
echo %ENDERECO%| findstr /r "^[0-9][0-9]*$" >nul || (
  echo %ENDERECO%| findstr /i "^http" >nul && set FONTE=%ENDERECO% || set FONTE=http://%ENDERECO%/video
)
echo  Abrindo %FONTE% ...
.venv\Scripts\python -m olhar --camera "%FONTE%"
pause
