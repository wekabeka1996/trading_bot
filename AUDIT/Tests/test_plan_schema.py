import json
from trading_bot.plan_parser import PlanParser


def test_plan_parses_default_json():
    parser = PlanParser("data/trading_plan.json")
    assert parser.load_and_validate() is True
    plan = parser.get_plan()
    assert plan is not None
    # прості інваріанти
    assert 0 < plan.global_settings.margin_limit_pct <= 1
    assert 0 < plan.risk_budget <= 1
