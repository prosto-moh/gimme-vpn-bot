from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import os


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Environment variable {name} is required.")
    return value


def _parse_superusers(raw: str) -> tuple[int, ...]:
    ids: list[int] = []
    for chunk in raw.split(","):
        item = chunk.strip()
        if not item:
            continue
        try:
            ids.append(int(item))
        except ValueError as exc:
            raise ValueError("SUPERUSER_TG_IDS must contain comma-separated integers.") from exc
    if not ids:
        raise ValueError("SUPERUSER_TG_IDS must not be empty.")
    return tuple(ids)


@dataclass(frozen=True)
class AppConfig:
    bot_token: str
    superuser_tg_ids: tuple[int, ...]
    wg0_path: Path
    clients_table_path: Path
    server_public_key_path: Path
    server_psk_path: Path
    primary_dns: str
    secondary_dns: str
    server_host: str
    server_port: int
    transport_proto: str
    default_mtu: int

    @property
    def state_lock_path(self) -> Path:
        return self.wg0_path.with_suffix(f"{self.wg0_path.suffix}.bot.lock")


def load_config() -> AppConfig:
    load_dotenv()

    return AppConfig(
        bot_token=_require_env("BOT_TOKEN"),
        superuser_tg_ids=_parse_superusers(_require_env("SUPERUSER_TG_IDS")),
        wg0_path=Path(_require_env("WG0_PATH")),
        clients_table_path=Path(_require_env("CLIENTS_TABLE_PATH")),
        server_public_key_path=Path(_require_env("SERVER_PUBLIC_KEY_PATH")),
        server_psk_path=Path(_require_env("SERVER_PSK_PATH")),
        primary_dns=_require_env("PRIMARY_DNS"),
        secondary_dns=_require_env("SECONDARY_DNS"),
        server_host=_require_env("SERVER_HOST"),
        server_port=int(_require_env("SERVER_PORT")),
        transport_proto=_require_env("TRANSPORT_PROTO"),
        default_mtu=int(_require_env("DEFAULT_MTU")),
    )

