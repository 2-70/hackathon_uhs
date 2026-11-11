@echo off
setlocal
pushd "%~dp0..\..\.." || exit /b 1

set "PREVIEW_PYTHON=%TEMP%\washwise-ai-tools\portable-python\python.exe"
if not exist "%PREVIEW_PYTHON%" set "PREVIEW_PYTHON=.venv\Scripts\python.exe"
if not exist "%PREVIEW_PYTHON%" set "PREVIEW_PYTHON=python"

"%PREVIEW_PYTHON%" -B -m backend.tests.ai.launch_preview %*
set "PREVIEW_EXIT=%ERRORLEVEL%"
if not "%PREVIEW_EXIT%"=="0" pause
popd
exit /b %PREVIEW_EXIT%
