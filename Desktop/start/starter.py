"""Учебный фрагмент для тестового задания ТОЛЬКООПТ.
Python 3.10+, только стандартная библиотека.
Запуск примера: python starter.py
Запуск тестов: python -m unittest -v starter.py
"""

import asyncio
from collections.abc import Awaitable, Callable
from decimal import ROUND_DOWN, Decimal
from typing import Any
import unittest


def _hold(current_price: Decimal, reason: str) -> dict[str, Any]:
    return {
        "price": current_price,
        "decision": "HOLD",
        "reason": reason,
    }


async def recommend_price(
    fetch_offers: Callable[[], Awaitable[dict[str, Any]]],
    current_price: Decimal,
    min_price: Decimal,
    timeout_s: float = 2.0,
) -> dict[str, Any]:
    # 1. Ограничиваем ожидание timeout_s; при ошибке, тайм-ауте или status != success -> HOLD
    try:
        result = await asyncio.wait_for(fetch_offers(), timeout=timeout_s)
    except asyncio.TimeoutError:
        return _hold(current_price, "Превышено время ожидания ответа от источника")
    except Exception:
        return _hold(current_price, "Ошибка при обращении к источнику предложений")

    if result.get("status") != "success":
        return _hold(
            current_price,
            f"Источник вернул некорректный статус: {result.get('status')}",
        )

    # 2. Фильтруем предложения: известная доставка <= 6 дней и не MYSHOP (без учёта регистра)
    valid_prices = [
        offer["price"]
        for offer in result.get("offers", [])
        if offer["delivery_days"] is not None
        and offer["delivery_days"] <= 6
        and offer["seller"].lower() != "myshop"
    ]

    # 3. Если подходящих предложений нет -> current_price и HOLD (даже если current_price < min_price)
    if not valid_prices:
        return _hold(current_price, "Нет подходящих предложений конкурентов")

    # 4. Минимум конкурента уменьшаем на 1.5%, округляем вниз до копейки, не ниже min_price
    min_competitor_price = min(valid_prices)
    discounted_price = (min_competitor_price * Decimal("0.985")).quantize(
        Decimal("0.01"),
        rounding=ROUND_DOWN,
    )
    recommended_price = max(discounted_price, min_price)

    # 5. Отклонение > 30% от текущей цены -> REVIEW, ровно 30% или меньше -> APPLY
    deviation = abs(recommended_price - current_price) / current_price
    if deviation > Decimal("0.30"):
        return {
            "price": recommended_price,
            "decision": "REVIEW",
            "reason": "Изменение цены превышает 30%, требуется ручная проверка",
        }

    return {
        "price": recommended_price,
        "decision": "APPLY",
        "reason": "Найдена конкурентная цена в допустимых пределах",
    }


async def sample_fetch_offers() -> dict[str, Any]:
    return {
        "status": "success",
        "offers": [
            {"seller": "myshop", "price": Decimal("4300.00"), "delivery_days": 2},
            {"seller": "PARTS", "price": Decimal("4800.00"), "delivery_days": 3},
            {"seller": "SLOW", "price": Decimal("4700.00"), "delivery_days": 8},
        ],
    }


class TestRecommendPrice(unittest.IsolatedAsyncioTestCase):
    async def test_regular_calculation_apply(self) -> None:
        """Тест 1: Обычный расчёт на примере из задания -> 4728.00 и APPLY."""
        res = await recommend_price(
            sample_fetch_offers,
            current_price=Decimal("4900.00"),
            min_price=Decimal("4500.00"),
        )
        self.assertEqual(res["price"], Decimal("4728.00"))
        self.assertEqual(res["decision"], "APPLY")

    async def test_timeout_and_review_boundary(self) -> None:
        """Тест 2: Тайм-аут источника (-> HOLD) и отклонение > 30% (-> REVIEW)."""

        async def slow_fetch() -> dict[str, Any]:
            await asyncio.sleep(0.2)
            return {"status": "success", "offers": []}

        timeout_res = await recommend_price(
            slow_fetch,
            current_price=Decimal("4900.00"),
            min_price=Decimal("4500.00"),
            timeout_s=0.05,
        )
        self.assertEqual(timeout_res["price"], Decimal("4900.00"))
        self.assertEqual(timeout_res["decision"], "HOLD")

        async def low_competitor_fetch() -> dict[str, Any]:
            return {
                "status": "success",
                "offers": [
                    {"seller": "COMP", "price": Decimal("1000.00"), "delivery_days": 2}
                ],
            }

        # 1000.00 * 0.985 = 985.00; max(985.00, 1300.01) = 1300.01
        # Отклонение от 1000.00 составляет 30.001% (> 30%) -> REVIEW
        review_res = await recommend_price(
            low_competitor_fetch,
            current_price=Decimal("1000.00"),
            min_price=Decimal("1300.01"),
        )
        self.assertEqual(review_res["price"], Decimal("1300.01"))
        self.assertEqual(review_res["decision"], "REVIEW")


if __name__ == "__main__":
    print(
        asyncio.run(
            recommend_price(
                sample_fetch_offers,
                current_price=Decimal("4900.00"),
                min_price=Decimal("4500.00"),
            )
        )
    )
