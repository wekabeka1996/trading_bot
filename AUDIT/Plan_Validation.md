Перевірка плану на відповідність шаблону та правилам:

- Структура JSON валідована через Pydantic моделі в `trading_bot/plan_parser.py`.
- Ключові інваріанти:
  - 0 < risk_budget ≤ 1
  - 0 < global_settings.margin_limit_pct ≤ 1
  - Кожен OrderGroup має: order_type, trigger_price, stop_loss, take_profit[], time_valid_from/to (ISO з TZ).
- Часові фази мають action і (time | start_time).
- Ризикові тригери можуть містити threshold_pct/threshold/points + action.

Додаткові ручні перевірки на базі docs/ШАБЛОН_ПЛАНУ.md рекомендовано автоматизувати окремим скриптом (TODO).
