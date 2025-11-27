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
