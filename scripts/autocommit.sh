#!/usr/bin/env bash
# Автокоммит для macOS и Linux. Поставить раз в час:
#   crontab -e
#   0 * * * * /полный/путь/к/репо/scripts/autocommit.sh >> /tmp/autocommit.log 2>&1
cd "$(dirname "$0")/.." || exit 1

log() { echo "$(date '+%Y-%m-%d %H:%M:%S')  $*" | tee -a .git/autocommit.log; }

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { log "не git-репозиторий"; exit 1; }
[ -z "$(git status --porcelain)" ] && { log "изменений нет"; exit 0; }

git add -A
git commit -q -m "auto: hourly snapshot ($(whoami))" || { log "коммит не прошёл"; exit 1; }
log "коммит сделан"

if ! git pull --rebase -q; then
  git rebase --abort 2>/dev/null
  log "КОНФЛИКТ при rebase. Коммит сохранён локально, push пропущен"
  exit 1
fi

git push -q || { log "push не прошёл (нет сети?)"; exit 1; }
log "запушено"
