# dashboard_db.py PRO
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "trades.db"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# INIT DB + INDEXES (PRO)
# ---------------------------------------------------------------------------
def init_db():
    """Initialise la DB + index optimisés."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Table deals (alignée sur history_sync._save_deals_to_db)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id TEXT PRIMARY KEY,
            platform TEXT,
            type TEXT,
            time TEXT,
            broker_time TEXT,
            commission REAL,
            swap REAL,
            profit REAL,
            symbol TEXT,
            magic INTEGER,
            order_id TEXT,
            position_id TEXT,
            reason TEXT,
            broker_comment TEXT,
            entry_type TEXT,
            volume REAL,
            price REAL,
            stop_loss REAL,
            take_profit REAL,
            account_currency_exchangeRate REAL
        )
    """)

    # Index PRO
    cur.execute("CREATE INDEX IF NOT EXISTS idx_time ON deals(time)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_symbol ON deals(symbol)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_profit ON deals(profit)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entry_type ON deals(entry_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_type ON deals(type)")

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Helpers de filtre (exclure BALANCE / CREDIT / CHARGE des stats)
# ---------------------------------------------------------------------------
# Liste des types qu'on NE veut PAS compter dans les stats de trading
NON_TRADE_TYPES = (
    "DEAL_TYPE_BALANCE",
    "DEAL_TYPE_CREDIT",
    "DEAL_TYPE_CHARGE",
    "DEAL_TYPE_CORRECTION",
)


def _trade_type_filter_sql(alias: str = "deals") -> str:
    """
    Retourne un bout de clause SQL pour exclure les non-trades.
    alias: nom de la table (utile si on fait des JOIN plus tard).
    """
    return (
        f"AND ({alias}.type IS NULL "
        f"OR {alias}.type NOT IN ({', '.join(['?' for _ in NON_TRADE_TYPES])}))"
    )


def _build_params_with_types(base_params: list) -> list:
    """Ajoute NON_TRADE_TYPES à la liste de paramètres SQL."""
    return [*base_params, *NON_TRADE_TYPES]


# ---------------------------------------------------------------------------
# SUMMARY ANALYTICS PRO
# ---------------------------------------------------------------------------
def summary_from_db(days: int = 30, symbol: Optional[str] = None) -> Dict[str, Any]:
    conn = get_db_connection()
    cur = conn.cursor()

    from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    base_params: List[Any] = [from_date]
    symbol_filter = ""

    if symbol:
        symbol_filter = "AND symbol = ?"
        base_params.append(symbol.upper())

    # ---------- PnL global ----------
    sql_pnl = f"""
        SELECT 
          COUNT(*) as nb_deals,
          SUM(profit) as pnl_total,
          AVG(profit) as avg_profit
        FROM deals
        WHERE time >= ?
          {symbol_filter}
          AND profit IS NOT NULL
          {_trade_type_filter_sql('deals')}
    """
    params = _build_params_with_types(base_params)
    cur.execute(sql_pnl, params)
    row = cur.fetchone()

    nb_deals = row["nb_deals"] or 0
    pnl_total = round(row["pnl_total"], 2) if row["pnl_total"] is not None else 0
    avg_profit = round(row["avg_profit"], 2) if row["avg_profit"] is not None else 0

    # ---------- Winrate (sorties uniquement) ----------
    sql_wr = f"""
        SELECT
          SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
          SUM(CASE WHEN profit <= 0 THEN 1 ELSE 0 END) as losses
        FROM deals
        WHERE time >= ?
          {symbol_filter}
          AND profit IS NOT NULL
          AND entry_type IN ('DEAL_ENTRY_OUT', NULL)
          {_trade_type_filter_sql('deals')}
    """
    cur.execute(sql_wr, params)
    row = cur.fetchone()
    wins = row["wins"] or 0
    losses = row["losses"] or 0
    total_closed = wins + losses
    winrate = round((wins / total_closed) * 100, 2) if total_closed > 0 else 0

    # ---------- Top symbols ----------
    sql_top = f"""
        SELECT symbol, COUNT(*) as n, SUM(profit) as pnl
        FROM deals
        WHERE time >= ?
          AND profit IS NOT NULL
          {_trade_type_filter_sql('deals')}
        GROUP BY symbol
        ORDER BY pnl DESC
        LIMIT 5
    """
    # ici on ne filtre pas par symbol (top global)
    params_top = _build_params_with_types([from_date])
    cur.execute(sql_top, params_top)

    top_symbols = [
        {
            "symbol": r["symbol"],
            "nb_deals": r["n"],
            "pnl": round(r["pnl"], 2) if r["pnl"] is not None else 0,
        }
        for r in cur.fetchall()
        if r["symbol"] is not None
    ]

    conn.close()

    return {
        "period_days": days,
        "symbol_filter": symbol.upper() if symbol else None,
        "nb_deals": nb_deals,
        "pnl_total": pnl_total,
        "avg_profit": avg_profit,
        "wins": wins,
        "losses": losses,
        "winrate": winrate,
        "top_symbols": top_symbols,
    }


# ---------------------------------------------------------------------------
# EQUITY CURVE / PNL BY DAY PRO
# ---------------------------------------------------------------------------
def pnl_by_day_from_db(days: int = 30, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()

    from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    base_params: List[Any] = [from_date]
    symbol_filter = ""

    if symbol:
        symbol_filter = "AND symbol = ?"
        base_params.append(symbol.upper())

    sql = f"""
        SELECT 
            substr(time, 1, 10) as day,
            SUM(profit) as pnl
        FROM deals
        WHERE time >= ?
          {symbol_filter}
          AND profit IS NOT NULL
          {_trade_type_filter_sql('deals')}
        GROUP BY day
        ORDER BY day ASC
    """
    params = _build_params_with_types(base_params)
    cur.execute(sql, params)

    rows = cur.fetchall()
    conn.close()

    return [
        {
            "day": r["day"],
            "pnl": round(r["pnl"], 2) if r["pnl"] is not None else 0,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# LISTE DES DEALS (pour le tableau "Derniers trades")
# ---------------------------------------------------------------------------
def list_deals_from_db(
    days: int = 30,
    symbol: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    conn = get_db_connection()
    cur = conn.cursor()

    from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    params: List[Any] = [from_date]
    symbol_filter = ""

    if symbol:
        symbol_filter = "AND symbol = ?"
        params.append(symbol.upper())

    # total pour pagination
    cur.execute(
        f"SELECT COUNT(*) as total FROM deals WHERE time >= ? {symbol_filter}",
        params,
    )
    total = cur.fetchone()["total"]

    # liste paginée
    cur.execute(
        f"""
        SELECT id, platform, type, symbol, time, broker_time,
               volume, price, profit, entry_type, reason,
               order_id, position_id, stop_loss, take_profit,
               broker_comment, account_currency_exchangeRate
        FROM deals
        WHERE time >= ?
          {symbol_filter}
        ORDER BY time DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    )

    rows = cur.fetchall()
    conn.close()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [dict(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# DRAWDOWN (courbe equity + drawdown %)
# ---------------------------------------------------------------------------
def drawdown_from_db(
    days: int = 30,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calcule la courbe de drawdown à partir de la PNL journalière.
    Retourne:
    {
      "period_days": ...,
      "symbol_filter": ...,
      "items": [{ "day": "2025-01-01", "equity": 123.45, "drawdown": -5.67 }, ...],
      "max_drawdown": -12.34
    }
    """
    daily = pnl_by_day_from_db(days=days, symbol=symbol)

    equity: List[float] = []
    dd: List[float] = []
    running_equity = 0.0
    running_peak = 0.0
    max_drawdown = 0.0

    for d in daily:
        pnl = d["pnl"] or 0.0
        running_equity += pnl
        if running_equity > running_peak:
            running_peak = running_equity

        if running_peak > 0:
            drawdown_pct = (running_equity - running_peak) / running_peak * 100.0
        else:
            drawdown_pct = 0.0

        max_drawdown = min(max_drawdown, drawdown_pct)
        equity.append(running_equity)
        dd.append(drawdown_pct)

    items = []
    for i, d in enumerate(daily):
        items.append(
            {
                "day": d["day"],
                "equity": round(equity[i], 2),
                "drawdown": round(dd[i], 2),
            }
        )

    return {
        "period_days": days,
        "symbol_filter": symbol.upper() if symbol else None,
        "items": items,
        "max_drawdown": round(max_drawdown, 2),
    }


# ---------------------------------------------------------------------------
# PNL MENSUELLE
# ---------------------------------------------------------------------------
def monthly_performance_from_db(
    days: int = 180,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    PNL agrégé par mois.
    {
      "period_days": ...,
      "symbol_filter": ...,
      "items": [
        {"month": "2025-01", "pnl": 1234.56},
        ...
      ]
    }
    """
    conn = get_db_connection()
    cur = conn.cursor()

    from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    base_params: List[Any] = [from_date]
    symbol_filter = ""

    if symbol:
        symbol_filter = "AND symbol = ?"
        base_params.append(symbol.upper())

    sql = f"""
        SELECT
            substr(time, 1, 7) as month,
            SUM(profit) as pnl
        FROM deals
        WHERE time >= ?
          {symbol_filter}
          AND profit IS NOT NULL
          {_trade_type_filter_sql('deals')}
        GROUP BY month
        ORDER BY month ASC
    """

    params: List[Any] = _build_params_with_types(base_params)
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    items = []
    for r in rows:
        month = r["month"]
        pnl = r["pnl"] if r["pnl"] is not None else 0.0
        items.append({"month": month, "pnl": round(pnl, 2)})

    return {
        "period_days": days,
        "symbol_filter": symbol.upper() if symbol else None,
        "items": items,
    }


# ---------------------------------------------------------------------------
# STATS PAR SYMBOLE
# ---------------------------------------------------------------------------
def symbol_stats_from_db(
    days: int = 90,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stats par symbole:
    {
      "period_days": ...,
      "symbol_filter": ...,
      "items": [
        {"symbol": "XAUUSD", "trades": 10, "pnl": 1234.0, "winrate": 70.0},
        ...
      ]
    }
    """
    conn = get_db_connection()
    cur = conn.cursor()

    from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    base_params: List[Any] = [from_date]
    symbol_filter = ""

    if symbol:
        symbol_filter = "AND symbol = ?"
        base_params.append(symbol.upper())

    sql = f"""
        SELECT
            symbol,
            COUNT(*) as trades,
            SUM(profit) as pnl,
            SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN profit <= 0 THEN 1 ELSE 0 END) as losses
        FROM deals
        WHERE time >= ?
          {symbol_filter}
          AND profit IS NOT NULL
          {_trade_type_filter_sql('deals')}
        GROUP BY symbol
        HAVING symbol IS NOT NULL
        ORDER BY pnl DESC
    """

    params: List[Any] = _build_params_with_types(base_params)
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    items: List[Dict[str, Any]] = []
    for r in rows:
        trades = r["trades"] or 0
        pnl = r["pnl"] if r["pnl"] is not None else 0.0
        wins = r["wins"] or 0
        losses = r["losses"] or 0
        total = wins + losses
        winrate = (wins / total * 100.0) if total > 0 else 0.0

        items.append(
            {
                "symbol": r["symbol"],
                "trades": trades,
                "pnl": round(pnl, 2),
                "winrate": round(winrate, 2),
            }
        )

    return {
        "period_days": days,
        "symbol_filter": symbol.upper() if symbol else None,
        "items": items,
    }
