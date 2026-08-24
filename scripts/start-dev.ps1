$ErrorActionPreference = 'Stop'
if (!(Test-Path '.venv')) { python -m venv .venv }
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
if (Test-Path 'requirements.txt') { pip install -r requirements.txt }
python manage.py check
python manage.py migrate
python manage.py runserver
