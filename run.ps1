# Запуск: .\run.ps1 -> пересчёт и http://127.0.0.1:8000
param([ValidateRange(1, 65535)][int]$Port = 8000)

Set-Location -LiteralPath $PSScriptRoot -ErrorAction Stop
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Write-Error 'Нет локального Python. Выполните uv venv .venv и uv pip install --python .venv\Scripts\python.exe -r requirements.txt'
    exit 1
}

& $python -m app.pipeline
if ($LASTEXITCODE -ne 0) {
    Write-Error 'Пересчёт не завершён. Исправьте ошибку выше и повторите запуск.'
    exit 1
}

# 127.0.0.1 - сервер виден только с этого ноутбука (в сети хакатона много чужих устройств)
& $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
