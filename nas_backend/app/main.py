from __future__ import annotations

import logging
import signal

from .ai import AIProvider
from .bridge_client import BridgeClient
from .config import Settings
from .database import Database
from .service import BotService


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    database = Database(settings.database_path)
    bridge = BridgeClient(settings.bridge_url, settings.bridge_key)
    ai = AIProvider(settings)
    service = BotService(settings, database, bridge, ai)

    def stop_service(*_: object) -> None:
        service.stop()

    signal.signal(signal.SIGTERM, stop_service)
    signal.signal(signal.SIGINT, stop_service)
    service.run_forever()


if __name__ == "__main__":
    main()

