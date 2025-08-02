# trading_bot/plan_parser.py
# Модуль для завантаження, валідації та доступу до торгового плану.
# Використовує Pydantic для надійної валідації структури JSON.

"""
Модуль для завантаження, валідації та доступу до торгового плану.
Використовує Pydantic для надійної валідації структури JSON.
"""

import json
import logging
from typing import List, Dict, Optional
from pydantic import BaseModel, ValidationError


# --- Pydantic моделі для валідації структури trading_plan.json ---


class GlobalSettings(BaseModel):
    """Глобальні параметри ризику для всього портфеля."""
    max_portfolio_risk: float
    emergency_stop_loss: float
    daily_profit_target: float
    max_concurrent_positions: int
    max_notional_per_trade: float = 25.0
    margin_limit_pct: float = 0.40


class OrderGroup(BaseModel):
    """Налаштування групи ордерів (наприклад, bullish / bearish)."""
    order_type: str
    trigger_price: float
    limit_price: Optional[float] = None
    stop_loss: float
    take_profit: List[float]
    time_valid_from: str
    time_valid_to: str


class DynamicManagement(BaseModel):
    """Параметри динамічного управління відкритою позицією."""
    trailing_sl_atr_multiple: Optional[float] = None
    atr_window_min: Optional[int] = None
    activate_after_profit: Optional[float] = None


class Hedge(BaseModel):
    """Параметри хеджування позиції."""
    symbol: str
    direction: str
    size_pct: float
    delta: float


class MonitoringRule(BaseModel):
    """
    Правило моніторингу ринкових даних (funding, OI, dominance тощо),
    що може ініціювати дію risk-managerʼа.
    """
    threshold: Optional[float] = None
    threshold_pct: Optional[float] = None
    threshold_points: Optional[float] = None
    action: str
    window_min: Optional[int] = None
    source: Optional[str] = None

    model_config = {"extra": "allow"}


class ActiveAsset(BaseModel):
    """Опис активу та стратегії, що торгується згідно плану."""
    symbol: str
    asset_type: str
    leverage: int
    strategy: str
    position_size_pct: float
    order_groups: Dict[str, OrderGroup]
    dynamic_management: Optional[DynamicManagement] = None
    hedge: Optional[Hedge] = None
    monitoring_rules: Optional[Dict[str, MonitoringRule]] = None


class TradePhase(BaseModel):
    """Часова фаза дня з відповідною дією (setup, cancel тощо)."""
    action: Optional[str] = None
    time: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    description: str


class RiskTrigger(BaseModel):
    """Глобальний тригер ризику, який діє на кілька активів одразу."""
    threshold_pct: Optional[float] = None
    action: str
    assets: Optional[List[str]] = None
    keyword: Optional[List[str]] = None


class TradingPlan(BaseModel):
    """Повна модель торгового плану."""
    plan_date: str
    plan_version: str
    plan_type: str
    risk_budget: float
    global_settings: GlobalSettings
    active_assets: List[ActiveAsset]
    trade_phases: Dict[str, TradePhase]
    risk_triggers: Dict[str, RiskTrigger]
    end_of_day_checklist: List[str]


# --- Основний клас парсера ---


class PlanParser:
    """
    Читає та валідує файл trading_plan.json.
    """

    def __init__(self, plan_path: str):
        self.plan_path = plan_path
        self.plan: Optional[TradingPlan] = None
        self.logger = logging.getLogger(__name__)

    def load_and_validate(self) -> bool:
        """
        Завантажує JSON з файлу та валідує його за допомогою Pydantic моделі.
        :return: True, якщо план успішно завантажено та валідовано,
                 інакше False.
        """
        try:
            with open(self.plan_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            self.plan = TradingPlan.model_validate(data)
            self.logger.info(
                "Торговий план '%s' версії %s успішно завантажено та "
                "валідовано.",
                self.plan.plan_type,
                self.plan.plan_version,
            )
            return True

        except FileNotFoundError:
            self.logger.critical(
                "Файл торгового плану не знайдено за шляхом: %s",
                self.plan_path,
            )
            return False

        except json.JSONDecodeError:
            self.logger.critical(
                "Помилка формату JSON у файлі плану: %s",
                self.plan_path,
            )
            return False

        except ValidationError as err:
            self.logger.critical(
                "Помилка валідації торгового плану. Перевірте структуру файлу."
            )
            self.logger.error(err)
            return False

        except Exception as err:  # pylint: disable=broad-except
            self.logger.critical(
                "Невідома помилка при завантаженні плану: %s",
                err,
                exc_info=True,
            )
            return False

    def get_plan(self) -> Optional[TradingPlan]:
        """Повертає завантажений та валідований план."""
        return self.plan

