@echo off
cd /d "%~dp0"

set LOGFILE=logs\daily_update.log
if not exist logs mkdir logs

echo [%date% %time%] ==== daily update start ==== >> "%LOGFILE%"

REM ---- locate python interpreter ----
set PYEXE=
where python >nul 2>&1
if %errorlevel%==0 set PYEXE=python
if not defined PYEXE (
  where py >nul 2>&1
  if %errorlevel%==0 set PYEXE=py
)
if not defined PYEXE (
  echo [%date% %time%] ERROR: Python not found in PATH >> "%LOGFILE%"
  exit /b 1
)

REM ---- collect sources and rebuild static site ----
echo [%date% %time%] collecting and generating site... >> "%LOGFILE%"
%PYEXE% run.py full --workers 8 >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] ERROR: pipeline failed >> "%LOGFILE%"
  exit /b 1
)

REM ---- publish: push triggers Cloudflare Pages deploy ----
echo [%date% %time%] publishing to GitHub... >> "%LOGFILE%"
git add site config >> "%LOGFILE%" 2>&1
git diff --cached --quiet
if errorlevel 1 (
  git -c user.name="ChristianNews Bot" -c user.email="bot@christian-news.local" commit -m "chore: daily auto update [%date%]" >> "%LOGFILE%" 2>&1
  git push origin master >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    echo [%date% %time%] WARN: git push failed, check credentials >> "%LOGFILE%"
  ) else (
    echo [%date% %time%] published to GitHub >> "%LOGFILE%"
  )
) else (
  echo [%date% %time%] no content changes to publish >> "%LOGFILE%"
)

echo [%date% %time%] ==== daily update done ==== >> "%LOGFILE%"
exit /b 0
