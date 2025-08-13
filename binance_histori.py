# binance_futures_export.py
import os, time, hmac, hashlib, argparse, csv, math
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import requests

BASE = "https://fapi.binance.com"

# --- Load .env before reading env vars ---
def _load_env_file(path: str):
    try:
        if not os.path.isfile(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' not in line:
                    continue
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                # do not override already-set environment vars
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        # fail silent; script will error later if keys missing
        pass

# Try to load .env from repo root (same folder as this script)
_load_env_file(os.path.join(os.path.dirname(__file__), '.env'))

# Detect testnet
_TESTNET_RAW = os.getenv("BINANCE_TESTNET", "False").strip().lower()
TESTNET = _TESTNET_RAW in ("1", "true", "yes", "y", "on")
if TESTNET:
    BASE = "https://testnet.binancefuture.com"

# Resolve API credentials (support multiple common names)
if TESTNET:
    API_KEY = (
        os.getenv("BINANCE_TESTNET_API_KEY")
        or os.getenv("BINANCE_API_KEY")
        or os.getenv("BINANCE_APIKEY")
        or os.getenv("BINANCE_KEY")
        or ""
    )
    API_SECRET = (
        os.getenv("BINANCE_TESTNET_SECRET")
        or os.getenv("BINANCE_API_SECRET")
        or os.getenv("BINANCE_SECRET")
        or os.getenv("BINANCE_APISECRET")
        or ""
    )
else:
    API_KEY = (
        os.getenv("BINANCE_API_KEY")
        or os.getenv("BINANCE_APIKEY")
        or os.getenv("BINANCE_KEY")
        or ""
    )
    API_SECRET = (
        os.getenv("BINANCE_API_SECRET")
        or os.getenv("BINANCE_SECRET")
        or os.getenv("BINANCE_APISECRET")
        or ""
    )

def now_ms():
    return int(time.time() * 1000)

def to_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)

def parse_ymd(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)

def sign(params: dict) -> str:
    query = urlencode(params, doseq=True)
    sig = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    return f"{query}&signature={sig}"

def get(endpoint: str, params: dict):
    params = dict(params or {})
    params.setdefault("timestamp", now_ms())
    params.setdefault("recvWindow", 5000)
    headers = {"X-MBX-APIKEY": API_KEY}
    url = f"{BASE}{endpoint}?{sign(params)}"
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code == 429:
        # rate limit: exponential backoff
        time.sleep(1.5)
        r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

def public_get(endpoint: str, params=None):
    url = f"{BASE}{endpoint}"
    r = requests.get(url, params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()

def ensure_outdir(path: str):
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)

def fetch_usdt_perp_symbols(include_majors: bool):
    info = public_get("/fapi/v1/exchangeInfo")
    symbols = []
    for s in info.get("symbols", []):
        if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING" and s.get("contractType") == "PERPETUAL":
            sym = s.get("symbol")
            if not include_majors and sym in ("BTCUSDT", "ETHUSDT"):
                continue
            symbols.append(sym)
    # деякі "екзоти" можуть бути зайвими — але краще забрати все
    return sorted(set(symbols))

def daterange_batches(start_ms: int, end_ms: int, days_step: int = 30):
    start = datetime.fromtimestamp(start_ms/1000, tz=timezone.utc)
    end = datetime.fromtimestamp(end_ms/1000, tz=timezone.utc)
    cur = start
    step = timedelta(days=days_step)
    while cur < end:
        nxt = min(cur + step, end)
        yield to_ms(cur), to_ms(nxt)
        cur = nxt

def write_csv(path: str, rows: list):
    if not rows:
        return
    # нормалізуємо поля
    fieldnames = sorted({k for row in rows for k in row.keys()})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

def fetch_trades_for_symbol(symbol: str, start_ms: int, end_ms: int) -> list:
    """/fapi/v1/userTrades requires symbol; реалізуємо batched time + fromId pagination"""
    all_rows = []
    for s_ms, e_ms in daterange_batches(start_ms, end_ms, days_step=30):
        from_id = None
        while True:
            params = {"symbol": symbol, "startTime": s_ms, "endTime": e_ms, "limit": 1000}
            if from_id is not None:
                params["fromId"] = from_id
            data = get("/fapi/v1/userTrades", params)
            if not data:
                break
            # додаємо символ явно
            for d in data:
                d["symbol"] = symbol
            all_rows.extend(data)
            if len(data) < 1000:
                break
            from_id = data[-1]["id"] + 1
            time.sleep(0.05)  # трішки паузи для лімітів
        time.sleep(0.05)
    return all_rows

def fetch_orders_for_symbol(symbol: str, start_ms: int, end_ms: int) -> list:
    """allOrders по 1000, батчимо по часу"""
    all_rows = []
    for s_ms, e_ms in daterange_batches(start_ms, end_ms, days_step=30):
        params = {"symbol": symbol, "startTime": s_ms, "endTime": e_ms, "limit": 1000}
        data = get("/fapi/v1/allOrders", params)
        for d in data:
            d["symbol"] = symbol
        all_rows.extend(data)
        time.sleep(0.05)
    return all_rows

def fetch_income(start_ms: int, end_ms: int) -> list:
    """/fapi/v1/income — можна без symbol; батчимо по часу"""
    all_rows = []
    for s_ms, e_ms in daterange_batches(start_ms, end_ms, days_step=30):
        cursor = s_ms
        while cursor < e_ms:
            params = {"startTime": cursor, "endTime": e_ms, "limit": 1000}
            data = get("/fapi/v1/income", params)
            if not data:
                break
            all_rows.extend(data)
            # Якщо повернуло <1000, значить вікно вичерпано
            if len(data) < 1000:
                break
            # Інакше рухаємо курсор за останній запис (поле time)
            try:
                last_time = int(data[-1].get('time') or data[-1].get('updateTime'))
                cursor = last_time + 1
            except Exception:
                # fallback: зрушимо курсор на +1 хвилину
                cursor += 60_000
            time.sleep(0.05)
        time.sleep(0.05)
    return all_rows

def fetch_positions_snapshot() -> list:
    """Поточні позиції/ризики на момент запуску"""
    data = get("/fapi/v2/positionRisk", {})
    # фільтруємо нульові позиції для зручності (але збережемо все — хай вирішує користувач)
    return data

def main():
    if not API_KEY or not API_SECRET:
        raise SystemExit("ERROR: BINANCE_API_KEY / BINANCE_API_SECRET не задані у змінних середовища.")

    parser = argparse.ArgumentParser(description="Binance USDⓈ-M Futures exporter (alts, no manual symbol list).")
    parser.add_argument("--since", type=str, default=None, help="Початок періоду, YYYY-MM-DD (UTC). За замовчуванням: 180 днів назад.")
    parser.add_argument("--outdir", type=str, default="export_out", help="Каталог для CSV.")
    parser.add_argument("--until", type=str, default=None, help="Кінець періоду, YYYY-MM-DD (UTC), включно (доба додається автоматично). За замовчуванням: зараз.")
    parser.add_argument("--include-majors", action="store_true", help="Включити BTCUSDT/ETHUSDT також.")
    parser.add_argument("--symbols", type=str, default=None, help="Кома-сепарований список символів для вибірки (наприклад: BTCUSDT,ETHUSDT). Якщо задано — інші фільтри ігноруються.")
    parser.add_argument("--symbols-add", type=str, default=None, help="Кома-сепарований список символів, які потрібно ДОДАТИ до вибору (працює з smart-filter або повним списком).")
    parser.add_argument("--smart-filter", action="store_true", help="Визначати символи з activity за періодом з income і відкритих позицій, і тягнути дані лише для них.")
    parser.add_argument("--limit-symbols", type=int, default=None, help="Ліміт кількості символів для обробки (для швидкої перевірки).")
    parser.add_argument("--only-income", action="store_true", help="Отримати лише income (PNL/депозити/комісії) без orders/trades.")
    args = parser.parse_args()

    ensure_outdir(args.outdir)

    # Обчислюємо межі періоду
    if args.until:
        # inclusive day end: add +1 day at 00:00 UTC
        end_dt = parse_ymd(args.until) + timedelta(days=1)
    else:
        end_dt = datetime.now(timezone.utc)

    if args.since:
        start_dt = parse_ymd(args.since)
    else:
        start_dt = end_dt - timedelta(days=180)  # дефолтно півроку
    start_ms, end_ms = to_ms(start_dt), to_ms(end_dt)

    # Якщо потрібен лише income — пропускаємо вибір символів і важкі цикли
    if args.only_income:
        print("→ Отримую тільки income …")
        all_income = []
        try:
            all_income = fetch_income(start_ms, end_ms)
        except Exception as e:
            print(f"!! Помилка income: {e}")

        print("→ Снапшот позицій/ризику …")
        positions = []
        try:
            positions = fetch_positions_snapshot()
        except Exception as e:
            print(f"!! Помилка positions: {e}")

        trades_path = os.path.join(args.outdir, "futures_trades.csv")
        orders_path = os.path.join(args.outdir, "futures_orders.csv")
        income_path = os.path.join(args.outdir, "futures_income.csv")
        positions_path = os.path.join(args.outdir, "futures_positions_snapshot.csv")

        write_csv(income_path, all_income)
        write_csv(positions_path, positions)
        # Порожні заглушки для послідовності
        write_csv(trades_path, [])
        write_csv(orders_path, [])

        print("✅ Готово (income only).")
        print(f"  • {trades_path}")
        print(f"  • {orders_path}")
        print(f"  • {income_path}")
        print(f"  • {positions_path}")
        print("Нагадування: ключ краще робити read-only + IP whitelist.")
        return

    # Обираємо символи
    selected_symbols = None

    # 1) Якщо вказані вручну
    if args.symbols:
        selected_symbols = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
        print(f"→ Обрані символи (з CLI): {len(selected_symbols)}")
    else:
        # 2) Якщо smart-filter: спершу тягнемо income/позиції і визначаємо символи
        if args.smart_filter:
            print("→ Smart-filter: тягну income для визначення активних символів …")
            all_income = []
            try:
                all_income = fetch_income(start_ms, end_ms)
            except Exception as e:
                print(f"!! Помилка income: {e}")
            income_symbols = {row.get('symbol') for row in all_income if row.get('symbol')}

            print("→ Smart-filter: тягну снапшот позицій …")
            positions = []
            try:
                positions = fetch_positions_snapshot()
            except Exception as e:
                print(f"!! Помилка positions: {e}")
            pos_symbols = set()
            for p in positions:
                try:
                    amt = float(p.get('positionAmt', 0) or 0)
                    if amt != 0:
                        sym = p.get('symbol')
                        if sym:
                            pos_symbols.add(sym)
                except Exception:
                    pass

            selected_symbols = sorted((income_symbols | pos_symbols))
            print(f"→ Smart-filter: активних символів знайдено: {len(selected_symbols)}")

            # Якщо нічого не знайшли — fallback на весь список біржі
            if not selected_symbols:
                print("→ Smart-filter: не знайдено activity. Переходимо до повного списку з біржі…")
                selected_symbols = fetch_usdt_perp_symbols(include_majors=args.include_majors)
        else:
            print("→ Отримую список USDT-перпів…")
            selected_symbols = fetch_usdt_perp_symbols(include_majors=args.include_majors)

    # Додаємо примусово вказані символи (symbols-add)
    if args.symbols_add:
        extra = [s.strip().upper() for s in args.symbols_add.split(',') if s.strip()]
        selected_symbols = sorted(set(selected_symbols) | set(extra))

    # Ліміт символів, якщо задано
    if args.limit_symbols is not None and args.limit_symbols > 0:
        selected_symbols = selected_symbols[: args.limit_symbols]

    print(f"→ Символів до обробки: {len(selected_symbols)}")
    # Ensure placeholders exist
    all_income = locals().get('all_income', [])
    positions = locals().get('positions', [])

    all_trades, all_orders = [], []

    # Основний цикл
    for i, sym in enumerate(selected_symbols, 1):
        print(f"[{i}/{len(selected_symbols)}] Тягну trades/orders для {sym} …")
        try:
            tr = fetch_trades_for_symbol(sym, start_ms, end_ms)
            if tr:
                all_trades.extend(tr)
            od = fetch_orders_for_symbol(sym, start_ms, end_ms)
            if od:
                all_orders.extend(od)
        except requests.HTTPError as e:
            print(f"!! HTTPError по {sym}: {e}")
        except Exception as e:
            print(f"!! Помилка по {sym}: {e}")
        time.sleep(0.05)

    # Income ми могли вже отримати у smart-filter. Якщо ні — тягнемо зараз
    if not (args.smart_filter and 'all_income' in locals()):
        print("→ Тягну income (PNL, funding, комісії) …")
        all_income = []
        try:
            all_income = fetch_income(start_ms, end_ms)
        except Exception as e:
            print(f"!! Помилка income: {e}")

    print("→ Снапшот позицій/ризику …")
    if not (args.smart_filter and 'positions' in locals()):
        positions = []
        try:
            positions = fetch_positions_snapshot()
        except Exception as e:
            print(f"!! Помилка positions: {e}")

    # Запис у CSV
    trades_path = os.path.join(args.outdir, "futures_trades.csv")
    orders_path = os.path.join(args.outdir, "futures_orders.csv")
    income_path = os.path.join(args.outdir, "futures_income.csv")
    positions_path = os.path.join(args.outdir, "futures_positions_snapshot.csv")

    write_csv(trades_path, all_trades)
    write_csv(orders_path, all_orders)
    write_csv(income_path, all_income)
    write_csv(positions_path, positions)

    print("✅ Готово.")
    print(f"  • {trades_path}")
    print(f"  • {orders_path}")
    print(f"  • {income_path}")
    print(f"  • {positions_path}")
    print("Нагадування: ключ краще робити read-only + IP whitelist.")

if __name__ == "__main__":
    main()
