@echo off
title Rise of Kingdoms Bot Launcher
color 0a

echo ======================================
echo      Rise of Kingdoms Bot - Start
echo ======================================
echo.

REM 
python --version >nul 2>&1
if errorlevel 1 (
    echo [❌] Python chưa được cài đặt hoặc chưa có trong PATH.
    pause
    exit /b
)

echo [✔] Python đã được phát hiện.
echo.

REM 
echo [🔄] Đang cài/ cập nhật thư viện cần thiết...
echo.

REM 
start /b cmd /c "python -m pip install --upgrade pip && python -m pip install --upgrade opencv-python PyQt5 > install.log 2>&1" 

set "spinner=|/-\"
:loop
for /l %%i in (0,1,3) do (
    <nul set /p= [⚙] Đang xử lý... !spinner:~%%i,1!
 
    ping -n 2 localhost >nul
    if not exist install.log (
        cls
        echo ======================================
        echo      Rise of Kingdoms Bot - Start
        echo ======================================
        echo.
        echo [✔] Cài đặt hoàn tất!
        goto done
    )
)
goto loop

:done
echo.
echo [🚀] Khởi chạy Bot...
python main.py

echo.
echo [⚠] Kết thúc !
pause


