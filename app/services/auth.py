from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class SuperuserMiddleware(BaseMiddleware):
    def __init__(self, allowed_ids: set[int]) -> None:
        self.allowed_ids = allowed_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None or user.id in self.allowed_ids:
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer("Доступ запрещен.")
            return None

        if isinstance(event, CallbackQuery):
            await event.answer("Доступ запрещен.", show_alert=True)
            return None

        return None

