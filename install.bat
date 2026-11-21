@echo off
chcp 65001 >nul
setlocal

rem ============================================================
rem  文本文件读取插件 · 本机一键安装脚本
rem
rem  用法：
rem    install.bat "<AstrBot根目录>"      （AstrBot 根目录，含 data\plugins 的那层）
rem    或先设置环境变量 ASTRBOT_ROOT
rem  目标目录：<AstrBot根目录>\data\plugins\astrbot_plugin_text_file_reader
rem
rem  安装后需要到 AstrBot WebUI → 插件管理 重载插件（本机未开启热重载），
rem  或重启 AstrBot。
rem ============================================================

set "ROOT=%~1"
if "%ROOT%"=="" set "ROOT=%ASTRBOT_ROOT%"
if "%ROOT%"=="" (
    echo 请指定 AstrBot 根目录（包含 data\plugins 的那一层目录）。
    set /p ROOT=请输入路径，例如 D:\AstrBot：
)
if "%ROOT%"=="" (
    echo [x] 未提供路径，已退出。
    pause
    exit /b 1
)
if not exist "%ROOT%\data\plugins" (
    echo [x] 没找到 %ROOT%\data\plugins，请确认 AstrBot 根目录填对了。
    pause
    exit /b 1
)

set "SRC=%~dp0."
set "DST=%ROOT%\data\plugins\astrbot_plugin_text_file_reader"

if exist "%DST%" (
    set "BAK=%DST%.bak_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
    set "BAK=%BAK: =0%"
    echo [i] 目标已存在，先备份到 %BAK%
    robocopy "%DST%" "%BAK%" /E /NFL /NDL /NJH /NJS >nul
)

echo [i] 正在安装到 %DST% ...
robocopy "%SRC%" "%DST%" /E /XD .git __pycache__ tests /XF *.pyc /NFL /NDL /NJH /NJS >nul
if errorlevel 8 (
    echo [x] 复制失败，请检查目标目录是否被占用。
    pause
    exit /b 1
)

echo [ok] 已安装。
echo     请到 AstrBot WebUI - 插件管理 重载本插件（或重启 AstrBot）。
echo     验证：私聊发一个 .md 文件后提问；群聊先发文件再 @机器人。
pause
