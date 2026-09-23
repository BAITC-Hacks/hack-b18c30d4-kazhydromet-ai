# Узнать, что происходит у команды: подтянуть изменения и показать, кто что делал.
# Запуск:  .\scripts\sync.ps1       (за последние 2 часа)
#          .\scripts\sync.ps1 -Hours 8
param([int]$Hours = 2)

Set-Location (Split-Path $PSScriptRoot -Parent)

git pull --rebase
if ($LASTEXITCODE) {
    git rebase --abort *>$null
    Write-Host "`nКОНФЛИКТ: твои правки разошлись с чужими. Позови того, кто трогал те же файлы." -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Статус команды ===" -ForegroundColor Cyan
Get-Content docs\STATUS.md -Encoding utf8 | Select-Object -First 16

Write-Host "`n=== Коммиты за последние $Hours ч ===" -ForegroundColor Cyan
$log = git log --since="$Hours hours ago" --pretty=format:"%h  %an  %ar  %s"
if ($log) { $log } else { "пусто" }

Write-Host "`n=== Какие файлы меняли ===" -ForegroundColor Cyan
$files = git log --since="$Hours hours ago" --name-only --pretty=format:"" | Where-Object { $_.Trim() } | Sort-Object -Unique
if ($files) { $files } else { "пусто" }

Write-Host "`nНе забудь обновить свою строку в docs/STATUS.md" -ForegroundColor Yellow
