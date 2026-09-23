"""Coverage of observed transfers by an analyst's shortlist, without double counting."""

import re

from . import graph


SELECTION_LIMIT = 100


def review_coverage(gids: list[str]) -> dict:
    """Count the union of incident raw transfers and suggest an incremental review."""
    nodes, _, _, _, transactions = graph._state()
    known = set(nodes.index.astype(str))
    selected, unknown, ignored = [], [], []
    seen = set()
    for value in gids:
        gid = str(value).strip()
        if not gid or gid in seen:
            continue
        seen.add(gid)
        if re.fullmatch(r"[0-9]{18}", gid) is None or gid not in known:
            unknown.append(gid)
        elif len(selected) < SELECTION_LIMIT:
            selected.append(gid)
        else:
            ignored.append(gid)

    selected_ids = {int(gid) for gid in selected}
    covered_mask = (transactions["src"].isin(selected_ids)
                    | transactions["dst"].isin(selected_ids))
    covered = transactions.loc[covered_mask]
    counterparties = (set(covered["src"]) | set(covered["dst"])) - selected_ids
    total_transactions = int(len(transactions))
    total_kzt = float(transactions["sum_kzt"].sum())
    n_transactions = int(len(covered))
    sum_kzt = float(covered["sum_kzt"].sum())

    candidates = []
    if len(selected) < SELECTION_LIMIT:
        uncovered = transactions.loc[~covered_mask]
        for card in graph.top(n=50):
            if card["gid"] in selected or card["is_seed"]:
                continue
            candidate_id = int(card["gid"])
            extra = uncovered.loc[(uncovered["src"] == candidate_id)
                                  | (uncovered["dst"] == candidate_id)]
            if extra.empty:
                continue
            candidates.append({
                "gid": card["gid"], "role": card["role"],
                "priority_score": float(card["priority_score"]), "rank": int(card["rank"]),
                "new_transactions": int(len(extra)), "new_kzt": float(extra["sum_kzt"].sum()),
            })
    if selected:
        candidates.sort(key=lambda item: (-item["new_transactions"],
                                          -item["priority_score"], item["gid"]))
    # With an empty shortlist retain the initial global ranking from graph.top.
    next_candidate = candidates[0] if candidates else None
    if next_candidate:
        amount = f"{next_candidate['new_kzt']:,.0f}".replace(",", " ")
        reason = ("Первый доступный клиент в общем рейтинге проверки. " if not selected else
                  "Наибольший прирост числа переводов среди невыбранных клиентов топ-50 "
                  "без исходных seed; при равенстве выше приоритет, затем меньше gid. ")
        next_candidate["why"] = (
            reason + f"Добавит {next_candidate['new_transactions']} ранее неохваченных переводов "
            f"на {amount} ₸. Рекомендация расширяет перечень и не меняет роль или приоритет клиента."
        )

    note = (
        "Учтены только видимые операции, где хотя бы одна сторона входит в перечень. "
        "Каждый перевод считается один раз, даже если выбраны обе стороны. "
        "Это охват данных для проверки, а не объём преступных денег и не эффект блокировки счетов. "
        "Входящие извне, операции ниже 5 000 ₸ и исходящие четвёртого колена могут отсутствовать."
    )
    if ignored:
        note += " Учтены только первые 100 найденных клиентов; остальные перечислены в ignored_gids."
    return {
        "selected_gids": selected, "unknown_gids": unknown, "ignored_gids": ignored,
        "n_selected": int(len(selected)), "n_transactions": n_transactions,
        "n_edges": int(len(covered[["src", "dst"]].drop_duplicates())),
        "n_counterparties": int(len(counterparties)), "sum_kzt": sum_kzt,
        "transactions_share": n_transactions / total_transactions if total_transactions else 0.0,
        "volume_share": sum_kzt / total_kzt if total_kzt else 0.0,
        "total_transactions": total_transactions, "total_kzt": total_kzt,
        "next_candidate": next_candidate, "note": note,
    }
