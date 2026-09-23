"""Markdown report for an AML analyst's review and follow-up requests."""

import argparse
import html
from datetime import datetime
from pathlib import Path

from . import graph


ROLE_HYPOTHESES = {
    "coordinator": "кандидат в организаторы",
    "consolidator": "признаки консолидации",
    "distributor": "признаки распределения",
    "transit": "признаки транзита",
    "terminal": "возможный конечный получатель",
    "peripheral": "периферия; выраженная роль не выявлена",
}


def _kzt(value: float) -> str:
    return f"{float(value):,.0f}".replace(",", " ") + " ₸"


def _score(value: float, digits: int = 4) -> str:
    return f"{float(value):.{digits}f}".replace(".", ",")


def _cell(value: str) -> str:
    return html.escape(" ".join(str(value).split()), quote=False).replace("|", "\\|")


def _role(card: dict) -> str:
    return ROLE_HYPOTHESES.get(card["role"], f"возможная роль: {card['role_ru']}")


def _flow_summary(card: dict) -> str:
    metrics = card["metrics"]
    incoming = f"Входящие: {_kzt(metrics['in_kzt'])}; плательщиков: {int(metrics['in_deg'])}."
    outgoing = ("Исходящие не наблюдаются: обрыв выгрузки." if metrics["truncated"] else
                f"Исходящие: {_kzt(metrics['out_kzt'])}; получателей: {int(metrics['out_deg'])}.")
    return incoming + " " + outgoing


def _counterpart_table(rows: list[dict]) -> str:
    if not rows:
        return "В пределах выгрузки переводов нет."
    lines = ["| Клиент (gid) | Роль (гипотеза) | Сумма | Переводов |",
             "|---|---|---:|---:|"]
    for row in rows[:5]:
        lines.append(f"| `{row['gid']}` | {_role(row)} | {_kzt(row['sum_kzt'])} | {int(row['n_tx'])} |")
    return "\n".join(lines)


def _routes_section(card: dict) -> str:
    routes = card.get("repeated_routes", [])[:3]
    lines = ["### Повторяющиеся маршруты", ""]
    if not routes:
        lines.append("В карточке повторяющиеся цепочки не найдены; это не исключает связей за пределами выгрузки.")
    else:
        lines.append(f"В карточке найдено цепочек: **{int(card['repeated_routes_count'])}**; "
                     f"ниже первые **{len(routes)}** по числу совместимых пар переводов.")
        for index, route in enumerate(routes, 1):
            path = " → ".join(f"`{gid}`" for gid in route["gids"])
            lines.extend([
                "",
                f"**{index}. {path}**",
                "",
                f"Совместимых по датам пар: **{int(route['repeats'])}**; "
                f"из них с совпадающими датами: **{int(route['same_day_pairs'])}**.",
            ])
            if route["examples"]:
                example = route["examples"][0]
                lines.append(f"Пример пары: первое звено — {example['in_date']}, {_kzt(example['in_kzt'])}; "
                             f"второе звено — {example['out_date']}, {_kzt(example['out_kzt'])}.")
    lines.extend(["", "Даты переводов в паре не убывают; порядок операций внутри одного дня неизвестен. "
                  "Внутри одной цепочки каждая операция участвует не более чем в одной паре. "
                  "Суммы между шагами не сопоставляются: совместимость дат не доказывает происхождение "
                  "и движение одних и тех же средств. Разные цепочки могут включать те же операции; "
                  "суммы цепочек складывать нельзя."])
    return "\n".join(lines)


def _node_section(card: dict, requested_gid: str) -> str:
    if "error" in card:
        safe_gid = _cell(requested_gid).replace("`", "")
        return f"## Узел `{safe_gid}` — не найден\n\nНет данных для карточки: {_cell(card['error'])}."

    metrics = card["metrics"]
    first, last = card["first_date"], card["last_date"]
    period = first if first == last else f"{first} — {last}"
    if first is None:
        period = "в выгрузке нет переводов"
    truncated = bool(metrics["truncated"])
    out_count = "Не наблюдаются: обрыв выгрузки" if truncated else str(int(metrics["out_deg"]))
    out_amount = "Не наблюдаются: обрыв выгрузки" if truncated else _kzt(metrics["out_kzt"])
    if truncated:
        fast_share = "Не оценивается: обрыв выгрузки"
        recipients = "Исходящие переводы и получатели не наблюдаются: обрыв выгрузки на четвёртом колене."
    else:
        fast_share = (_score(100 * metrics["fast_share"], 1) + " %" if metrics["out_kzt"] else
                      "— (нет видимых исходящих)")
        recipients = _counterpart_table(card["out"])
    anomaly_count = int(metrics.get("anomaly_count", 0))
    anomaly_flags = metrics.get("anomaly_flags", "нет")
    if isinstance(anomaly_flags, list):
        anomaly_flags = "; ".join(str(flag) for flag in anomaly_flags)
    anomaly_text = (f"Сработало флагов: **{anomaly_count}**. {_cell(anomaly_flags)}."
                    if anomaly_count else "По применённым правилам флаги аномалий не выявлены.")
    gaps = card["gaps"]
    gap_text = ("\n".join(f"- {item}" for item in gaps) if gaps else
                "По правилам полноты точечный пробел не выявлен; для подтверждения гипотезы нужна полная выписка.")
    return "\n".join([
        f"## Узел `{card['gid']}`",
        "",
        f"- **Гипотеза о роли:** {_role(card)}.",
        f"- **Место в рейтинге:** №{int(card['rank'])}.",
        f"- **Наблюдаемые потоки:** {_flow_summary(card)}",
        f"- **Период активности:** {period}.",
        "",
        "### Метрики",
        "",
        "| Показатель | Значение |",
        "|---|---:|",
        f"| Роль в выгрузке (`role`) | `{card['role']}` |",
        f"| Основание правила (`evidence`) | {_cell(card['evidence'])} |",
        f"| Приоритет проверки (`priority_score`) | {_score(card['priority_score'])} из 1 |",
        f"| Сила правила роли (`role_score`) | {_score(card['role_score'])} из 1 |",
        f"| Разных плательщиков (`in_deg`) | {int(metrics['in_deg'])} |",
        f"| Разных получателей (`out_deg`) | {out_count} |",
        f"| Видимые входящие (`in_kzt`) | {_kzt(metrics['in_kzt'])} |",
        f"| Видимые исходящие (`out_kzt`) | {out_amount} |",
        f"| Доля исходящей суммы за ≤2 дня после поступления (`fast_share`) | {fast_share} |",
        f"| Циклы до 6 шагов (`cycles`) | {int(metrics['cycles'])} |",
        f"| Известных клиентов в двух шагах выше по потоку (`seeds_2hop`) | {int(metrics['seeds_2hop'])} |",
        f"| Флагов аномалий (`anomaly_count`) | {anomaly_count} |",
        "",
        "Баллы показывают силу правила и относительный приоритет проверки, а не вероятность виновности. "
        "Близость дат поступления и отправки не доказывает передачу именно полученных средств.",
        "",
        "### 5 крупнейших плательщиков",
        "",
        _counterpart_table(card["in"]),
        "",
        "### 5 крупнейших получателей",
        "",
        recipients,
        "",
        "### Наблюдаемые признаки аномалий",
        "",
        anomaly_text,
        "Флаги указывают на необычные операции в этой выборке. Они не меняют роль и приоритет "
        "и не подтверждают нарушение; отсутствие флагов также не исключает его.",
        "",
        _routes_section(card),
        "",
        "### Чего не хватает и что запросить",
        "",
        gap_text,
    ])


def node_section(gid: str) -> str:
    """Build one Markdown node card from graph.node_card, including missing-data requests."""
    return _node_section(graph.node_card(gid, limit=5), str(gid))


def build_report(gids: list[str] | None = None, top: int = 10) -> str:
    """Build a ranked review list with node cards and explicit data limitations."""
    if gids is None:
        selected = [row["gid"] for row in graph.top(max(0, top))]
    else:
        selected = list(dict.fromkeys(str(gid).strip() for gid in gids if str(gid).strip()))
        if not selected:
            graph.top(0)  # Initialize outputs for the overview, even with an empty list.

    cards = [(gid, graph.node_card(gid, limit=5)) for gid in selected]
    cards.sort(key=lambda item: ("error" in item[1], item[1].get("rank", float("inf"))))
    overview = graph.overview()
    total, seeds = int(overview["nodes"]), int(overview["seeds"])
    rows = ["| Ранг | Клиент (gid) | Роль (гипотеза) | Приоритет | Краткое обоснование |",
            "|---:|---|---|---:|---|"]
    for requested_gid, card in cards:
        if "error" in card:
            rows.append(f"| — | `{_cell(requested_gid).replace('`', '')}` | не найден | — | Нет в выгрузке |")
            continue
        rows.append(f"| {int(card['rank'])} | `{card['gid']}` | {_role(card)} | "
                    f"{_score(card['priority_score'])} | {_cell(_flow_summary(card))} |")
    if not cards:
        rows.append("| — | — | — | — | Перечень пуст |")

    known_gids = [card["gid"] for _, card in cards if "error" not in card]
    known_cards = [card for _, card in cards if "error" not in card]
    if known_cards:
        first_card = known_cards[0]
        summary = (f"Выбрано клиентов: **{len(cards)}**; найдены в выгрузке: **{len(known_cards)}**; "
                   f"не найдены: **{len(cards) - len(known_cards)}**.\n\n"
                   f"Первым среди выбранных проверить `{first_card['gid']}` "
                   f"(№{int(first_card['rank'])} в общем рейтинге; {_role(first_card)}). "
                   "Основания приведены в перечне и карточках ниже.\n\n"
                   f"С флагами аномалий: **{sum(int(c['metrics'].get('anomaly_count', 0)) > 0 for c in known_cards)}**; "
                   f"с обрывом исходящих на четвёртом колене: **{sum(bool(c['metrics']['truncated']) for c in known_cards)}**. "
                   "Окончательное решение о проверке принимает аналитик.")
    else:
        summary = ("Введённые идентификаторы не найдены в выгрузке. Проверьте их и сформируйте перечень заново."
                   if cards else "Клиенты для проверки не выбраны. Укажите идентификаторы или число первых клиентов.")
    sections = [
        "# Перечень клиентов для углублённой проверки",
        (f"**Сформировано:** {datetime.now().strftime('%d.%m.%Y')}.  "
         f"**Источник:** обезличенная выгрузка внутрибанковских переводов за июль 2026 года; "
         f"{total:,} узлов.".replace(",", " ")),
        "## Краткая сводка\n\n" + summary,
        "## Методика\n\n"
        f"1. От исходного списка из {seeds} клиентов прослежены исходящие переводы на четыре колена. "
        "В таблицах gid — обезличенный идентификатор, seed — клиент из исходного списка.\n"
        "2. Роли — гипотезы по связям, суммам и времени переводов; приоритет — относительный балл 0–1.\n"
        "3. Пороговые правила, формула и ограничения описаны в [README](../README.md).",
        "## Перечень для проверки\n\n" + "\n".join(rows),
    ]
    sections.extend(_node_section(card, gid) for gid, card in cards)
    if known_gids:
        request_ids = ", ".join(f"`{gid}`" for gid in known_gids)
        next_action = (
            "### Запросы внутри банка\n\n"
            f"Передать аналитикам финансового мониторинга перечень {request_ids} с основаниями проверки. "
            "Сопоставить видимые операции с полной выпиской за июль 2026 года, включая входящие "
            "из-за пределов выборки, операции ниже порога и исходящие четвёртого колена. "
            "Запросить доступные банку сведения о назначениях платежей и об источниках средств; "
            "при синхронных поступлениях — доступные данные об устройствах и IP. "
            "Конкретные пробелы перечислены в карточках; этих сведений в исходной выгрузке нет.\n\n"
            "### Проверка возможных связей через правоохранительные органы\n\n"
            "Если уполномоченный сотрудник банка решит направить запрос, обозначить вопрос: "
            "подтверждаются ли возможные связи выбранных клиентов с исходным списком и участниками "
            "показанных цепочек? Приложить наблюдаемые переводы, даты и ограничения анализа. "
            "Идентификаторы gid в этом отчёте обезличены; личности и факт противоправной деятельности "
            "из них не устанавливаются. Отчёт не формирует и не отправляет такой запрос автоматически."
        )
    else:
        next_action = ("Сначала сформировать непустой перечень клиентов, найденных в выгрузке. "
                       "Оснований готовить запрос по текущему перечню нет.")
    sections.extend([
        "## Следующее действие аналитика\n\n" + next_action,
        "## Ограничения\n\n"
        "- Выборка построена прослеживанием исходящих переводов; входящие из-за её пределов неполны.\n"
        "- Переводы менее 5 000 ₸ отсутствуют.\n"
        "- На 4-м колене обход обрывается: отсутствие исходящих не означает удержания денег.\n"
        "- Роли и приоритеты — гипотезы для проверки, не доказательство вины.",
    ])
    return "\n\n".join(sections) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Сформировать Markdown-отчёт по графу переводов")
    parser.add_argument("--top", type=int, default=10, help="Число первых узлов по приоритету")
    parser.add_argument("--gids", help="Список gid через запятую вместо топа")
    parser.add_argument("--out", type=Path, default=Path("out/report.md"), help="Путь к Markdown-файлу")
    args = parser.parse_args()
    gids = args.gids.split(",") if args.gids is not None else None
    markdown = build_report(gids=gids, top=args.top)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")
    print(f"Сохранён отчёт: {args.out}")


if __name__ == "__main__":
    main()
