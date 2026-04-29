@echo off
chcp 65001 >nul 2>&1
title MellowDLP Setup

echo.
echo  MellowDLP Builder
echo  -----------------
echo.
echo    [1]  Full installer   (creates dist\MellowDLP_Setup.exe)
echo    [2]  App only         (creates dist\MellowDLP.exe + Desktop shortcut)
echo.
choice /c 12 /n /m "  Choose [1/2]: "
if %errorlevel% == 2 (
    python build_setup.py --desktop-shortcut
) else (
    python build_setup.py
)
set BUILD_RESULT=%errorlevel%
echo.
if %BUILD_RESULT% == 0 (
    echo  Build complete!
) else (
    echo  Build failed. Check errors above.
)
echo.
pause
