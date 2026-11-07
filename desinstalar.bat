@echo off
rem Remove os atalhos do Olhar-mouse e a abertura junto com o Windows.
rem Depois disso basta apagar esta pasta.
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  Desinstalar o Olhar-mouse
echo.
choice /c SN /m " Remover os atalhos e a abertura automatica"
if errorlevel 2 exit /b 0
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*-m olhar*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
powershell -NoProfile -Command "Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Olhar-mouse.lnk') -ErrorAction SilentlyContinue; Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Programs')) 'Olhar-mouse.lnk') -ErrorAction SilentlyContinue"
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v OlharMouse /f >nul 2>&1
echo.
echo  Atalhos e abertura automatica removidos.
echo  Para terminar, apague esta pasta:
echo    %~dp0
echo.
pause
