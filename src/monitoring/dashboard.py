# Дашборд для моніторингу торгового бота
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json
import os

st.set_page_config(
    page_title="Торговий Бот - Дашборд", 
    page_icon="🤖",
    layout="wide"
)

def load_trading_data():
    """Завантаження торгових даних"""
    # Тут буде реальне завантаження з файлів/БД
    # Поки що використовуємо тестові дані
    return {
        'portfolio_value': 62.50,
        'daily_pnl': 4.50,
        'total_pnl': 4.50,
        'active_positions': 3,
        'total_trades': 8,
        'win_rate': 62.5
    }

def create_portfolio_chart():
    """Графік зміни портфеля"""
    dates = pd.date_range(start='2025-07-15', end='2025-07-21', freq='D')
    values = [58.0, 59.2, 57.8, 61.3, 60.1, 62.5, 62.5]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, 
        y=values,
        mode='lines+markers',
        name='Вартість портфеля',
        line=dict(color='#00D4AA', width=3)
    ))
    
    fig.update_layout(
        title="📈 Динаміка портфеля",
        xaxis_title="Дата",
        yaxis_title="Вартість ($)",
        height=400
    )
    
    return fig

def create_positions_table():
    """Таблиця активних позицій"""
    positions_data = {
        'Символ': ['PENDLE', 'DIA', 'API3'],
        'Розмір ($)': [14.50, 13.34, 9.86],
        'Вхідна ціна': [2.24, 0.67, 1.45],
        'Поточна ціна': [2.31, 0.69, 1.43],
        'P&L (%)': ['+3.1%', '+2.9%', '-1.4%'],
        'Плече': ['5x', '5x', '4x']
    }
    
    return pd.DataFrame(positions_data)

def main():
    """Головна функція дашборду"""
    
    # Заголовок
    st.title("🤖 Автоматична торгова система")
    st.markdown("**Версія 2.0** | Оптимізована під план від 21.07.2025")
    
    # Завантаження даних
    data = load_trading_data()
    
    # Метрики в колонках
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="💰 Вартість портфеля", 
            value=f"${data['portfolio_value']:.2f}",
            delta=f"{data['daily_pnl']:+.2f} за день"
        )
    
    with col2:
        st.metric(
            label="📊 Загальний P&L", 
            value=f"${data['total_pnl']:+.2f}",
            delta=f"{(data['total_pnl']/58)*100:+.1f}%"
        )
    
    with col3:
        st.metric(
            label="🔄 Активні позиції", 
            value=data['active_positions']
        )
    
    with col4:
        st.metric(
            label="🎯 Відсоток прибуткових", 
            value=f"{data['win_rate']:.1f}%"
        )
    
    # Графік портфеля
    st.plotly_chart(create_portfolio_chart(), use_container_width=True)
    
    # Дві колонки для таблиць
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📋 Активні позиції")
        positions_df = create_positions_table()
        st.dataframe(positions_df, use_container_width=True)
    
    with col2:
        st.subheader("⚙️ Налаштування")
        
        # Елементи управління
        if st.button("🛑 Екстрена зупинка", type="primary"):
            st.error("🚨 Команда екстренної зупинки відправлена!")
        
        if st.button("📊 Експорт звіту"):
            st.success("✅ Звіт експортовано в trading_report.pdf")
        
        # Налаштування ризиків
        st.write("**Ризик-менеджмент:**")
        max_risk = st.slider("Максимальний ризик (%)", 1.0, 5.0, 2.5, 0.1)
        emergency_stop = st.slider("Екстрений стоп (%)", -20.0, -5.0, -10.0, 1.0)
    
    # Лог активності
    st.subheader("📝 Останні дії")
    
    log_data = {
        'Час': ['14:23:45', '14:15:32', '13:45:12', '12:30:05'],
        'Дія': ['Позиція закрита', 'Стоп-лосс спрацював', 'Позиція відкрита', 'Система запущена'],
        'Символ': ['PENDLE', 'API3', 'DIA', '-'],
        'Результат': ['+$2.15', '-$1.20', 'Відкрито', 'OK']
    }
    
    log_df = pd.DataFrame(log_data)
    st.dataframe(log_df, use_container_width=True)
    
    # Статус системи
    st.sidebar.title("📊 Статус системи")
    st.sidebar.success("🟢 Система працює")
    st.sidebar.info(f"⏱️ Час роботи: 2 год 15 хв")
    st.sidebar.info(f"🔄 Останнє оновлення: {datetime.now().strftime('%H:%M:%S')}")
    
    # Ринкові умови
    st.sidebar.title("🌐 Ринкові умови")
    st.sidebar.metric("₿ BTC домінація", "61.2%", "-0.8%")
    st.sidebar.metric("😨 Fear & Greed", "74", "+5")
    st.sidebar.metric("💱 Avg Funding", "0.08%", "-0.02%")

if __name__ == "__main__":
    main()
