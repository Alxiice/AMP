@echo off
:: Activate the Python virtual environment for AMP
:: ==============================================

:: Check if venv exists
if not exist "venv\Scripts\activate.bat" (
    echo Error: Virtual environment not found.
    echo Please run: python -m venv venv
    exit /b 1
)

:: Activate the virtual environment
call venv\Scripts\activate.bat

:: Display activation message
echo.
echo Virtual environment activated.
echo.
echo To deactivate, run: deactivate
