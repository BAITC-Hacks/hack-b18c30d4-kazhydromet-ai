# Автокоммит: коммитит и пушит изменения. Запускается по расписанию раз в час.
# Вручную:  .\scripts\autocommit.ps1
# С сообщением от Codex: .\scripts\autocommit.ps1 -Codex
# ErrorActionPreference не ставим в Stop: git пишет обычный вывод в stderr.
param(
    [string]$RepoPath = (Split-Path $PSScriptRoot -Parent),
    [switch]$Codex
)

Set-Location $RepoPath
$log = Join-Path $RepoPath '.git\autocommit.log'
function Log($m) {
    $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding utf8
}

git rev-parse --is-inside-work-tree *>$null
if ($LASTEXITCODE) { Log "не git-репозиторий: $RepoPath"; exit 1 }

if (-not (git status --porcelain)) { Log "изменений нет"; exit 0 }

git add -A
$msg = "auto: hourly snapshot ($env:USERNAME)"

if ($Codex) {
    # Спрашиваем у Codex одну строку описания. Если не ответил за 2 минуты - берём обычное сообщение.
    $stat = (git diff --cached --stat | Out-String)
    if ($stat.Length -gt 2000) { $stat = $stat.Substring(0, 2000) }
    $tmp = [IO.Path]::GetTempFileName()
    $in = [IO.Path]::GetTempFileName()
    # Промпт отдаём через stdin: иначе PowerShell разобьёт его на отдельные аргументы
    @"
Вот git diff --stat перед коммитом:
$stat
Напиши ОДНУ строку commit message на английском, до 60 символов, повелительное наклонение.
Ответь только этой строкой, без пояснений и кавычек.
"@ | Set-Content $in -Encoding utf8
    try {
        $p = Start-Process 'codex.cmd' -ArgumentList @('exec', '-s', 'read-only', '-') `
            -NoNewWindow -PassThru -RedirectStandardInput $in -RedirectStandardOutput $tmp -WorkingDirectory $RepoPath
        if ($p.WaitForExit(120000)) {
            $line = (Get-Content $tmp -Encoding utf8 | Where-Object { $_.Trim() } | Select-Object -Last 1)
            if ($line -and $line.Trim().Length -lt 80) { $msg = "auto: " + $line.Trim() }
        } else {
            $p.Kill()
            Log "Codex не ответил за 2 минуты, беру обычное сообщение"
        }
    } catch {
        Log "Codex недоступен: $($_.Exception.Message)"
    }
    Remove-Item $tmp, $in -ErrorAction SilentlyContinue
}

git commit -q -m $msg
if ($LASTEXITCODE) { Log "коммит не прошёл"; exit 1 }
Log "коммит: $msg"

git pull --rebase -q
if ($LASTEXITCODE) {
    git rebase --abort *>$null
    Log "КОНФЛИКТ при rebase. Коммит сохранён локально, push пропущен — разрулите руками"
    exit 1
}

git push -q
if ($LASTEXITCODE) { Log "push не прошёл (нет сети?). Коммит остался локально"; exit 1 }
Log "запушено"
