# app.py
import os
import logging
import time
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from telegram import Bot, Update
from telegram.ext import Dispatcher

from metaapi_client import MetaApiClient
from config import API_KEY, ACCOUNT_ID, TOKEN

import mt_bot                  # ton bot existant
import dashboard_db as db      # module DB/analytics
from history_sync import full_sync_history, incremental_sync_history

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- MetaApi RPC client ---
META = MetaApiClient(api_key=API_KEY, account_id=ACCOUNT_ID)

# Intervalle de sync incrémentale en secondes (configurable via env si tu veux)
INCREMENTAL_SYNC_INTERVAL = int(os.getenv("INCREMENTAL_SYNC_INTERVAL", "60"))

# --- FastAPI app ---
app = FastAPI(title="Aiteck Bot + Dashboard", version="1.0.0")
app.mount("/dashboard", StaticFiles(directory="dashboard"), name="dashboard")

# --- Telegram ---
bot = Bot(TOKEN)
dispatcher = Dispatcher(bot, None, workers=0, use_context=True)
mt_bot.setup_dispatcher(dispatcher)   # on branche tous les handlers existants


# ---------------------------------------------------------------------------
# TÂCHE BACKGROUND : SYNC INCRÉMENTALE PÉRIODIQUE
# ---------------------------------------------------------------------------
async def incremental_sync_worker():
    """
    Tâche périodique en arrière-plan :
    - appelle incremental_sync_history(META)
    - attend INCREMENTAL_SYNC_INTERVAL secondes
    - recommence en boucle
    """
    logger.info(
        f"🚀 Tâche de sync incrémentale démarrée "
        f"(toutes les {INCREMENTAL_SYNC_INTERVAL}s)"
    )

    while True:
        try:
            if not META._connected:
                logger.warning("⏳ MetaApi non connecté, skip de la sync incrémentale.")
            else:
                logger.info("⏱ Lancement incremental_sync_history()")
                # on déplace le travail lourd dans un thread pour ne pas bloquer l'event loop
                await asyncio.to_thread(incremental_sync_history, META)
                logger.info("✅ incremental_sync_history() terminé")
        except Exception as e:
            logger.error(f"❌ Erreur dans incremental_sync_history(): {e}")

        await asyncio.sleep(INCREMENTAL_SYNC_INTERVAL)


# ---------------------------------------------------------------------------
# ÉVÉNEMENTS FASTAPI
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    # 1) Init DB + index
    db.init_db()

    # 2) Connexion MetaApi RPC
    META.connect_threaded()

    # 3) Attendre la connexion RPC (petit retry)
    for _ in range(25):
        if META._connected:
            break
        await asyncio.sleep(0.5)

    if not META._connected:
        logger.error("❌ MetaApi RPC n’a pas pu se connecter.")
        return

    # 4) FULL SYNC si DB vide, sinon on ne fait rien (on laisse l'incrémentale bosser)
    conn = db.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM deals")
    count = cur.fetchone()["c"]
    conn.close()

    if count == 0:
        logger.info("Aucune donnée locale → FULL SYNC")
        # full_sync_history peut être lourd → on le lance dans un thread
        await asyncio.to_thread(full_sync_history, META)
    else:
        logger.info("Données déjà présentes → pas de FULL SYNC")

    # 5) Démarrer la tâche de sync incrémentale en arrière-plan
    app.state.sync_task = asyncio.create_task(incremental_sync_worker())


@app.on_event("shutdown")
async def on_shutdown():
    """
    On arrête proprement la tâche background quand l'app se ferme.
    """
    task = getattr(app.state, "sync_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("🔚 Tâche de sync incrémentale arrêtée proprement.")


# ---------------------------------------------------------------------------
# WEBHOOK TELEGRAM
# ---------------------------------------------------------------------------
@app.post("/telegram/webhook")
def telegram_webhook(update: dict):
    """
    Endpoint synchrone pour le webhook Telegram.
    FastAPI parse automatiquement le JSON du body en dict `update`.
    """
    try:
        tg_update = Update.de_json(update, bot)
        dispatcher.process_update(tg_update)
    except Exception as e:
        logger.error(f"Erreur dans telegram_webhook: {e}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# DASHBOARD HTML
# ---------------------------------------------------------------------------
@app.get("/dashboard")
def dashboard_page():
    return FileResponse("dashboard/index.html")


# ---------------------------------------------------------------------------
# ENDPOINTS API DASHBOARD
# ---------------------------------------------------------------------------
@app.get("/api/summary")
def api_summary(
    days: int = Query(30, ge=1, le=365),
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    return db.summary_from_db(days=days, symbol=symbol)


@app.get("/api/pnl-by-day")
def api_pnl_by_day(
    days: int = Query(30, ge=1, le=365),
    symbol: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return db.pnl_by_day_from_db(days=days, symbol=symbol)


@app.get("/api/deals")
def list_deals(
    days: int = Query(30, ge=1, le=365),
    symbol: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    conn = db.get_db_connection()
    cur = conn.cursor()

    from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    params: List[Any] = [from_date]
    symbol_filter = ""

    if symbol:
        symbol_filter = "AND symbol = ?"
        params.append(symbol.upper())

    cur.execute(
        f"SELECT COUNT(*) as total FROM deals WHERE time >= ? {symbol_filter}",
        params,
    )
    total = cur.fetchone()["total"]

    cur.execute(
        f"""
        SELECT id, platform, type, symbol, time, broker_time,
               volume, price, profit, entry_type, reason,
               order_id, position_id, stop_loss, take_profit
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


@app.get("/api/open-trades")
async def api_open_trades(symbol: Optional[str] = None) -> Dict[str, Any]:
    """
    Retourne les positions ouvertes (live) depuis MetaAPI.
    - Utilise exclusivement META.get_open_positions() (wrapper RPC existant)
    - Peut filtrer par symbole via ?symbol=XAUUSD
    - Expose à la fois `profit` et `unrealizedProfit`, plus un `displayProfit` pour le dashboard
    """
    if not META._connected:
        return {
            "count": 0,
            "items": [],
            "status": "MetaApi not connected yet"
        }

    try:
        # ⇨ appel à ton wrapper RPC existant (aucune nouvelle méthode MetaApi)
        positions = META.get_open_positions()
    except Exception as e:
        logger.error(f"Erreur MetaApi get_open_positions: {e}")
        # Réponse claire pour le frontend
        raise HTTPException(status_code=500, detail="MetaApi error while fetching open positions")

    filtered: List[Dict[str, Any]] = []
    symbol_filter = symbol.upper() if symbol else None

    for p in positions:
        # some impls renvoient des objets, d'autres déjà des dicts
        pos = dict(p)

        sym = (pos.get("symbol") or "").upper()
        if symbol_filter and sym != symbol_filter:
            continue

        # Profit d'affichage : on privilégie unrealizedProfit, sinon profit
        unreal = pos.get("unrealizedProfit")
        raw_profit = pos.get("profit")
        display_profit = unreal if unreal is not None else raw_profit

        filtered.append({
            "id": pos.get("id"),
            "symbol": pos.get("symbol"),
            "type": pos.get("type"),
            "volume": pos.get("volume"),
            "openPrice": pos.get("openPrice"),
            "profit": raw_profit,
            "unrealizedProfit": unreal,
            "displayProfit": display_profit,
            "swap": pos.get("swap"),
            "commission": pos.get("commission"),
            "time": pos.get("updateTime") or pos.get("time"),
            "stopLoss": pos.get("stopLoss"),
            "takeProfit": pos.get("takeProfit"),
        })

    # Trier par time décroissant (les plus récents en haut)
    filtered.sort(key=lambda x: x.get("time") or "", reverse=True)

    return {
        "count": len(filtered),
        "symbol_filter": symbol_filter,
        "items": filtered,
        "status": "ok"
    }

# --- Endpoints analytics supplémentaires pour le dashboard PRO ---


@app.get("/api/drawdown")
def api_drawdown(
    days: int = Query(30, ge=1, le=365),
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calcule la courbe de drawdown à partir de la PNL journalière.
    Retourne un format : {"items": [{day, equity, drawdown}], "max_drawdown": ..., ...}
    """
    # On réutilise la PNL journalière déjà filtrée (symbol + NON_TRADE_TYPES)
    daily = db.pnl_by_day_from_db(days=days, symbol=symbol)

    equity = []
    dd = []
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


@app.get("/api/monthly-performance")
def api_monthly_performance(
    days: int = Query(180, ge=1, le=730),
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    PNL agrégé par mois.
    Format retourné:
    {
      "period_days": ...,
      "symbol_filter": ...,
      "items": [
        {"month": "2025-01", "pnl": 1234.56},
        ...
      ]
    }
    """
    conn = db.get_db_connection()
    cur = conn.cursor()

    from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    base_params: List[Any] = [from_date]
    symbol_filter = ""

    if symbol:
        symbol_filter = "AND symbol = ?"
        base_params.append(symbol.upper())

    # On exclut les NON_TRADE_TYPES (BALANCE, CREDIT, etc.)
    non_trade_placeholders = ", ".join(["?" for _ in db.NON_TRADE_TYPES])

    sql = f"""
        SELECT
            substr(time, 1, 7) as month,
            SUM(profit) as pnl
        FROM deals
        WHERE time >= ?
          {symbol_filter}
          AND profit IS NOT NULL
          AND (type IS NULL OR type NOT IN ({non_trade_placeholders}))
        GROUP BY month
        ORDER BY month ASC
    """

    params: List[Any] = [*base_params, *db.NON_TRADE_TYPES]
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


@app.get("/api/symbol-stats")
def api_symbol_stats(
    days: int = Query(90, ge=1, le=365),
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stats par symbole:
    - trades = nombre de deals
    - pnl = somme des profits
    - winrate = % de trades gagnants
    Format:
    {
      "period_days": ...,
      "symbol_filter": ...,
      "items": [
        {"symbol": "XAUUSD", "trades": 10, "pnl": 1234.0, "winrate": 70.0},
        ...
      ]
    }
    """
    conn = db.get_db_connection()
    cur = conn.cursor()

    from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    base_params: List[Any] = [from_date]
    symbol_filter = ""

    if symbol:
        symbol_filter = "AND symbol = ?"
        base_params.append(symbol.upper())

    non_trade_placeholders = ", ".join(["?" for _ in db.NON_TRADE_TYPES])

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
          AND (type IS NULL OR type NOT IN ({non_trade_placeholders}))
        GROUP BY symbol
        HAVING symbol IS NOT NULL
        ORDER BY pnl DESC
    """

    params: List[Any] = [*base_params, *db.NON_TRADE_TYPES]
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
