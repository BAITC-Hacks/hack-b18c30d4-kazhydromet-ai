"""AI-агент на OpenAI Agents SDK. Новый инструмент = функция в tools.py + обёртка @function_tool здесь."""
import json
import os

from agents import Agent, Runner, function_tool

from . import dataset, tools

MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

INSTRUCTIONS = """Ты — AI-помощник по финансовым госуслугам Казахстана: налоги, пошлины, штрафы,
пособия и субсидии. Помогаешь сотруднику госоргана проверять начисления и выплаты, а гражданину —
понимать, что ему начислено или положено.
Правила:
- Любые цифры бери только из инструментов, ничего не выдумывай.
- Если вопрос про загруженные данные или ты не знаешь, какие колонки есть, — СНАЧАЛА вызови dataset_info,
  и только потом query_data. Не угадывай названия колонок.
- Пиши простым языком, без канцелярита. Вместо «отказано в связи с несоответствием» — «не хватает такого-то
  документа, вот что сделать».
- Объясняй, на чём основан вывод: какая запись, какая сумма, какое правило.
- Отвечай на языке пользователя (русский, казахский или английский).
- Суммы в тенге с разделителями тысяч: 1 250 000 ₸. Даты в формате ДД.ММ.ГГГГ.
- Коротко: 3-6 предложений или список. В конце — одно конкретное действие, что сделать дальше.
- Решения по отказам и спорным случаям принимает человек. Ты готовишь и обосновываешь."""


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False)


@function_tool
def get_summary() -> str:
    """Общая сводка: сколько начислений и выплат, граждан, просрочек, сумм в бюджет и из бюджета,
    разбивка по типам услуг."""
    return _j(tools.summary())


@function_tool
def find_anomalies(limit: int = 10) -> str:
    """Записи, требующие проверки: дубли выплат, длинные просрочки, необычные отказы. У каждой указана причина.

    Args:
        limit: Сколько записей вернуть.
    """
    return _j(tools.find_anomalies(limit))


@function_tool
def citizen_profile(iin: str) -> str:
    """Всё по одному человеку: начисления, выплаты, просрочки и спорные записи.

    Args:
        iin: ИИН из 12 цифр, например 990007300007.
    """
    return _j(tools.citizen_profile(iin))


@function_tool
def search_payments(service_type: str | None = None, region: str | None = None, status: str | None = None,
                    min_amount: int = 0, limit: int = 20) -> str:
    """Поиск начислений и выплат (самые крупные первыми).

    Args:
        service_type: Налог, Пошлина, Штраф, Пособие или Субсидия.
        region: Регион, например "Алматы" или "Туркестанская".
        status: Оплачено, Просрочено, Ожидает оплаты, Назначено, Отказано, На рассмотрении.
        min_amount: Минимальная сумма в тенге.
        limit: Сколько вернуть.
    """
    return _j(tools.search_payments(service_type, region, status, min_amount, limit))


@function_tool
def refusal_rates() -> str:
    """Доля отказов по выплатам в разрезе регионов: где людям отказывают чаще всего."""
    return _j(tools.refusal_rates())


@function_tool
def dataset_info() -> str:
    """Что за данные сейчас загружены: имя файла, число строк, список колонок с типами и примерами значений.
    Вызывай первым, если не уверен в структуре данных."""
    return _j(dataset.info())


@function_tool
def query_data(where: str | None = None, group_by: str | None = None, value_column: str | None = None,
               agg: str = "sum", order_desc: bool = True, limit: int = 20) -> str:
    """Универсальный запрос к активным данным: фильтр, группировка, агрегат. Работает с любым датасетом.

    Args:
        where: Условие в синтаксисе pandas, например `amount_kzt > 100000 and region == "Алматы"`.
        group_by: Колонка для группировки.
        value_column: Числовая колонка для агрегата. Без неё считается количество строк.
        agg: sum, mean, count, min, max, median или nunique.
        order_desc: Сортировать по убыванию.
        limit: Сколько строк вернуть.
    """
    return _j(dataset.query(where, group_by, value_column, agg, order_desc, limit))


@function_tool
def find_outliers(value_column: str, group_column: str | None = None, z: float = 3.0, limit: int = 10) -> str:
    """Выбросы в любой числовой колонке по z-score. Работает с любым датасетом.

    Args:
        value_column: Числовая колонка, например сумма.
        group_column: Считать отклонение внутри группы, например по региону.
        z: Порог, обычно 2.5-4.
        limit: Сколько вернуть.
    """
    return _j(dataset.outliers(value_column, group_column, z, limit))


agent = Agent(
    name="GovFinAssistant",
    instructions=INSTRUCTIONS,
    tools=[get_summary, find_anomalies, citizen_profile, search_payments, refusal_rates,
           dataset_info, query_data, find_outliers],
    model=MODEL,
)


def _mock(error: str | None = None) -> dict:
    """Фолбэк без ключа/интернета: демо не падает, а честно показывает реальные цифры."""
    s = tools.summary()
    a = tools.find_anomalies(1)
    n = lambda x: f"{x:,}".replace(",", " ")  # noqa: E731
    reply = (f"Демо-режим (без LLM). В базе {n(s['documents'])} начислений и выплат по {s['citizens']} гражданам, "
             f"просрочено {s['overdue']}, на проверку помечено {s['flagged']}.")
    if a:
        reply += f" Например: {a[0]['service']} на {n(a[0]['amount_kzt'])} ₸ — {a[0]['flag_reason']}."
    trace = [{"tool": "get_summary", "args": "{}"}]
    if error:
        trace.append({"tool": "error", "args": error[:300]})
    return {"reply": reply, "trace": trace, "mode": "mock"}


async def ask(messages: list[dict]) -> dict:
    if not os.getenv("OPENAI_API_KEY"):
        return _mock()
    try:
        result = await Runner.run(agent, messages, max_turns=8)
    except Exception as e:  # сеть/лимиты/модель — демо должно жить
        return _mock(f"{type(e).__name__}: {e}")
    trace = [{"tool": getattr(i.raw_item, "name", type(i.raw_item).__name__),
              "args": getattr(i.raw_item, "arguments", "")}
             for i in result.new_items if i.type == "tool_call_item"]
    return {"reply": str(result.final_output), "trace": trace, "mode": "live"}
