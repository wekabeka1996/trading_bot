import csv
import argparse
from datetime import datetime, timezone
from collections import defaultdict, Counter
from pathlib import Path

# Binance futures income typical fields:
# time (ms), asset, symbol, incomeType, income, info, tranId, tradeId


def ms_to_date(ms: str | int) -> str:
    try:
        ms_int = int(float(ms))
        dt = datetime.fromtimestamp(ms_int / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return "unknown"


def parse_float(x: str) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def analyze_income(csv_path: Path):
    totals_by_type = defaultdict(float)
    totals_by_symbol = defaultdict(float)
    totals_by_day = defaultdict(float)
    totals_by_day_symbol = defaultdict(float)
    totals_by_day_trading_only = defaultdict(float)

    rows = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
            income = parse_float(row.get('income') or row.get('amount') or '0')
            income_type = (row.get('incomeType') or row.get('type') or '').upper()
            symbol = row.get('symbol') or ''
            day = ms_to_date(row.get('time') or row.get('updateTime') or '0')

            totals_by_type[income_type] += income
            if symbol:
                totals_by_symbol[symbol] += income
                totals_by_day_symbol[(day, symbol)] += income
            totals_by_day[day] += income
            # trading-only excludes TRANSFER
            if income_type not in ("TRANSFER",):
                totals_by_day_trading_only[day] += income

    return {
        'totals_by_type': dict(totals_by_type),
        'totals_by_symbol': dict(totals_by_symbol),
        'totals_by_day': dict(totals_by_day),
    'totals_by_day_trading_only': dict(totals_by_day_trading_only),
        'totals_by_day_symbol': {f"{k[0]}|{k[1]}": v for k, v in totals_by_day_symbol.items()},
        'row_count': len(rows),
    }


def write_summary(summary_path: Path, data: dict):
    # Write three CSVs: by_day, by_symbol, by_type
    out_dir = summary_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    by_day_csv = out_dir / 'income_by_day.csv'
    with open(by_day_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['day', 'pnl_total'])
        for day, total in sorted(data['totals_by_day'].items()):
            w.writerow([day, f"{total:.8f}"])

    by_day_trading_csv = out_dir / 'income_by_day_trading_only.csv'
    with open(by_day_trading_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['day', 'pnl_trading_only'])
        for day, total in sorted(data['totals_by_day_trading_only'].items()):
            w.writerow([day, f"{total:.8f}"])

    by_symbol_csv = out_dir / 'income_by_symbol.csv'
    with open(by_symbol_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['symbol', 'pnl_total'])
        for sym, total in sorted(data['totals_by_symbol'].items(), key=lambda x: abs(x[1]), reverse=True):
            w.writerow([sym, f"{total:.8f}"])

    by_type_csv = out_dir / 'income_by_type.csv'
    with open(by_type_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['incomeType', 'total'])
        for t, total in sorted(data['totals_by_type'].items()):
            w.writerow([t, f"{total:.8f}"])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Analyze Binance futures income CSV and produce summaries')
    p.add_argument('csv_path', type=str, help='Path to futures_income.csv')
    p.add_argument('--outdir', type=str, default='export_out', help='Where to write summary CSVs')
    args = p.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        raise SystemExit(f"File not found: {csv_path}")

    data = analyze_income(csv_path)
    # Print concise console summary
    print(f"Rows: {data['row_count']}")
    total = sum(data['totals_by_day'].values())
    trading_total = sum(data['totals_by_day_trading_only'].values())
    print(f"Total PnL (all types): {total:.8f}")
    print(f"Trading PnL (no TRANSFER): {trading_total:.8f}")

    # Top 10 symbols by absolute PnL
    top_symbols = sorted(data['totals_by_symbol'].items(), key=lambda x: abs(x[1]), reverse=True)[:10]
    print('\nTop symbols by |PnL|:')
    for sym, val in top_symbols:
        print(f"  {sym:<12} {val:.8f}")

    # Type breakdown
    print('\nBy incomeType:')
    for t, val in sorted(data['totals_by_type'].items()):
        print(f"  {t:<18} {val:.8f}")

    # Write summaries
    outdir = Path(args.outdir)
    write_summary(outdir / 'income_summary.txt', data)
    print(f"\nCSV summaries written to: {outdir}")
