"""
🔧 EXCHANGE MANAGER
Правильне підключення до Binance Testnet/Mainnet з перевіркою ключів
"""

import os
import ccxt  # ✅ Використовуємо синхронний CCXT (як у робочому тесті)
import asyncio
import logging
from typing import Dict, Optional, Any
from datetime import datetime

# Спроба імпорту dotenv (якщо встановлено)
try:
    from dotenv import load_dotenv
    load_dotenv()  # Завантажуємо .env файл
except ImportError:
    print("python-dotenv не встановлено. Використовуємо системні змінні оточення.")

logger = logging.getLogger(__name__)

class ExchangeManager:
    """Менеджер підключення до біржі з правильним налаштуванням"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.exchange = None
        self.is_connected = False
        self.testnet_mode = False
        
    def initialize(self) -> bool:
        """Ініціалізація підключення до біржі (ТОЧНО як у робочому тесті)"""
        try:
            logger.info("[EXCHANGE] Ініціалізація підключення до Binance...")
            
            # Отримуємо ключі ТОЧНО як у тесті
            API_KEY = os.getenv('BINANCE_API_KEY')
            API_SECRET = os.getenv('BINANCE_SECRET')
            
            if not API_KEY or not API_SECRET:
                logger.error("[EXCHANGE] API ключі не знайдено!")
                logger.info("[EXCHANGE] Створіть .env файл з ключами або оновіть config.json")
                return False
            
            logger.info(f"[EXCHANGE] 🔑 API Key: {API_KEY[:10]}...{API_KEY[-10:]}")
            logger.info(f"[EXCHANGE] 🔑 Secret: {API_SECRET[:10]}...{API_SECRET[-10:]}")
            
            # Створюємо CCXT клієнт ТОЧНО як у робочому тесті
            self.exchange = ccxt.binance({
                "apiKey": API_KEY,
                "secret": API_SECRET,
                "enableRateLimit": True,
                "sandbox": True,  # Важливо: тестнет режим
                "options": {
                    "defaultType": "future",        # важливо: FUTURES, не spot
                    "adjustForTimeDifference": True,
                }
            })
            
            logger.info("[EXCHANGE] 🏗️ CCXT клієнт створено для Futures Testnet")
            
            # Тестуємо підключення ТОЧНО як у тесті
            if self._test_connection():
                self.is_connected = True
                self.testnet_mode = True
                logger.info("[EXCHANGE] ✅ Підключення до Binance Futures Testnet успішне!")
                return True
            else:
                logger.error("[EXCHANGE] ❌ Тест підключення провалився!")
                return False
                
        except Exception as e:
            logger.error(f"[EXCHANGE] Помилка підключення до біржі: {e}")
            self.exchange = None
            return False
            self.exchange = ccxt.binance({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
                'sandbox': testnet,                 # ВАЖЛИВО: тестнет режим
                'options': {
                    'defaultType': 'future',        # ВАЖЛИВО: futures, не spot
                    'adjustForTimeDifference': True,
                }
            })
            
            # Налаштовуємо testnet режим
            if testnet:
                logger.info("[EXCHANGE] Режим: BINANCE FUTURES TESTNET")
                self.testnet_mode = True
            else:
                logger.warning("[EXCHANGE] Режим: BINANCE FUTURES MAINNET (РЕАЛЬНІ ГРОШІ!)")
                self.testnet_mode = False
            
            # Тестуємо підключення (синхронно, як у робочому коді)
            connection_ok = self._test_connection()
            if connection_ok:
                self.is_connected = True
                logger.info("[EXCHANGE] ✅ Підключення успішне!")
                self._log_account_info()
                return True
            else:
                logger.error("[EXCHANGE] ❌ Помилка підключення!")
                return False
                
        except Exception as e:
            logger.error(f"[EXCHANGE] Критична помилка ініціалізації: {e}")
            return False
    
    def _get_api_key(self) -> Optional[str]:
        """Отримати API ключ з .env або config"""
        # Спочатку пробуємо .env
        key = os.getenv('BINANCE_API_KEY')
        if key and key != 'your_testnet_api_key_here':
            return key
        
        # Потім config.json
        key = self.config.get('exchange', {}).get('api_key')
        if key and key != 'YOUR_BINANCE_API_KEY':
            return key
        
        return None
    
    def _get_api_secret(self) -> Optional[str]:
        """Отримати API secret з .env або config"""
        # Спочатку пробуємо .env (правильна назва змінної)
        secret = os.getenv('BINANCE_SECRET')  # ВИПРАВЛЕНО: BINANCE_SECRET
        if secret and secret != 'your_testnet_secret_here':
            return secret
        
        # Потім config.json
        secret = self.config.get('exchange', {}).get('api_secret')
        if secret and secret != 'YOUR_BINANCE_API_SECRET':
            return secret
        
        return None
    
    def _is_testnet_mode(self) -> bool:
        """Визначити чи використовувати testnet"""
        # З .env (BINANCE_TESTNET - правильна назва змінної)
        env_testnet = os.getenv('BINANCE_TESTNET', '').lower()
        if env_testnet in ('true', '1', 'yes'):
            return True
        
        # З config
        return self.config.get('exchange', {}).get('testnet', True)
    
    def _validate_key_format(self, api_key: str, api_secret: str) -> bool:
        """Перевірити формат API ключів"""
        if not api_key or not api_secret:
            return False
        
        # Binance API ключі зазвичай 64 символи
        if len(api_key) < 40:
            logger.error(f"[EXCHANGE] API key занадто короткий: {len(api_key)} символів")
            return False
        
        if len(api_secret) < 40:
            logger.error(f"[EXCHANGE] API secret занадто короткий: {len(api_secret)} символів")
            return False
        
        # Перевіряємо на placeholder значення
        placeholders = [
            'your_binance_api_key',
            'YOUR_BINANCE_API_KEY',
            'your_testnet_api_key_here',
            'xxx', 'test', 'placeholder'
        ]
        
        for placeholder in placeholders:
            if placeholder.lower() in api_key.lower():
                logger.error(f"[EXCHANGE] API key містить placeholder: {placeholder}")
                return False
            if placeholder.lower() in api_secret.lower():
                logger.error(f"[EXCHANGE] API secret містить placeholder: {placeholder}")
                return False
        
        return True
    
    def _test_connection(self) -> bool:
        """Тестувати підключення до біржі (ТОЧНО як у робочому тесті)"""
        try:
            logger.info("[EXCHANGE] 📊 Перевіряємо баланс...")
            
            # Тест 1: Баланс аккаунту (ТОЧНО як у тесті)
            balance = self.exchange.fetch_balance()
            usdt_balance = balance['total'].get('USDT', 0)
            logger.info(f"[EXCHANGE] 💰 USDT balance: {usdt_balance}")
            
            # Тест 2: Завантаження ринків (ТОЧНО як у тесті)
            logger.info("[EXCHANGE] 🏪 Завантажуємо ринки...")
            markets = self.exchange.load_markets()
            logger.info(f"[EXCHANGE] Завантажено {len(markets)} ринків")
            
            # Тест 3: Перевірка наших символів (ТОЧНО як у тесті)
            our_symbols = ["BTC/USDT", "PENDLE/USDT", "DIA/USDT", "API3/USDT", "RENDER/USDT", "UMA/USDT", "FIDA/USDT"]
            available_count = 0
            
            for symbol in our_symbols:
                if symbol in markets:
                    available_count += 1
                    logger.info(f"[EXCHANGE] ✅ {symbol} - доступний")
                else:
                    logger.warning(f"[EXCHANGE] ❌ {symbol} - НЕ доступний")
            
            logger.info(f"[EXCHANGE] 📊 Наші символи: {available_count}/{len(our_symbols)} доступно")
            
            return True
            
        except ccxt.AuthenticationError as e:
            logger.error(f"[EXCHANGE] ❌ Помилка автентифікації: {e}")
            logger.error("[EXCHANGE] 🔧 Перевірте API ключі з https://testnet.binancefuture.com/")
            return False
        except ccxt.NetworkError as e:
            logger.error(f"[EXCHANGE] ❌ Мережева помилка: {e}")
            return False
        except Exception as e:
            logger.error(f"[EXCHANGE] ❌ Помилка тестування: {e}")
            return False
    
    def _log_account_info(self):
        """Логувати інформацію про аккаунт (синхронно)"""
        try:
            balance = self.exchange.fetch_balance()
            
            logger.info("[EXCHANGE] Інформація про аккаунт:")
            logger.info(f"  Режим: {'TESTNET' if self.testnet_mode else 'MAINNET'}")
            
            # Показуємо ненульові баланси
            for currency, data in balance.items():
                if isinstance(data, dict) and data.get('total', 0) > 0:
                    logger.info(f"  {currency}: {data['total']} (доступно: {data['free']})")
            
        except Exception as e:
            logger.warning(f"[EXCHANGE] Не вдалося отримати інформацію про аккаунт: {e}")
    
    def close(self):
        """Закрити підключення (синхронно)"""
        if self.exchange:
            # У синхронному CCXT немає методу close()
            self.exchange = None
            logger.info("[EXCHANGE] Підключення закрито")
            self.is_connected = False

# Інструкції для користувача
def print_setup_instructions():
    """Вивести інструкції налаштування"""
    print("🔧 НАЛАШТУВАННЯ BINANCE API")
    print("=" * 50)
    print()
    print("1. Перейдіть на https://testnet.binance.vision/")
    print("2. Увійдіть через GitHub або створіть аккаунт")
    print("3. Створіть API ключі:")
    print("   - Натисніть 'Create API Key'")
    print("   - Вкажіть назву (наприклад: 'Trading Bot')")
    print("   - Увімкніть 'Futures Trading' якщо потрібно")
    print("   - Скопіюйте API Key та Secret Key")
    print()
    print("4. Створіть файл .env в папці бота:")
    print("   BINANCE_API_KEY=ваш_api_key")
    print("   BINANCE_SECRET=ваш_secret_key")
    print("   USE_TESTNET=true")
    print()
    print("5. Запустіть бота знову")
    print()

if __name__ == "__main__":
    # Тест модуля
    print_setup_instructions()
