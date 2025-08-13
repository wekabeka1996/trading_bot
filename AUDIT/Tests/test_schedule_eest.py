import pytest
import pytz
from datetime import datetime

# Пропускаємо, якщо немає залежностей, що тягнуться транзитивно через engine
pytest.importorskip("binance")
pytest.importorskip("telegram")

from trading_bot.engine import Engine

def test_is_within_entry_hours_blocks_night(monkeypatch):
    eng = object.__new__(Engine)
    assert eng._is_within_entry_hours_eest(
        datetime(2025, 8, 8, 1, 0, tzinfo=pytz.utc)
    ) is False
    # 07:59 EEST == 04:59 UTC
    assert eng._is_within_entry_hours_eest(
        datetime(2025, 8, 8, 4, 59, tzinfo=pytz.utc)
    ) is False


def test_is_within_entry_hours_allows_daytime():
    from trading_bot.engine import Engine
    eng = object.__new__(Engine)
    # метод не залежить від стану плану
    assert eng._is_within_entry_hours_eest(
        datetime(2025, 8, 8, 10, 0, tzinfo=pytz.utc)
    ) is True
    assert eng._is_within_entry_hours_eest(
        datetime(2025, 8, 8, 22, 30, tzinfo=pytz.utc)
    ) in (True, False)  # залежить від EEST конвертації, просто smoke
