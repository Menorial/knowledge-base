@echo off
rem ============================================================
rem  个人知识库 - 一键启动（CMD 版，绕过 PowerShell 执行策略）
rem  用法:  start       （首次，自动建 venv + 装依赖）
rem         start -SkipInstall   （日常快速启动）
rem ============================================================
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
