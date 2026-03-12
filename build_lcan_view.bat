@echo off
chcp 65001 >nul
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
echo.

:: 执行打包命令
pyinstaller --noconsole --onefile --name "LCAN-View" --icon="LCAN-View.ico" --add-binary "gs_usb.cp314-mingw_x86_64_ucrt_gnu.pyd;." --add-binary "C:/msys64/ucrt64/bin/libusb-1.0.dll;." up2.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败！
    pause
    exit /b 1
)

echo.
echo ====================================
echo [完成] 打包成功！
echo 可执行文件位于: dist\LCAN-View.exe
echo ====================================
echo.
pause
