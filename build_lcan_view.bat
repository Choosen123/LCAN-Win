@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ================= 配置区 =================
set "BASE_NAME=LCAN-View"
set "EXE_NAME=%BASE_NAME%"

:: 路径配置
set "PKG_ROOT=.packaging"
set "DIST_DIR=%PKG_ROOT%\dist"
set "PYI_WORK_DIR=%PKG_ROOT%\build"
set "SPEC_DIR=%PKG_ROOT%"
set "SPEC_FILE=%SPEC_DIR%\%EXE_NAME%.spec"
set "FINAL_OUTPUT_EXE=%PKG_ROOT%\%EXE_NAME%.exe"

:: 依赖项路径 (请确保这些文件路径正确)
set "PYD_PATH=../libs/gs_usb.pyd"
set "USB_DLL_PATH=../libusb/VS2022/MS64/dll/libusb-1.0.dll"
set "ICON_PATH=../LCAN-View.ico"
:: ==========================================

echo ====================================
echo %BASE_NAME% 自动打包脚本 (One-File 模式)
echo ====================================
echo.

:: 初始化环境/清理旧文件
echo [信息] 正在初始化环境...
if exist "%PKG_ROOT%" (
    :: 尝试删除旧的 build/dist，但不删除根目录以防里面有其他重要文件
    if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
    if exist "%PYI_WORK_DIR%" rmdir /s /q "%PYI_WORK_DIR%"
    if exist "%SPEC_FILE%" del /f /q "%SPEC_FILE%"
    if exist "%FINAL_OUTPUT_EXE%" del /f /q "%FINAL_OUTPUT_EXE%"
) else (
    mkdir "%PKG_ROOT%"
)

:: 检查 pyinstaller
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 pyinstaller，正在安装...
    python -m pip install pyinstaller
)

echo [信息] 开始使用 PyInstaller 构建...
echo [信息] 目标: %FINAL_OUTPUT_EXE%
echo.

:: 执行构建
:: 注意: --onefile 模式会将所有内容打包进一个 exe
pyinstaller --onefile ^
    --name "%EXE_NAME%" ^
    --icon="%ICON_PATH%" ^
    --add-binary "%PYD_PATH%;." ^
    --distpath "%DIST_DIR%" ^
    --workpath "%PYI_WORK_DIR%" ^
    --specpath "%SPEC_DIR%" ^
    --clean ^
    up2.py

if errorlevel 1 (
    echo.
    echo [错误] 构建失败！
    pause
    exit /b 1
)

:: 后处理：只保留最终的 EXE
echo.
echo [信息] 正在执行后期清理...

if exist "%DIST_DIR%\%EXE_NAME%.exe" (
    :: 1. 将 exe 移动到 packaging 根目录
    move /y "%DIST_DIR%\%EXE_NAME%.exe" "%FINAL_OUTPUT_EXE%" >nul

    :: 2. 删除临时文件夹和 spec 文件
    if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
    if exist "%PYI_WORK_DIR%" rmdir /s /q "%PYI_WORK_DIR%"
    if exist "%SPEC_FILE%" del /f /q "%SPEC_FILE%"

    echo ====================================
    echo [完成] 打包成功！
    echo 最终文件: %FINAL_OUTPUT_EXE%
    echo 临时构建文件已全部清理。
    echo ====================================
) else (
    echo [错误] 找不到生成的可执行文件！
)

echo.
pause
