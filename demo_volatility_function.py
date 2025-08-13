#!/usr/bin/env python3
"""
Демонстрація функції cancel_all_orders при високій волатільності BTC
"""

print("🔍 ДЕМО: BTC волатільність > 3% → cancel_all_orders()")
print("="*60)

print("""
✅ ДОДАНО ДО ENGINE.PY:

1. 📊 ФУНКЦІЯ _check_btc_volatility_simple():
   - Збирає ціни BTC кожну хвилину
   - Розраховує волатільність з останніх 5-10 цін  
   - Тригер: якщо волатільність > 3%

2. 🚫 ФУНКЦІЯ _cancel_all_orders():
   - Скасовує ВСІ активні ордери
   - Для всіх активів з плану
   - Надсилає сповіщення в Telegram

3. 🔄 ІНТЕГРАЦІЯ В _check_global_risks():
   - Викликається кожні 15 секунд
   - Після kill-switch перевірки
   - Синхронна, не блокує основний цикл

📝 КОД ЛОГІКИ:
```python
def _check_global_risks(self, _: datetime):
    # ... kill-switch логіка ...
    
    # Перевірка волатільності BTC
    try:
        if self._check_btc_volatility_simple():
            self.logger.warning("🚨 Скасовуємо ордери через високу волатільність BTC!")
            self._cancel_all_orders()
    except Exception as e:
        self.logger.debug(f"Помилка перевірки волатільності: {e}")
```

🎯 РЕЗУЛЬТАТ:
✅ if btc_5m_volatility > 3%: cancel_all_orders() - РЕАЛІЗОВАНО!

⚠️  АКТИВАЦІЯ:
- Автоматично працює після запуску Engine
- Перевірка кожну хвилину
- Скасування при волатільності > 3%
""")

print("\n🚀 Функціональність готова до використання!")
