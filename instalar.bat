@echo off
rem Instala o Olhar-mouse neste PC: Python (se faltar), dependencias e atalhos com o icone do olho.
rem Rode com dois cliques depois de extrair o ZIP. Pode rodar de novo para atualizar/reparar.
chcp 65001 >nul
cd /d "%~dp0"
title Instalacao do Olhar-mouse
echo.
echo  ==========================================
echo   Instalacao do Olhar-mouse
echo  ==========================================
echo.

rem --- 1. Python 3.12 (o MediaPipe funciona com 3.9 a 3.12)
set PY=
py -3.12 -c "pass" >nul 2>&1 && set PY=py -3.12
if not defined PY py -3.11 -c "pass" >nul 2>&1 && set PY=py -3.11
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined PY goto tem_python

echo  [1/4] Python 3.12 nao encontrado. Instalando pelo winget...
echo        (o Windows pode pedir confirmacao)
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if not exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" goto sem_python
set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

:tem_python
echo  [1/4] Python: %PY%

rem --- 2. Ambiente proprio do programa (nao mexe no Python do sistema)
if exist ".venv\Scripts\python.exe" goto tem_venv
echo  [2/4] Criando o ambiente do programa...
%PY% -m venv .venv
if errorlevel 1 goto erro
:tem_venv
echo  [2/4] Ambiente pronto.

rem --- 3. Dependencias (~380 MB, alguns minutos na primeira vez)
echo  [3/4] Instalando as dependencias (MediaPipe, OpenCV...). Aguarde...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto erro

rem --- 4. Atalhos na Area de Trabalho e no menu Iniciar
echo  [4/4] Criando os atalhos "Olhar-mouse"...
".venv\Scripts\python.exe" -c "from pathlib import Path; from olhar.bandeja import criar_atalhos; l = criar_atalhos(Path('.').resolve()); [print('        ' + str(x)) for x in l]; raise SystemExit(0 if l else 1)"
if errorlevel 1 goto erro

echo.
echo  Pronto! Abra pelo icone "Olhar-mouse" na Area de Trabalho ou no menu Iniciar.
echo  Com o programa aberto, o icone do olho fica perto do relogio (setinha ^).
echo.
choice /c SN /m " Abrir o Olhar-mouse agora"
if errorlevel 2 exit /b 0
start "" ".venv\Scripts\pythonw.exe" -m olhar
exit /b 0

:sem_python
echo.
echo  Nao consegui instalar o Python automaticamente.
echo  Instale o Python 3.12 por https://www.python.org/downloads/ (marque "Add python.exe to PATH")
echo  e rode este instalador de novo.
pause
exit /b 1

:erro
echo.
echo  Algo deu errado na instalacao. Veja a mensagem acima.
echo  Dica: confira a internet e rode o instalar.bat de novo.
pause
exit /b 1
