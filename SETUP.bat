@echo off
chcp 65001 >nul 2>&1
title MellowDLP Setup
python build_setup.py
if %errorlevel% neq 0 pause
