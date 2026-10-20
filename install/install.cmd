@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set "marathon_exit=%errorlevel%"
if not defined MARATHON_INSTALL_NO_PAUSE pause
exit /b %marathon_exit%
