from __future__ import annotations

from pathlib import Path

from app.utils.files import atomic_write_json, read_json_array


class ClientsTableService:
    def __init__(self, path: Path) -> None:
        self.path = path

    def list_clients(self) -> list[dict]:
        return read_json_array(self.path)

    def get_client(self, client_id: str) -> dict | None:
        for client in self.list_clients():
            if str(client.get("clientId", "")) == client_id:
                return client
        return None

    def append_client(self, client: dict) -> None:
        clients = self.list_clients()
        clients.append(client)
        atomic_write_json(self.path, clients)

    def rename_client(self, client_id: str, new_name: str) -> dict:
        clients = self.list_clients()
        updated: dict | None = None
        for client in clients:
            if str(client.get("clientId", "")) == client_id:
                user_data = client.get("userData")
                if not isinstance(user_data, dict):
                    user_data = {}
                    client["userData"] = user_data
                user_data["clientName"] = new_name
                updated = client
                break
        if updated is None:
            raise ValueError(f"Client not found: {client_id}")
        atomic_write_json(self.path, clients)
        return updated

    def delete_client(self, client_id: str) -> dict:
        clients = self.list_clients()
        remaining: list[dict] = []
        deleted: dict | None = None
        for client in clients:
            if deleted is None and str(client.get("clientId", "")) == client_id:
                deleted = client
                continue
            remaining.append(client)
        if deleted is None:
            raise ValueError(f"Client not found: {client_id}")
        atomic_write_json(self.path, remaining)
        return deleted

    @staticmethod
    def client_name(client: dict) -> str:
        user_data = client.get("userData")
        if isinstance(user_data, dict):
            value = user_data.get("clientName")
            if isinstance(value, str) and value.strip():
                return value.strip()
        value = client.get("clientName")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return str(client.get("clientId", "Без имени"))

    @staticmethod
    def creation_date(client: dict) -> str:
        user_data = client.get("userData")
        if isinstance(user_data, dict):
            value = user_data.get("creationDate")
            if isinstance(value, str) and value.strip():
                return value.strip()
        value = client.get("creationDate")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return "—"
