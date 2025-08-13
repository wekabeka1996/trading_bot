"""Конфигурация Telegram-бота."""

from dataclasses import dataclass
from typing import List, Dict

@dataclass
class TelegramConfig:
    """Конфигурация для расширенного функционала Telegram."""
    
    # Основные настройки
    token: str
    chat_id: str
    
    # Разрешенные пользователи (для мультипользовательского режима)
    allowed_users: List[int] = None
    
    # Настройки уведомлений
    notification_levels: Dict[str, bool] = None
    
    # Автоматические отчеты
    auto_reports: Dict[str, str] = None  # {'daily': '22:00', 'weekly': 'sunday 22:00'}
    
    # Лимиты команд (защита от спама)
    rate_limits: Dict[str, int] = None  # {'status': 10, 'close': 5}  # запросов в минуту
    
    def __post_init__(self):
        if self.notification_levels is None:
            self.notification_levels = {
                'info': True,
                'warning': True,
                'critical': True,
                'trade': True,
                'success': True
            }
            
        if self.auto_reports is None:
            self.auto_reports = {
                'daily': '21:40',
                'weekly': 'sunday 22:00'
            }
            
        if self.rate_limits is None:
            self.rate_limits = {
                'status': 30,
                'positions': 30,
                'close': 10,
                'emergency': 3
            }