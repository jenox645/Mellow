@echo off
chcp 65001 >nul 2>&1
title MellowDLP Setup

rem Locate Python: prefer "python" on PATH, fall back to the "py" launcher
set "PY=python"
where python >nul 2>&1
if errorlevel 1 (
    where py >nul 2>&1
    if errorlevel 1 (
        echo.
        echo  ERROR: Python not found.
        echo  Install from https://python.org and tick "Add python.exe to PATH",
        echo  then run SETUP.bat again from a NEW terminal.
        echo.
        pause
        exit /b 1
    )
    set "PY=py -3"
)

echo.
echo  MellowDLP Builder
echo  -----------------
echo.
echo    [1]  Full installer   (creates dist\MellowDLP_Setup.exe)
echo    [2]  App only         (creates dist\MellowDLP.exe + Desktop shortcut)
echo    [3]  Frontend only    (rebuilds static\ bundle in seconds - for UI dev)
echo    [4]  Run tests        (installs test deps in .venv, runs pytest)
echo.
choice /c 1234 /n /m "  Choose [1/2/3/4]: "
if %errorlevel% == 4 (
    %PY% build_setup.py --run-tests
) else if %errorlevel% == 3 (
    %PY% build_setup.py --frontend-only
) else if %errorlevel% == 2 (
    %PY% build_setup.py --desktop-shortcut
) else (
    %PY% build_setup.py
)
set BUILD_RESULT=%errorlevel%
echo.
if %BUILD_RESULT% == 0 (
    echo  Build complete!
) else (
    echo  Build failed. Scroll up for the first line starting with "ERROR:".
    echo  Tip: if a tool was just installed (Node, esbuild^), open a NEW
    echo  terminal so PATH refreshes, then run SETUP.bat again.
)
echo.
pause
