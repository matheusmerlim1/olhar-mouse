@echo off
rem Olhar-mouse com o celular Android pelo cabo USB (sem Wi-Fi, sem internet).
rem Abre sem janela: fica so o icone do olho perto do relogio. Na primeira vez instala o ambiente Python.
rem (cada atalho e completo: nesta pasta com acento o "call outro.bat" do Windows falha)
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Primeira execucao: instalando o ambiente Python...
  py -3.12 -m venv .venv || goto erro
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt || goto erro
)
start "" ".venv\Scripts\pythonw.exe" -m olhar --camera usb %*
exit /b 0
:erro
echo.
echo Algo deu errado na instalacao. Veja a mensagem acima.
pause
exit /b 1
