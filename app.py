# app.py
import os
import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from telegram import Bot, Update
from telegram.ext import Dispatcher

from metaapi_client import MetaApiClient
from config import API_KEY, ACCOUNT_ID, TOKEN, APP_URL

import mt_bot                  # ton bot existant
import dashboard_db as db      # module DB/analytics
from history_sync import full_sync_history, incremental_sync_history

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- MetaApi RPC client ---
META = MetaApiClient(api_key=API_KEY, account_id=ACCOUNT_ID)

# Intervalle de sync incrémentale en secondes
INCREMENTAL_SYNC_INTERVAL = int(os.getenv("INCREMENTAL_SYNC_INTERVAL", "60"))

# URL publique de l'app (Railway / ngrok) pour le webhook Telegram
#APP_URL = os.getenv("APP_URL", "").strip()

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

    # 6) (optionnel) Setup automatique du webhook Telegram si APP_URL est configuré
    if APP_URL:
        webhook_url = f"{APP_URL.rstrip('/')}/telegram/webhook"
        try:
            bot.set_webhook(webhook_url)
            logger.info(f"✅ Webhook Telegram configuré automatiquement sur {webhook_url}")
        except Exception as e:
            logger.error(f"❌ Impossible de configurer automatiquement le webhook Telegram: {e}")
    else:
        logger.warning("⚠ APP_URL non défini → webhook Telegram non configuré automatiquement.")


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
# ENDPOINT POUR SETUP MANUEL DU WEBHOOK (Railway)
# ---------------------------------------------------------------------------
@app.get("/setup-webhook")
def setup_webhook():
    """
    À appeler UNE FOIS après déploiement si besoin :
      GET https://.../setup-webhook

    Utilise APP_URL pour définir l'URL du webhook Telegram.
    """
    if not APP_URL:
        raise HTTPException(
            status_code=500,
            detail="APP_URL n'est pas configuré dans les variables d'environnement",
        )

    webhook_url = f"{APP_URL.rstrip('/')}/telegram/webhook"
    try:
        bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook Telegram configuré sur {webhook_url}")
        return {"ok": True, "webhook_url": webhook_url}
    except Exception as e:
        logger.error(f"❌ Erreur lors du setup webhook Telegram: {e}")
        raise HTTPException(
            status_code=500,
            detail="Impossible de configurer le webhook Telegram",
        )


# ---------------------------------------------------------------------------
# DASHBOARD HTML
# ---------------------------------------------------------------------------
@app.get("/")
def dashboard_page():
    return FileResponse("dashboard/index.html")


# ---------------------------------------------------------------------------
# ENDPOINTS API DASHBOARD → délégués à dashboard_db
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
def api_deals(
    days: int = Query(30, ge=1, le=365),
    symbol: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    return db.list_deals_from_db(days=days, symbol=symbol, limit=limit, offset=offset)


@app.get("/api/drawdown")
def api_drawdown(
    days: int = Query(30, ge=1, le=365),
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    return db.drawdown_from_db(days=days, symbol=symbol)


@app.get("/api/monthly-performance")
def api_monthly_performance(
    days: int = Query(180, ge=1, le=730),
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    return db.monthly_performance_from_db(days=days, symbol=symbol)


@app.get("/api/symbol-stats")
def api_symbol_stats(
    days: int = Query(90, ge=1, le=365),
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    return db.symbol_stats_from_db(days=days, symbol=symbol)


# ---------------------------------------------------------------------------
# POSITIONS OUVERTES (LIVE) VIA METAAPI
# ---------------------------------------------------------------------------
@app.get("/api/open-trades")
async def api_open_trades(symbol: Optional[str] = None) -> Dict[str, Any]:
    """
    Retourne les positions ouvertes (live) depuis MetaAPI.
    - Utilise exclusivement META.get_open_positions() (wrapper RPC existant)
    - Peut filtrer par symbole via ?symbol=XAUUSD
    - Expose `profit`, `unrealizedProfit` et `displayProfit` pour le dashboard
    """
    if not META._connected:
        return {
            "count": 0,
            "items": [],
            "status": "MetaApi not connected yet",
        }

    try:
        # ⇨ appel à ton wrapper RPC existant (aucune nouvelle méthode MetaApi)
        positions = META.get_open_positions()
    except Exception as e:
        logger.error(f"Erreur MetaApi get_open_positions: {e}")
        raise HTTPException(
            status_code=500,
            detail="MetaApi error while fetching open positions",
        )

    filtered: List[Dict[str, Any]] = []
    symbol_filter = symbol.upper() if symbol else None

    for p in positions:
        pos = dict(p)

        sym = (pos.get("symbol") or "").upper()
        if symbol_filter and sym != symbol_filter:
            continue

        unreal = pos.get("unrealizedProfit")
        raw_profit = pos.get("profit")
        display_profit = unreal if unreal is not None else raw_profit

        filtered.append(
            {
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
            }
        )

    # Trier par time décroissant (les plus récents en haut)
    filtered.sort(key=lambda x: x.get("time") or "", reverse=True)

    return {
        "count": len(filtered),
        "symbol_filter": symbol_filter,
        "items": filtered,
        "status": "ok",
    }
