@echo off
rem Opens Gota from the source code, using the Python environment that lives in .venv
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" main.py
