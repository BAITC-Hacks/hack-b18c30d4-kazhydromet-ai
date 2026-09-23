"""Markdown report for an AML analyst's review and follow-up requests."""

import argparse
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
    return " ".join(str(value).split()).replace("|", "\\|")


def _role(card: dict) -> str:
    return ROLE_HYPOTHESES.get(card["role"], f"возможная роль: {card['role_ru']}")


def _counterpart_table(rows: list[dict]) -> str:
    if not rows:
        return "В пределах выгрузки переводов нет."
    lines = ["| gid | Роль (гипотеза) | Сумма | Переводов |",
             "|---|---|---:|---:|"]
    for row in rows[:5]:
        lines.append(f"| `{row['gid']}` | {_role(row)} | {_kzt(row['sum_kzt'])} | {int(row['n_tx'])} |")
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
    fast_share = (_score(100 * metrics["fast_share"], 1) + " %" if metrics["out_kzt"] else
                  "— (нет видимых исходящих)")
    gaps = card["gaps"]
    gap_text = ("\n".join(f"- {item}" for item in gaps) if gaps else
                "По правилам полноты точечный пробел не выявлен; для подтверждения гипотезы нужна полная выписка.")
    return "\n".join([
        f"## Узел `{card['gid']}`",
        "",
        f"- **Гипотеза о роли:** {_role(card)} (`{card['role']}`).",
        f"- **Место в рейтинге:** №{int(card['rank'])}.",
        f"- **Приоритет (`priority_score`):** {_score(card['priority_score'])} из 1.",
        f"- **Сила правила (`role_score`):** {_score(card['role_score'], 2)} из 1; это не вероятность виновности.",
        f"- **Основание гипотезы:** {card['evidence']}",
        f"- **Период активности:** {period}.",
        "",
        "### Метрики",
        "",
        "| Показатель | Значение |",
        "|---|---:|",
        f"| Разных плательщиков (`in_deg`) | {int(metrics['in_deg'])} |",
        f"| Разных получателей (`out_deg`) | {int(metrics['out_deg'])} |",
        f"| Видимые входящие (`in_kzt`) | {_kzt(metrics['in_kzt'])} |",
        f"| Видимые исходящие (`out_kzt`) | {_kzt(metrics['out_kzt'])} |",
        f"| Доля исходящей суммы за ≤2 дня после поступления (`fast_share`) | {fast_share} |",
        f"| Циклы до 6 шагов (`cycles`) | {int(metrics['cycles'])} |",
        f"| Seed в двух шагах выше (`seeds_2hop`) | {int(metrics['seeds_2hop'])} |",
        "",
        "### 5 крупнейших плательщиков",
        "",
        _counterpart_table(card["in"]),
        "",
        "### 5 крупнейших получателей",
        "",
        _counterpart_table(card["out"]),
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
    rows = ["| Ранг | gid | Роль (гипотеза) | Приоритет | Краткое обоснование |",
            "|---:|---|---|---:|---|"]
    for requested_gid, card in cards:
        if "error" in card:
            rows.append(f"| — | `{_cell(requested_gid).replace('`', '')}` | не найден | — | Нет в выгрузке |")
            continue
        evidence = " ".join(card["evidence"].split())
        short = evidence if len(evidence) <= 140 else evidence[:137].rstrip() + "…"
        rows.append(f"| {int(card['rank'])} | `{card['gid']}` | {_role(card)} | "
                    f"{_score(card['priority_score'])} | {_cell(short)} |")
    if not cards:
        rows.append("| — | — | — | — | Перечень пуст |")

    known_gids = [card["gid"] for _, card in cards if "error" not in card]
    request_ids = ", ".join(f"`{gid}`" for gid in known_gids) or "—"
    sections = [
        "# Перечень клиентов для углублённой проверки",
        (f"**Сформировано:** {datetime.now().strftime('%d.%m.%Y')}.  "
         f"**Источник:** обезличенная выгрузка внутрибанковских переводов за июль 2026 года; "
         f"{total:,} узлов.".replace(",", " ")),
        "## Методика\n\n"
        f"1. От исходного списка {seeds} gid прослежены исходящие переводы на четыре колена.\n"
        "2. Роли — гипотезы по связям, суммам и времени переводов; приоритет — относительный балл 0–1.\n"
        "3. Пороговые правила, формула и ограничения описаны в [README](../README.md).",
        "## Перечень для проверки\n\n" + "\n".join(rows),
    ]
    sections.extend(node_section(gid) for gid, _ in cards)
    sections.extend([
        "## Следующее действие аналитика\n\n"
        f"Передать перечень {request_ids} в подразделение финансового мониторинга для углублённой проверки. "
        "В запросе в правоохранительные органы указать эти gid и попросить проверить возможные связи "
        "с исходным списком; в банке запросить недостающие сведения, перечисленные в карточках.",
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
