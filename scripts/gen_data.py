"""Синтетические начисления и выплаты по госуслугам (Казахстан). Запуск: python scripts/gen_data.py

ИИН полностью выдуманные: начинаются с 99, такой серии не существует.
В данные заложены три «истории», которые агент должен найти на демо, — см. data/STORIES.md
"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)
OUT = Path(__file__).resolve().parent.parent / "data" / "payments.csv"

REGIONS = ["Астана", "Алматы", "Шымкент", "Акмолинская", "Актюбинская", "Алматинская", "Атырауская",
           "Восточно-Казахстанская", "Жамбылская", "Карагандинская", "Костанайская", "Кызылординская",
           "Мангистауская", "Павлодарская", "Северо-Казахстанская", "Туркестанская"]

# тип услуги -> (услуги, минимум, максимум, направление денег)
SERVICES = {
    "Налог": (["Налог на транспорт", "Налог на имущество", "Земельный налог", "ИПН индивидуального предпринимателя"],
              5_000, 120_000, "В бюджет"),
    "Пошлина": (["Госпошлина за регистрацию авто", "Пошлина за загранпаспорт", "Пошлина за регистрацию недвижимости"],
                1_500, 30_000, "В бюджет"),
    "Штраф": (["Штраф за превышение скорости", "Штраф за парковку", "Административный штраф"],
              10_000, 100_000, "В бюджет"),
    "Пособие": (["Пособие по уходу за ребёнком", "Адресная социальная помощь", "Пособие по инвалидности"],
                25_000, 150_000, "Из бюджета"),
    "Субсидия": (["Жилищная помощь", "Субсидия на коммунальные услуги", "Агросубсидия"],
                 30_000, 400_000, "Из бюджета"),
}
CHANNELS = ["eGov", "ЦОН", "Банк", "Мобильное приложение"]
PAY_STATUS = ["Оплачено", "Оплачено", "Оплачено", "Ожидает оплаты", "Просрочено"]
APP_STATUS = ["Назначено", "Назначено", "На рассмотрении", "Отказано"]
START = datetime(2026, 4, 1)

rows = []


def add(iin, region, stype, service, amount, channel, status, overdue, flag=""):
    ts = START + timedelta(days=random.randint(0, 174))
    rows.append([ts, iin, region, stype, service, amount, channel, status, overdue,
                 1 if flag else 0, flag, SERVICES[stype][3]])


for i in range(1, 121):
    iin = f"99{i:04d}30{i:04d}"
    region = random.choice(REGIONS)
    for _ in range(random.randint(4, 12)):
        stype = random.choice(list(SERVICES))
        services, lo, hi, _ = SERVICES[stype]
        status = random.choice(PAY_STATUS if stype in ("Налог", "Пошлина", "Штраф") else APP_STATUS)
        overdue = random.randint(5, 240) if status == "Просрочено" else 0
        add(iin, region, stype, random.choice(services), round(random.uniform(lo, hi)),
            random.choice(CHANNELS), status, overdue)

# История 1: дубли выплат — одно пособие назначено дважды одному человеку
for i in (7, 23, 41, 58):
    iin = f"99{i:04d}30{i:04d}"
    amount = round(random.uniform(60_000, 90_000))
    for _ in range(2):
        add(iin, "Туркестанская", "Пособие", "Пособие по уходу за ребёнком", amount,
            "ЦОН", "Назначено", 0, "Дубль выплаты: то же пособие назначено дважды")

# История 2: хроническая просрочка с крупной суммой
for i in (12, 33, 77):
    add(f"99{i:04d}30{i:04d}", "Алматы", "Налог", "Налог на имущество", round(random.uniform(300_000, 900_000)),
        "eGov", "Просрочено", random.randint(200, 400), "Просрочка больше 200 дней и крупная сумма")

# История 3: в одном регионе аномально много отказов по субсидиям
for i in range(80, 100):
    add(f"99{i:04d}30{i:04d}", "Кызылординская", "Субсидия", "Жилищная помощь",
        round(random.uniform(40_000, 120_000)), "ЦОН", "Отказано", 0,
        "Отказ по субсидии: в регионе доля отказов заметно выше средней")

rows.sort(key=lambda r: r[0])
OUT.parent.mkdir(exist_ok=True)
with OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["doc_id", "date", "iin", "region", "service_type", "service", "amount_kzt",
                "channel", "status", "days_overdue", "is_flagged", "flag_reason", "direction"])
    for n, r in enumerate(rows, 1):
        w.writerow([f"D{n:05d}", r[0].strftime("%Y-%m-%d"), *r[1:]])

flagged = sum(1 for r in rows if r[9])
print(f"{len(rows)} записей, из них помечено {flagged} -> {OUT}")
