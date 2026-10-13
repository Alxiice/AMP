<#
.SYNOPSIS
    Activates the Python virtual environment for AMP.
.DESCRIPTION
    This script activates the virtual environment located in the ./venv directory.
    Run this from the project root (AMP/).
#>

# Check if venv exists
if (-not (Test-Path -Path "venv\Scripts\Activate.ps1")) {
    Write-Host "Error: Virtual environment not found."
    Write-Host "Please run: python -m venv venv"
    exit 1
}

# Activate the virtual environment
& "venv\Scripts\Activate.ps1"

Write-Host "`nVirtual environment activated."
Write-Host "To deactivate, run: deactivate"
