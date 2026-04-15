from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import load_config
from app.handlers import router
from app.services.auth import SuperuserMiddleware
from app.services.clients_table import ClientsTableService
from app.services.wg_manager import WireGuardManager


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    config = load_config()
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher(storage=MemoryStorage())

    clients_table_service = ClientsTableService(config.clients_table_path)
    wg_manager = WireGuardManager(config, clients_table_service)

    dispatcher["wg_manager"] = wg_manager
    middleware = SuperuserMiddleware(set(config.superuser_tg_ids))
    dispatcher.message.middleware(middleware)
    dispatcher.callback_query.middleware(middleware)
    dispatcher.include_router(router)

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
