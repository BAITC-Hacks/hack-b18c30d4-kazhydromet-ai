# docs

Материалы команды, не код:

- `PLAN.md` — разбор задания и план на 5 часов (создаётся скиллом `hackalem-kickoff`)
- `PITCH.md` — текст питча, структура слайдов, ответы на вопросы жюри (скилл `hackalem-pitch`)
- скриншоты и видео-бэкап демо

## Codex: лимиты

Если Codex отвечает «You've hit your usage limit» — переключите его на API-ключ хакатона,
тогда он тратит выданные кредиты, а не лимит вашего ChatGPT-аккаунта:

```powershell
"sk-ВАШ-КЛЮЧ" | codex login --with-api-key
codex login status
```

Вернуться на обычный аккаунт потом: `codex login`.

## Автокоммит

Раз в час изменения коммитятся и пушатся сами. Поставить у себя:

```powershell
.\scripts\install-autocommit.ps1          # раз в час
.\scripts\install-autocommit.ps1 -Remove  # убрать после хакатона
Get-Content .git\autocommit.log -Tail 20  # что происходило
```

macOS и Linux: `crontab -e`, строка `0 * * * * /путь/к/репо/scripts/autocommit.sh`

Флаг `-Codex` заставляет Codex писать осмысленное сообщение коммита, но тратит лимит Codex.
На хакатоне лучше без него.
