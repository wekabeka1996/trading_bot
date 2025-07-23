# Простий синхронний провайдер ринкових даних
import logging
import requests
from typing import Dict, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class SimpleMarketDataProvider:
    def __init__(self, config: Dict):
        """Простий синхронний провайдер ринкових даних"""
        self.config = config
        logger.info("[DATA] Ініціалізація провайдера ринкових даних")
    
    def get_btc_dominance(self) -> Optional[float]:
        """Отримання BTC домінації"""
        try:
            url = "https://api.coingecko.com/api/v3/global"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                dominance = data['data']['market_cap_percentage']['btc']
                logger.debug(f"BTC домінація: {dominance:.2f}%")
                return dominance
        except Exception as e:
            logger.warning(f"Не вдалося отримати BTC домінацію: {e}")
        return 60.0  # Fallback значення
    
    def get_fear_greed_index(self) -> Optional[Dict]:
        """Отримання індексу страху та жадібності"""
        try:
            url = "https://api.alternative.me/fng/"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                index_data = data['data'][0]
                result = {
                    'value': int(index_data['value']),
                    'classification': index_data['value_classification'],
                    'timestamp': index_data['timestamp']
                }
                logger.debug(f"Fear & Greed: {result['value']} ({result['classification']})")
                return result
        except Exception as e:
            logger.warning(f"Не вдалося отримати Fear & Greed: {e}")
        return {'value': 50, 'classification': 'Neutral', 'timestamp': str(int(datetime.now().timestamp()))}
    
    def get_market_sentiment(self) -> Optional[Dict]:
        """Простий розрахунок настроїв ринку"""
        try:
            btc_dominance = self.get_btc_dominance()
            fear_greed = self.get_fear_greed_index()
            
            # Простий розрахунок
            sentiment_score = 50  # Нейтральний
            
            if btc_dominance and btc_dominance > 65:
                sentiment_score -= 10
            elif btc_dominance and btc_dominance < 55:
                sentiment_score += 10
                
            if fear_greed:
                fg_value = fear_greed['value']
                if fg_value > 75:
                    sentiment_score += 15
                elif fg_value < 25:
                    sentiment_score -= 15
            
            # Класифікація
            if sentiment_score >= 70:
                sentiment = "EXTREMELY_BULLISH"
            elif sentiment_score >= 55:
                sentiment = "BULLISH"
            elif sentiment_score >= 45:
                sentiment = "NEUTRAL"
            elif sentiment_score >= 30:
                sentiment = "BEARISH"
            else:
                sentiment = "EXTREMELY_BEARISH"
            
            return {
                'sentiment': sentiment,
                'score': sentiment_score,
                'btc_dominance': btc_dominance,
                'fear_greed': fear_greed,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.warning(f"Помилка аналізу настроїв: {e}")
            return {
                'sentiment': 'NEUTRAL',
                'score': 50,
                'btc_dominance': 60.0,
                'fear_greed': {'value': 50, 'classification': 'Neutral'},
                'timestamp': datetime.now().isoformat()
            }
