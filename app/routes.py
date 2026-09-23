"""Повторяющиеся цепочки переводов, совместимые по календарным датам.

Совпадение дат допускается: времени внутри дня нет, фактический порядок неизвестен.
Это гипотезы о маршрутах, а не доказательство движения одних и тех же средств.
В пределах одной цепочки каждая транзакция участвует максимум в одной паре.
Между разными цепочками переводы могут повторяться, поэтому результаты неаддитивны.
"""

from collections import defaultdict

import pandas as pd


def find_routes(tx: pd.DataFrame) -> list[dict]:
    """Найти A→B→C с тремя разными gid и минимум двумя совместимыми парами.

    Жадное сопоставление по возрастанию дат максимизирует число пар: для каждого
    входящего выбирается самый ранний ещё не использованный исходящий не раньше
    его даты. `n_tx` и `sum_kzt` каждого звена учитывают все его транзакции;
    `repeats` — только сопоставленные пары. Суммы между звеньями не связываются.
    Исходный DataFrame не изменяется; идентификаторы в результате — строки.
    """
    required = ["src", "dst", "date", "sum_kzt"]
    missing = set(required) - set(tx.columns)
    if missing:
        raise ValueError("Missing transaction columns: " + ", ".join(sorted(missing)))
    if tx.empty:
        return []

    frame = tx[required].copy()
    if frame.isna().any().any():
        raise ValueError("Transaction fields must not be empty")
    frame["src"] = frame["src"].astype(str)
    frame["dst"] = frame["dst"].astype(str)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    frame["sum_kzt"] = pd.to_numeric(frame["sum_kzt"], errors="raise")
    frame = frame.sort_values("date", kind="stable")

    incoming = defaultdict(list)
    outgoing = defaultdict(list)
    for (src, dst), group in frame.groupby(["src", "dst"], sort=True):
        if src == dst or len(group) < 2:
            continue
        leg = {"src": src, "dst": dst, "n_tx": int(len(group)),
               "sum_kzt": float(group["sum_kzt"].sum())}
        transfers = list(group[["date", "sum_kzt"]].itertuples(index=False, name=None))
        incoming[dst].append((leg, transfers))
        outgoing[src].append((leg, transfers))

    routes = []
    for middle in sorted(incoming.keys() & outgoing.keys()):
        for first_leg, receipts in incoming[middle]:
            for second_leg, payments in outgoing[middle]:
                if first_leg["src"] == second_leg["dst"]:
                    continue
                payment_index = 0
                repeats = 0
                same_day_pairs = 0
                examples = []
                for in_date, in_kzt in receipts:
                    while payment_index < len(payments) and payments[payment_index][0] < in_date:
                        payment_index += 1
                    if payment_index == len(payments):
                        break
                    out_date, out_kzt = payments[payment_index]
                    payment_index += 1
                    repeats += 1
                    same_day_pairs += int(in_date == out_date)
                    if len(examples) < 3:
                        examples.append({"in_date": in_date.strftime("%d.%m.%Y"),
                                         "out_date": out_date.strftime("%d.%m.%Y"),
                                         "in_kzt": float(in_kzt), "out_kzt": float(out_kzt)})
                if repeats >= 2:
                    routes.append({"gids": [first_leg["src"], middle, second_leg["dst"]],
                                   "repeats": repeats, "first_leg": first_leg.copy(),
                                   "second_leg": second_leg.copy(), "examples": examples,
                                   "same_day_pairs": same_day_pairs})

    return sorted(routes, key=lambda route: (-route["repeats"], route["gids"]))
