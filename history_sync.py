# history_sync.py – SIMPLE, STABLE, RPC-ONLY (Option 1)
import json
import logging
import asyncio
from datetime import datetime

import dashboard_db as db
from metaapi_client import MetaApiClient

logger = logging.getLogger("history_sync")


# ---------------------------------------------------------
# FETCH RPC DEALS — Version stable, filtrage anti-chaînes
# ---------------------------------------------------------
async def fetch_rpc_deals(start, end, client):
    """
    Récupère les deals via RPC (get_deals_by_time_range)
    et les normalise en une liste Python de deals dict.
    Compatible avec mt_bot.py.
    """

    try:
        # Appel RPC officiel (la seule bonne méthode)
        raw = await client.connection.get_deals_by_time_range(
            start_time=start,
            end_time=end
        )

        # MetaApi RPC renvoie PARFOIS :
        # - un dict python déjà propre
        # - une string JSON (selon transport WebSocket)
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception as err:
                logger.error(f"❌ JSON RPC invalide : {err} → raw={raw}")
                return []

        # LOGIQUE IDENTIQUE À mt_bot.py
        if isinstance(raw, dict) and "deals" in raw:
            return raw["deals"]

        elif isinstance(raw, list):
            return raw

        else:
            logger.warning(f"⚠ Format RPC inattendu: {type(raw)} → {raw}")
            return []

    except Exception as e:
        logger.error(f"❌ RPC fetch failed: {e}")
        return []
    

# ---------------------------------------------------------
# SAVE IN DB
# ---------------------------------------------------------
def save_deals_to_db(deals):
    conn = db.get_db_connection()
    cur = conn.cursor()
    inserted = 0

    for deal in deals:
        if not isinstance(deal, dict):
            logger.warning(f"Deal non dict ignoré: {deal}")
            continue

        deal_id = deal.get("id")
        if not deal_id:
            logger.warning(f"Deal sans id ignoré: {deal}")
            continue

        try:
            cur.execute("""
                INSERT OR REPLACE INTO deals (
                    id, platform, type, time, broker_time, commission, swap, 
                    profit, symbol, magic, order_id, position_id, reason, 
                    broker_comment, entry_type, volume, price, stop_loss, 
                    take_profit, account_currency_exchangeRate 
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                            ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                deal.get("id"),
                deal.get("platform"),
                deal.get("type"),
                deal.get("time"),
                deal.get("brokerTime"),
                deal.get("commission"),
                deal.get("swap"),
                deal.get("profit"),
                deal.get("symbol"),
                deal.get("magic"),
                deal.get("orderId"),
                deal.get("positionId"),
                deal.get("reason"),
                deal.get("brokerComment"),
                deal.get("entryType"),
                deal.get("volume"),
                deal.get("price"),
                deal.get("stopLoss"),
                deal.get("takeProfit"),
                deal.get("accountCurrencyExchangeRate"),
                #"default",  # ou ton vrai account_id
            ))
            inserted += 1

        except Exception as e:
            logger.error(f"Échec insertion DB: {e}")

    conn.commit()
    conn.close()
    return inserted


# ---------------------------------------------------------
# FULL SYNC — OPTION 1 : simple, direct
# ---------------------------------------------------------
def full_sync_history(meta_client: MetaApiClient):
    logger.info("🚀 FULL SYNC — SIMPLE (Option 1)")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # récupère tout l’historique en 1 appel
    START = datetime(2000, 1, 1)
    END = datetime.utcnow()

    deals = loop.run_until_complete(fetch_rpc_deals(START, END, meta_client))
    loop.close()

    logger.info(f"→ {len(deals)} deals reçus")

    inserted = save_deals_to_db(deals)
    logger.info(f"✔ {inserted} deals insérés dans la base")

    return inserted



# ---------------------------------------------------------
# INCREMENTAL SYNC — simple et propre
# ---------------------------------------------------------
def incremental_sync_history(meta_client: MetaApiClient):
    logger.info("🔄 INCREMENTAL SYNC")

    conn = db.get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT MAX(time) AS last FROM deals")
    row = cur.fetchone()
    conn.close()

    if not row or not row["last"]:
        logger.info("⚠ Aucun historique — démarrage FULL SYNC")
        return full_sync_history(meta_client)

    start = datetime.fromisoformat(row["last"])
    end = datetime.utcnow()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    deals = loop.run_until_complete(fetch_rpc_deals(start, end, meta_client))
    loop.close()

    inserted = save_deals_to_db(deals)
    logger.info(f"✔ INCREMENTAL SYNC — {inserted} deals ajoutés")

    return inserted
