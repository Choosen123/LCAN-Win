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
set "PKG_ROOT=.packaging"
set "DIST_DIR=%PKG_ROOT%\dist"
set "NUITKA_BUILD_DIR=%PKG_ROOT%\nuitka_build"

echo ====================================
echo LCAN-View 自动打包脚本
echo ====================================
echo.

:: 清理旧文件
echo [信息] 正在清理旧文件...
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
if exist "%NUITKA_BUILD_DIR%" rmdir /s /q "%NUITKA_BUILD_DIR%"
if exist "%PKG_ROOT%\up2.build" rmdir /s /q "%PKG_ROOT%\up2.build"
if exist "%PKG_ROOT%\up2.dist" rmdir /s /q "%PKG_ROOT%\up2.dist"
if exist "%PKG_ROOT%\up2.onefile-build" rmdir /s /q "%PKG_ROOT%\up2.onefile-build"
if not exist "%PKG_ROOT%" mkdir "%PKG_ROOT%"

:: 检查是否安装了nuitka
python -m pip show nuitka >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 nuitka，正在安装...
    python -m pip install nuitka
    if errorlevel 1 (
        echo [错误] 安装 nuitka 失败！
        pause
        exit /b 1
    )
)

:: onefile 推荐依赖（可选）
python -m pip show zstandard >nul 2>&1
if errorlevel 1 (
    echo [信息] 未找到 zstandard，正在安装以提升 onefile 构建体验...
    python -m pip install zstandard >nul 2>&1
)

echo [信息] 开始使用 Nuitka 构建 LCAN-View...
echo [信息] 输出文件名: %EXE_NAME%.exe
echo [信息] 打包目录: %PKG_ROOT%
echo.

:: 执行 Nuitka 构建（含编译级保护/混淆）
python -m nuitka ^
  --standalone ^
  --onefile ^
  --enable-plugin=pyqt6 ^
  --windows-console-mode=disable ^
  --output-dir="%PKG_ROOT%" ^
  --remove-output ^
  --jobs=4 ^
  --assume-yes-for-downloads ^
  --report="%PKG_ROOT%\nuitka-report.xml" ^
  --output-filename="%EXE_NAME%.exe" ^
  --windows-icon-from-ico="LCAN-View.ico" ^
  --follow-imports ^
  up2.py

if errorlevel 1 (
    echo.
    echo [错误] Nuitka 构建失败！
    pause
    exit /b 1
)

echo.
echo ====================================
echo [完成] 打包成功！
echo 可执行文件位于: %DIST_DIR%\%EXE_NAME%.exe
echo ====================================
echo.
pause
