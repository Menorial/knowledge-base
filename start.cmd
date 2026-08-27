@echo off
rem ============================================================
rem  个人知识库 - 一键启动（CMD 版，绕过 PowerShell 执行策略）
rem
rem  注意：必须输入带扩展名的 start.cmd，不要输入 start
rem        （start 是 CMD 自带命令，会被 Windows 拦截）
rem
rem  用法:  start.cmd            （首次，自动建 venv + 装依赖）
rem         start.cmd -SkipInstall   （日常快速启动）
rem ============================================================
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
