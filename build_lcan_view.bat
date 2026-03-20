@echo off
chcp 65001 >nul
set "BASE_NAME=LCAN-View"

:ask_version
set "APP_VERSION="
set /p APP_VERSION=请输入版本号（例如 3.0.1）: 
if "%APP_VERSION%"=="" (
    echo [提示] 版本号不能为空，请重新输入。
    goto ask_version
)
set "APP_VERSION=%APP_VERSION: =_%"
set "EXE_NAME=%BASE_NAME%_v%APP_VERSION%"

echo ====================================
echo LCAN-View 自动打包脚本
echo ====================================
echo.

:: 检查是否安装了pyinstaller
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 pyinstaller，正在安装...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo [错误] 安装 pyinstaller 失败！
        pause
        exit /b 1
    )
)

echo [信息] 开始打包 LCAN-View...
echo [信息] 输出文件名: %EXE_NAME%.exe
echo.

:: 执行打包命令
pyinstaller --noconsole --onefile --name "%EXE_NAME%" --icon="LCAN-View.ico" --add-binary "gs_usb.cp314-mingw_x86_64_ucrt_gnu.pyd;." --add-binary "C:/msys64/ucrt64/bin/libusb-1.0.dll;." up2.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败！
    pause
    exit /b 1
)

echo.
echo ====================================
echo [完成] 打包成功！
echo 可执行文件位于: dist\%EXE_NAME%.exe
echo ====================================
echo.
pause
