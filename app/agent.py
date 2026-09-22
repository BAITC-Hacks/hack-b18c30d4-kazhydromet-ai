"""AI-агент на OpenAI Agents SDK. Новый инструмент = функция в tools.py + обёртка @function_tool здесь."""
import json
import os

from agents import Agent, Runner, function_tool

from . import tools

MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

INSTRUCTIONS = """Ты — AI-аналитик банковских транзакций для сотрудника банка (антифрод и аналитика клиентов).
Правила:
- Любые цифры бери только из инструментов, ничего не выдумывай.
- Отвечай на языке пользователя (русский, казахский или английский).
- Суммы в тенге с разделителями тысяч: 1 250 000 ₸.
- Коротко: 3-6 предложений или список. В конце — одно конкретное действие, что сделать дальше."""


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False)


@function_tool
def get_summary() -> str:
    """Общая статистика: число транзакций и клиентов, сумма, средний чек, разбивка по категориям."""
    return _j(tools.summary())


@function_tool
def find_anomalies(z: float = 3.0, limit: int = 10) -> str:
    """Найти подозрительные транзакции, сильно выбивающиеся из обычных трат клиента.

    Args:
        z: Порог z-score (чем больше, тем строже). Обычно 2.5-4.
        limit: Сколько транзакций вернуть.
    """
    return _j(tools.find_anomalies(z, limit))


@function_tool
def client_profile(client_id: str) -> str:
    """Профиль клиента: город, траты, топ категорий, подозрительные операции.

    Args:
        client_id: ID клиента вида C001.
    """
    return _j(tools.client_profile(client_id))


@function_tool
def search_transactions(category: str | None = None, city: str | None = None,
                        min_amount: int = 0, limit: int = 20) -> str:
    """Поиск транзакций по категории, городу и минимальной сумме (самые крупные первыми).

    Args:
        category: Категория, например "Переводы" или "АЗС".
        city: Город, например "Алматы".
        min_amount: Минимальная сумма в тенге.
        limit: Сколько вернуть.
    """
    return _j(tools.search_transactions(category, city, min_amount, limit))


agent = Agent(
    name="FinAnalyst",
    instructions=INSTRUCTIONS,
    tools=[get_summary, find_anomalies, client_profile, search_transactions],
    model=MODEL,
)


def _mock(error: str | None = None) -> dict:
    """Фолбэк без ключа/интернета: демо не падает, а честно показывает реальные цифры."""
    s = tools.summary()
    top = next(iter(s["by_category"]))
    n = lambda x: f"{x:,}".replace(",", " ")  # noqa: E731
    reply = (f"Демо-режим (без LLM). В базе {n(s['transactions'])} транзакций на {n(s['total_kzt'])} ₸, "
             f"помечено подозрительных: {s['flagged']}. Больше всего тратят на «{top}».")
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
