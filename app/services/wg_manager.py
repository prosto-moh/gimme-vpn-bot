from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Address, ip_interface
from pathlib import Path
import re

from app.config import AppConfig
from app.services.clients_table import ClientsTableService
from app.services.config_builder import AWG_PARAM_KEYS, ClientArtifacts
from app.utils.files import (
    FileStateError,
    atomic_write_json,
    atomic_write_text,
    exclusive_lock,
    read_json_array,
    read_text_checked,
)
from app.utils.process import ProcessExecutionError, run_bash, run_command
from app.utils.time import utc_now_iso


class WgConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class GeneratedClient:
    client_record: dict
    artifacts: ClientArtifacts
    native_conf: str
    vpn_uri: str


@dataclass(frozen=True)
class ServerContext:
    interface_address: str
    subnet_address: str
    awg_params: dict[str, str]
    server_public_key: str
    server_psk: str


class WireGuardManager:
    def __init__(self, config: AppConfig, clients_table_service: ClientsTableService) -> None:
        self.config = config
        self.clients_table_service = clients_table_service

    def list_clients(self) -> list[dict]:
        return self.clients_table_service.list_clients()

    def rename_client(self, client_id: str, new_name: str) -> dict:
        with exclusive_lock(self.config.state_lock_path):
            return self.clients_table_service.rename_client(client_id, new_name)

    def revoke_client(self, client_id: str) -> dict:
        with exclusive_lock(self.config.state_lock_path):
            wg_conf = read_text_checked(self.config.wg0_path)
            current_clients = read_json_array(self.config.clients_table_path)
            updated_conf, removed = self._remove_peer_block(wg_conf, client_id)
            if not removed:
                raise WgConfigError(f"Peer with PublicKey/clientId {client_id} not found in wg0.conf.")

            remaining_clients: list[dict] = []
            deleted_client: dict | None = None
            for client in current_clients:
                if deleted_client is None and str(client.get("clientId", "")) == client_id:
                    deleted_client = client
                    continue
                remaining_clients.append(client)
            if deleted_client is None:
                raise WgConfigError(f"Client with clientId {client_id} not found in clientsTable.")

            atomic_write_text(self.config.wg0_path, updated_conf)
            atomic_write_json(self.config.clients_table_path, remaining_clients)
            try:
                self._sync_conf()
            except Exception:
                atomic_write_text(self.config.wg0_path, wg_conf)
                atomic_write_json(self.config.clients_table_path, current_clients)
                raise
            return deleted_client

    def create_client(self, owner_name: str, device_name: str) -> GeneratedClient:
        with exclusive_lock(self.config.state_lock_path):
            server_context = self._read_server_context()
            client_private_key = self._generate_private_key()
            client_public_key = self._derive_public_key(client_private_key)
            assigned_ip = self._choose_next_client_ip(self.config.wg0_path)
            client_name = f"{owner_name.strip()} - {device_name.strip()}"
            client_record = {
                "clientId": client_public_key,
                "clientName": client_name,
                "creationDate": utc_now_iso(),
                "ownerName": owner_name.strip(),
                "deviceName": device_name.strip(),
                "clientIp": assigned_ip,
            }
            peer_block = self._build_peer_block(client_public_key, server_context.server_psk, assigned_ip)

            current_conf = read_text_checked(self.config.wg0_path)
            current_clients = read_json_array(self.config.clients_table_path)
            if "[Interface]" not in current_conf:
                raise WgConfigError("wg0.conf does not contain an [Interface] section.")

            updated_conf = current_conf.rstrip() + "\n\n" + peer_block + "\n"
            updated_clients = [*current_clients, client_record]
            atomic_write_text(self.config.wg0_path, updated_conf)
            atomic_write_json(self.config.clients_table_path, updated_clients)
            try:
                self._sync_conf()
            except Exception:
                atomic_write_text(self.config.wg0_path, current_conf)
                atomic_write_json(self.config.clients_table_path, current_clients)
                raise

            artifacts = ClientArtifacts(
                client_name=client_name,
                client_id=client_public_key,
                client_ip=assigned_ip,
                client_private_key=client_private_key,
                client_public_key=client_public_key,
                server_public_key=server_context.server_public_key,
                server_psk=server_context.server_psk,
                awg_params=server_context.awg_params,
                subnet_address=server_context.subnet_address,
            )
            from app.services.config_builder import build_native_conf, build_vpn_uri

            native_conf = build_native_conf(self.config, artifacts)
            vpn_uri = build_vpn_uri(self.config, artifacts, native_conf)
            return GeneratedClient(
                client_record=client_record,
                artifacts=artifacts,
                native_conf=native_conf,
                vpn_uri=vpn_uri,
            )

    def _read_server_context(self) -> ServerContext:
        wg_conf = read_text_checked(self.config.wg0_path)
        interface_values = self._parse_interface_values(wg_conf)

        missing_keys = [key for key in AWG_PARAM_KEYS if key not in interface_values]
        if missing_keys:
            raise WgConfigError(
                f"wg0.conf [Interface] is missing required AWG parameters: {', '.join(missing_keys)}"
            )
        address = interface_values.get("Address", "").split(",")[0].strip()
        if not address:
            raise WgConfigError("wg0.conf [Interface] must contain Address.")
        interface = ip_interface(address)
        server_public_key = read_text_checked(self.config.server_public_key_path).strip()
        server_psk = read_text_checked(self.config.server_psk_path).strip()
        return ServerContext(
            interface_address=str(interface.ip),
            subnet_address=str(interface.network.network_address),
            awg_params={key: interface_values[key] for key in AWG_PARAM_KEYS},
            server_public_key=server_public_key,
            server_psk=server_psk,
        )

    def _generate_private_key(self) -> str:
        return run_command(["wg", "genkey"]).stdout.strip()

    def _derive_public_key(self, private_key: str) -> str:
        return run_command(["wg", "pubkey"], input_text=private_key + "\n").stdout.strip()

    def _choose_next_client_ip(self, wg0_path: Path) -> str:
        wg_conf = read_text_checked(wg0_path)
        interface_values = self._parse_interface_values(wg_conf)
        raw_address = interface_values.get("Address", "").split(",")[0].strip()
        if not raw_address:
            raise WgConfigError("Unable to determine Address from wg0.conf [Interface].")
        interface = ip_interface(raw_address)
        if interface.version != 4:
            raise WgConfigError("Only IPv4 Address is supported for client allocation.")

        allocated = self._extract_allocated_ipv4_addresses(wg_conf, str(interface.network.network_address))
        start_candidate = int(interface.ip) + 1
        if allocated:
            next_candidate = max(max(allocated) + 1, start_candidate)
        else:
            next_candidate = start_candidate
        candidate_ip = IPv4Address(next_candidate)
        if candidate_ip not in interface.network:
            raise WgConfigError("No free IP addresses left in the current subnet.")
        return str(candidate_ip)

    def _extract_allocated_ipv4_addresses(self, wg_conf: str, subnet_prefix: str) -> list[int]:
        pattern = re.compile(r"^\s*AllowedIPs\s*=\s*([^\n#]+)", re.MULTILINE)
        allocated: list[int] = []
        for match in pattern.finditer(wg_conf):
            values = [value.strip() for value in match.group(1).split(",")]
            for value in values:
                if not value.endswith("/32"):
                    continue
                ip = value.split("/", 1)[0].strip()
                if ip.startswith(subnet_prefix.rsplit(".", 1)[0] + "."):
                    allocated.append(int(IPv4Address(ip)))
        return allocated

    def _build_peer_block(self, client_public_key: str, server_psk: str, assigned_ip: str) -> str:
        return (
            "[Peer]\n"
            f"PublicKey = {client_public_key}\n"
            f"PresharedKey = {server_psk}\n"
            f"AllowedIPs = {assigned_ip}/32"
        )

    def _remove_peer_block(self, wg_conf: str, client_id: str) -> tuple[str, bool]:
        lines = wg_conf.splitlines()
        output: list[str] = []
        current_block: list[str] = []
        current_section: str | None = None
        removed = False

        def flush_block() -> None:
            nonlocal current_block, current_section, removed
            if not current_block:
                return
            block_text = "\n".join(current_block)
            if current_section == "Peer":
                values = self._parse_key_values(block_text)
                if values.get("PublicKey") == client_id:
                    removed = True
                else:
                    output.extend(current_block)
            else:
                output.extend(current_block)
            current_block = []
            current_section = None

        for line in lines:
            section_match = re.match(r"^\[(.+)]\s*$", line.strip())
            if section_match:
                flush_block()
                current_section = section_match.group(1)
            current_block.append(line)

        flush_block()
        cleaned = "\n".join(output).strip() + "\n"
        return cleaned, removed

    def _parse_interface_values(self, wg_conf: str) -> dict[str, str]:
        interface_block = self._extract_section(wg_conf, "Interface")
        if interface_block is None:
            raise WgConfigError("Unable to find [Interface] section in wg0.conf.")
        return self._parse_key_values(interface_block)

    def _extract_section(self, wg_conf: str, section_name: str) -> str | None:
        pattern = re.compile(
            rf"(?ms)^\[{re.escape(section_name)}\]\s*$([\s\S]*?)(?=^\[[^\]]+\]\s*$|\Z)"
        )
        match = pattern.search(wg_conf)
        if not match:
            return None
        return f"[{section_name}]\n{match.group(1).strip()}\n"

    def _parse_key_values(self, block: str) -> dict[str, str]:
        values: dict[str, str] = {}
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("[") or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def _sync_conf(self) -> None:
        try:
            run_bash(f"wg syncconf wg0 <(wg-quick strip {self.config.wg0_path})")
        except ProcessExecutionError as exc:
            raise WgConfigError(f"Failed to apply wg syncconf: {exc}") from exc
        except FileStateError as exc:
            raise WgConfigError(str(exc)) from exc
