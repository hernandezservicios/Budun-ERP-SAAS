$ErrorActionPreference = 'Stop'
if (Test-Path '.venv\Scripts\Activate.ps1') { . .\.venv\Scripts\Activate.ps1 }
python manage.py check
