@echo off
chcp 65001 >nul
title AI日报推送服务

cd /d "%~dp0"

echo ========================================
echo   AI日报推送服务
echo ========================================

:parse_args
if "%1"=="--test" (
    set TEST_MODE=--test
    echo [模式] 测试模式（仅邮件发送给本人）
    shift
    goto parse_args
)
if "%1"=="--repush" (
    set REPUSH_MODE=--repush
    echo [模式] 补推模式
    shift
    goto parse_args
)

echo [步骤1] 查找今日PNG...
py -m src.html_to_png
if errorlevel 1 (
    echo [警告] PNG转换失败或HTML不存在，继续尝试推送已有PNG
)

echo [步骤2] 运行推送主程序...
py -m src.push.orchestrator %TEST_MODE% %REPUSH_MODE%

echo.
echo ========================================
if errorlevel 1 (
    echo [结果] 推送失败
) else (
    echo [结果] 推送完成
)
echo ========================================

pause
