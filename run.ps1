# Запуск: .\run.ps1   -> http://localhost:8000
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Создан .env - впиши OPENAI_API_KEY" -ForegroundColor Yellow }
if (-not (Test-Path data\transactions.csv)) { .\.venv\Scripts\python scripts\gen_data.py }
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
