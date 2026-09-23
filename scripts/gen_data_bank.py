"""Запасные демо-данные: банковские транзакции — на случай, если трек окажется про финансовый рынок,
а не про госуслуги. Запуск: python scripts/gen_data_bank.py

Потом на главной странице нажать «Загрузить CSV или Excel» и выбрать data/transactions.csv —
универсальные инструменты агента (dataset_info, query_data, find_outliers) заработают сразу.
Чтобы под эти данные переписать и специальные инструменты, скажи Codex: «перепиши app/tools.py
под data/transactions.csv по правилам AGENTS.md» — это минут двадцать.
"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)
OUT = Path(__file__).resolve().parent.parent / "data" / "transactions.csv"

CITIES = ["Астана", "Алматы", "Шымкент", "Караганда", "Актобе", "Атырау", "Павлодар", "Усть-Каменогорск"]
MERCHANTS = {
    "Продукты": (["Magnum", "Small", "Galmart", "Анвар"], 2_000, 25_000),
    "Кафе и рестораны": (["Del Papa", "Rumi", "Coffee Boom"], 1_500, 30_000),
    "Транспорт": (["Яндекс Go", "Onay", "InDrive"], 300, 6_000),
    "АЗС": (["Helios", "Qazaq Oil", "Sinooil"], 5_000, 30_000),
    "Коммунальные": (["Астана-ЕРЦ", "Алсеко", "Казахтелеком"], 8_000, 45_000),
    "Маркетплейсы": (["Kaspi Магазин", "Wildberries", "Ozon"], 3_000, 150_000),
    "Переводы": (["Перевод по номеру", "Перевод на карту"], 2_000, 200_000),
    "Здоровье": (["Europharma", "Биосфера", "Invitro"], 1_000, 40_000),
}
CHANNELS = ["Карта", "QR", "Перевод", "Онлайн"]
START = datetime(2026, 4, 1)

rows = []
for i in range(1, 61):
    client = f"C{i:03d}"
    home = random.choice(CITIES)
    level = random.uniform(0.6, 1.8)  # у каждого клиента свой уровень трат
    for _ in range(random.randint(30, 70)):
        cat = random.choice(list(MERCHANTS))
        names, lo, hi = MERCHANTS[cat]
        ts = START + timedelta(days=random.randint(0, 174), hours=random.randint(8, 22), minutes=random.randint(0, 59))
        rows.append([ts, client, round(random.uniform(lo, hi) * level), cat, random.choice(names),
                     home, random.choice(CHANNELS), 0])
    # подозрительные: крупно, ночью, в чужом городе — типичная социальная инженерия
    for _ in range(random.randint(0, 3)):
        ts = START + timedelta(days=random.randint(0, 174), hours=random.randint(1, 4), minutes=random.randint(0, 59))
        rows.append([ts, client, round(random.uniform(300_000, 1_500_000)), "Переводы", "Перевод на карту",
                     random.choice([c for c in CITIES if c != home]), "Онлайн", 1])

rows.sort(key=lambda r: r[0])
OUT.parent.mkdir(exist_ok=True)
with OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["tx_id", "ts", "client_id", "amount_kzt", "category", "merchant", "city", "channel", "is_suspicious"])
    for n, r in enumerate(rows, 1):
        w.writerow([f"T{n:05d}", r[0].strftime("%Y-%m-%d %H:%M"), *r[1:]])

print(f"{len(rows)} транзакций, подозрительных {sum(r[7] for r in rows)} -> {OUT}")
