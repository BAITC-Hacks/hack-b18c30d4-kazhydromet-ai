# Ставит задачу Windows: автокоммит раз в час. Запускать один раз, на каждой машине команды.
#   .\scripts\install-autocommit.ps1              # раз в час, обычное сообщение коммита
#   .\scripts\install-autocommit.ps1 -Minutes 30  # каждые 30 минут
#   .\scripts\install-autocommit.ps1 -Codex       # сообщение коммита пишет Codex
#   .\scripts\install-autocommit.ps1 -Remove      # убрать задачу
param([int]$Minutes = 60, [switch]$Codex, [switch]$Remove)

$name = 'HackAlem AutoCommit'
$repo = Split-Path $PSScriptRoot -Parent
$script = Join-Path $PSScriptRoot 'autocommit.ps1'

if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Задача «$name» удалена" -ForegroundColor Green
    return
}

$taskArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -RepoPath `"$repo`""
if ($Codex) { $taskArgs += " -Codex" }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $taskArgs -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes $Minutes) -RepetitionDuration (New-TimeSpan -Days 10)
# На ноутбуке важно: не выключаться от батареи и досылать пропущенный запуск
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force `
    -Description "Автокоммит репозитория хакатона каждые $Minutes минут" | Out-Null

Write-Host "Готово: «$name» каждые $Minutes мин для $repo" -ForegroundColor Green
Write-Host "Проверить сейчас:  Start-ScheduledTask -TaskName '$name'"
Write-Host "Лог:               Get-Content '$repo\.git\autocommit.log' -Tail 20"
Write-Host "Убрать:            .\scripts\install-autocommit.ps1 -Remove"
