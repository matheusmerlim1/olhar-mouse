@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Criando o ambiente Python pela primeira vez...
  py -3.12 -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python -m olhar %*
pause
