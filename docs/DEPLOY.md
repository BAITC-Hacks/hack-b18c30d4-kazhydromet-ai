# Общий доступ для команды и жюри

Один сервер Railway раздаёт экран, API и AI-помощника. Посетителям нужен только браузер;
ключ модели хранится на сервере. **Публичного URL пока нет: размещение ещё не выполнено.**
Локальный запуск для жюри описан в [README](../README.md).

## Размещение на Railway

1. Создать сервис из GitHub-репозитория проекта; корень сервиса — корень репозитория.
2. Выбрать **Railpack**. Он читает `.python-version` (Python 3.12), устанавливает
   существующий `requirements.txt` и использует команду из `railpack.json`.
3. В Variables задать `PUBLIC_DEMO=1` и настройки одного провайдера из таблицы ниже.
   Ключ вводить непосредственно в Variables; не добавлять его в Git, HTML или README.
4. В Deploy указать Healthcheck Path **`/api/health`**, timeout **300 секунд**.
   Оставить одну реплику. `PORT` предоставляет Railway автоматически.
5. Выполнить Deploy. После успешного запуска создать адрес через **Networking → Generate Domain**.
6. Открыть адрес с другого компьютера и выполнить проверки ниже.

Команда запуска уже записана в `railpack.json`:

```sh
python -m app.pipeline && exec python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
```

Pipeline создаёт `out/` в корне проекта до старта API; при ошибке сервер не запускается.
Один worker работает без autoreload. Для восстановимых выгрузок отдельный volume не нужен.
Не переносить pipeline в Pre-Deploy: эта стадия работает в другом контейнере и не сохраняет файлы.
`0.0.0.0` используется внутри облачного контейнера. Локальный `run.ps1` по-прежнему слушает `127.0.0.1`.

## Настройки AI

| Переменная | OpenAI | NVIDIA |
| --- | --- | --- |
| `LLM_PROVIDER` | `openai` | `nvidia` |
| Ключ | `OPENAI_API_KEY` — ключ аккаунта | `NVIDIA_API_KEY` — ключ аккаунта |
| Модель | `OPENAI_MODEL=gpt-5-mini` | `NVIDIA_MODEL=nvidia/nemotron-3-super-120b-a12b` |
| Адрес API | штатный OpenAI API | `NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1` |
| Публичное демо | `PUBLIC_DEMO=1` | `PUBLIC_DEMO=1` |

Выбор провайдера явный: сбой NVIDIA не переключает расходы на OpenAI.
Публичный чат допускает 2 одновременных запроса и 20 запросов в минуту на процесс;
история ограничена 24 000 символами. Это ограничения нагрузки, не гарантированный денежный лимит аккаунта.
Без ключа, при ошибке провайдера или таймауте помощник отвечает по локальному графу в режиме `mock`.
`live: true` в `/api/health` означает наличие конфигурации; это **не проверка ключа, баланса или доступа к модели**.
Живой ответ подтверждается запросом к `/api/chat` с `mode: "live"` и вызванным инструментом в `trace`.

## Проверка общего адреса

- `GET /api/health` → HTTP 200, `ok: true`; выбранные `provider` и `model` соответствуют Variables.
- `GET /api/overview` → 2 248 узлов и 81 seed; главная страница, поиск и карточка работают.
- `GET /api/report?top=3` → Markdown; выбранный перечень скачивается в браузере.
- В чате: «Почему у 100000008603629100 такая роль?» → ответ с числами из карточки.
- При `PUBLIC_DEMO=1` запросы `POST /api/recompute`, `POST /api/dataset/upload`
  и `POST /api/dataset/reset` должны возвращать HTTP 403; проверить до передачи ссылки жюри.

**Пока не проверено:** сборка и запуск этого проекта на Railway, публичный адрес и живой вызов NVIDIA.
Windows-проверки не подтверждают установку всех зависимостей на Linux. PyArrow поддерживает Python 3.12
и Linux wheels; результат установки нужно подтвердить логом облачной сборки.

## Официальные источники

- [Railway: FastAPI и публичный адрес](https://docs.railway.com/guides/fastapi).
- [Railpack: Python и requirements.txt](https://railpack.com/languages/python/),
  [формат railpack.json](https://railpack.com/config/file/).
- [Railway: PORT и healthchecks](https://docs.railway.com/deployments/healthchecks),
  [отдельный контейнер Pre-Deploy](https://docs.railway.com/deployments/pre-deploy-command).
- [PyArrow: совместимость и Linux wheels](https://arrow.apache.org/docs/python/install.html).

`railpack.json` — конфигурация сборщика. Не путать с устаревшим `railway.json`:
[Railway больше не подключает Config as Code для новых сервисов](https://docs.railway.com/config-as-code).
