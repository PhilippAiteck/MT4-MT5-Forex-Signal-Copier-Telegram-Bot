# metaapi_client.py (RPC léger – sans streaming)
import asyncio
import threading
import logging
from metaapi_cloud_sdk import MetaApi

logger = logging.getLogger(__name__)

class MetaApiClient:
    def __init__(self, api_key: str, account_id: str):
        self.api_key = api_key
        self.account_id = account_id
        self.api = None
        self.account = None
        self.connection = None

        self._connected = False
        self.loop = None

    async def connect_async(self):
        logger.info("Initialisation MetaApi...")

        self.api = MetaApi(self.api_key)
        self.account = await self.api.metatrader_account_api.get_account(self.account_id)

        if self.account.state not in ["DEPLOYING", "DEPLOYED"]:
            await self.account.deploy()

        await self.account.wait_connected()

        self.connection = self.account.get_rpc_connection()
        await self.connection.connect()

        # très important : attendre la synchro RPC
        await self.connection.wait_synchronized()

        self._connected = True
        logger.info("MetaApi RPC READY ✔️")

    def connect_threaded(self):
        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.connect_async())
            self.loop.run_forever()

        t = threading.Thread(target=run, daemon=True)
        t.start()

    def get_open_positions(self):
        if not self._connected or not self.loop:
            return []

        try:
            future = asyncio.run_coroutine_threadsafe(
                self.connection.get_positions(),
                self.loop
            )
            return future.result(timeout=10)
        except Exception as e:
            logger.error(f"Erreur get_open_positions: {e}")
            return []
