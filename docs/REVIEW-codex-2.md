# Финальная проверка Codex — 23.09.2026

Кейс Freedom «Граф денег». Правила ролей, THRESHOLDS и формула приоритета не менялись.

## ТЗ: обязательное выполнено

| Пункт | Подтверждение |
|---|---|
| 7.1: одна команда, менее 300 с | `python -m app.pipeline`; чистый клон: расчёт 4,8 с, весь процесс 9,66 с |
| 7.2: роль каждому | 2 248 gid совпадают с raw; роли, оценки и evidence проверены в сохранённых и свежих CSV |
| 7.3: объяснимые правила | README: 12 веток; все примеры evidence и формула сверены с кодом и CSV |
| 7.4: кластеры | 72 строки; покрытие узлов, суммы n_nodes=2 248 и n_seed=81; гипотезы заполнены |
| 7.5: топ и экран | 50 строк CSV; экран топ-10/схема топ-50, поиск, стрелки, карточки, кластеры и отчёт |

Раздел 9: 444 обрыва не terminal; 19 изолированных seed сохранены; входящие неполны; суммы и количество различаются. Направленность и проекция Louvain оговорены; gid — строки, выдуманных атрибутов и зашитых результатов нет. Роли — гипотезы; интернет нужен только необязательной LLM; масштабирование до миллиона узлов описано в README.

## Коммиты

- `055778e`: автоматический снимок промежуточных plain/валидатора/README; главный экран восстановлен следующим коммитом.
- `7ce0187`: новый главный экран, plain, ранги и полнота; офлайн-снимки.
- `7a68979`: типы сообщений, таймаут/ограничения AI, дробные суммы аномалий, легенда и неизвестные исходящие.
- `371f0d9`: README/запуск; `4d6305b`: демо/схема, учтён `2f17b01`; `8b2c4f2`: удалён неиспользуемый старый код, прежние API сохранены.
- `a005bae`: 429 повторяющихся цепочек, `/api/routes`, карточки; `8969ac2`: .env только текущего проекта.

## Реальные баги: сценарий → исправление

| Файл:строка | Что исправлено |
|---|---|
| scripts/check_outputs.py:55 | Плохой свежий CSV проходил при хорошем saved → проверяются оба набора; 201 символ с пробелом даёт FAIL/exit 1 |
| app/graph.py:60,124 | Равные баллы давали 509 несовпадений рангов → стабильный порядок, 0 расхождений на 2 248 карточках |
| app/graph.py:18 | Отсутствие части out/ ломало API → восстановление при отсутствии любого из пяти файлов |
| app/graph.py:104,124,165 | Пропущены 95 неполных входов; top(-1), путь к себе, материализация всех путей → gaps при B>A, clamp, нет нулевого маршрута, islice(5) |
| app/main.py:15; app/agent.py:186 | Некорректный content ронял mock; служебные роли, долгий API и сырой текст ошибки → валидация, бюджет 25 с, безопасный fallback |
| app/agent.py:27 | Live утверждал организатора и «несколько seed» при 1 → уточнены инструкции; повторный live дал 1 seed и гипотезу |
| app/pipeline.py:126,137,301 | 9 999,50 ₸ выпадали из диапазона; z=2,5 скрывал превышение; кластер 0 утверждал неизвестную активность → точные границы и оговорки |
| web/index.html:93 | Обрыв выглядел как «отправил 0»; легенда не соответствовала кластерной окраске → исходящие неизвестны, легенда переключается |
| app/__init__.py:5 | Чистый вложенный клон подхватывал родительский ключ → явный путь .env текущего checkout; теперь live=false |

## Проверки

Baseline сохранён в `tmp/review-codex-2/baseline`; роли, role_score, priority, evidence, cluster_id и число аномалий всех узлов не изменились.
Чистый клон `8969ac2`: uv venv + requirements, Python 3.12.13, pandas 3.0.6, NetworkX 3.7; 21/21 OK, без .env.
API: health/graph/top/node/clusters/path/report/routes и прежние GET — 200; неправильный chat — 422; неизвестный gid в отчёте не падает.
Live chat: 200, mode=live, node_card, 6,36 с; чистый клон: chat 200/mode=mock; таймаут и ошибки SDK проверены отдельно.
Chrome офлайн 1600×1000 и 1280×1000: главная, три gid и backup, клики, поиск, фильтры, вся сеть, отчёт; 0 неожиданных ошибок/внешних запросов.
Реальный «Пересчитать»: 6,89 с до готового экрана; топ-5, 82 маршрута карточки и 429 по сети сохранились; серверы 8012 остановлены, 8000 не трогали.
Секреты: .env не отслеживается, отсутствует в истории, игнорируется; шаблоны ключей не найдены, hook активен. Данные не исполняются; неиспользуемый df.query удалён.

Реальный вывод `.\.venv\Scripts\python scripts\check_outputs.py` (финальный контроль, exit 0):
```text
OK   full recompute under 300 s (4.04 s)
OK   read generated CSVs and raw parquet (saved + fresh)
OK   nodes_roles: 2248 rows (found 2248)
OK   nodes_roles: unique gid
OK   nodes_roles: gid match raw nodes
OK   nodes_roles: required columns
OK   nodes_roles: no empty required values
OK   nodes_roles: roles in dictionary (invalid 0)
OK   nodes_roles: role_score in [0,1] (invalid 0)
OK   nodes_roles: priority_score in [0,1] (invalid 0)
OK   nodes_roles: evidence 1..200 chars with a digit (invalid 0)
OK   clusters: required columns
OK   clusters: covers every node cluster_id
OK   clusters: sum n_nodes = 2248 (found 2248)
OK   clusters: sum n_seed = 81 (found 81)
OK   top_nodes: at least 20 rows (found 50)
OK   top_nodes: required columns
OK   top_nodes: descending priority
OK   top_nodes: gid in nodes_roles
OK   top_nodes: consecutive rank
OK   depth=4 with out_deg=0: no terminal role (checked 444, invalid 0)
```
Скриншоты просмотрены: `docs/screenshots/main.png`, `coordinator.png`, `anomaly.png`, `truncated.png`, `routes.png`.

## Что осталось и почему

Требуется репетиция команды на проекторе; она не заменяется headless-проверкой. Роли не откалиброваны по ground truth, маршруты не доказывают происхождение денег.
`codex review` не выполнил CLI-ревью: Windows `helper_sandbox_lock_failed`; непосредственное ревью и независимые проверки выполнены.
Автоматическая проверка дважды отклонила удаление временных клонов (`blocked by policy`), в том числе по проверенному полному пути.
Для ручного удаления в `tmp/review-codex-2/`: `clean-install/clone-0f9a8a55`, `clean-final-20260923-153114`, `clean-final-20260923-153133`; логи лежат рядом.
