from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import zlib

from app.config import AppConfig


AWG_PARAM_KEYS = ("Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4")


@dataclass(frozen=True)
class ClientArtifacts:
    client_name: str
    client_id: str
    client_ip: str
    client_private_key: str
    client_public_key: str
    server_public_key: str
    server_psk: str
    awg_params: dict[str, str]
    subnet_address: str


def build_native_conf(config: AppConfig, artifacts: ClientArtifacts) -> str:
    params_block = "\n".join(f"{key} = {artifacts.awg_params[key]}" for key in AWG_PARAM_KEYS)
    return (
        "[Interface]\n"
        f"Address = {artifacts.client_ip}/32\n"
        f"DNS = {config.primary_dns}, {config.secondary_dns}\n"
        f"PrivateKey = {artifacts.client_private_key}\n"
        f"{params_block}\n\n"
        "[Peer]\n"
        f"PublicKey = {artifacts.server_public_key}\n"
        f"PresharedKey = {artifacts.server_psk}\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        f"Endpoint = {config.server_host}:{config.server_port}\n"
        "PersistentKeepalive = 25\n"
    )


def build_vpn_uri(config: AppConfig, artifacts: ClientArtifacts, native_conf: str) -> str:
    last_config_payload = {
        **artifacts.awg_params,
        "allowed_ips": ["0.0.0.0/0", "::/0"],
        "clientId": artifacts.client_id,
        "client_ip": artifacts.client_ip,
        "client_priv_key": artifacts.client_private_key,
        "client_pub_key": artifacts.client_public_key,
        "config": native_conf,
        "hostName": config.server_host,
        "mtu": str(config.default_mtu),
        "persistent_keep_alive": "25",
        "port": config.server_port,
        "psk_key": artifacts.server_psk,
        "server_pub_key": artifacts.server_public_key,
    }
    payload = {
        "containers": [
            {
                "awg": {
                    **artifacts.awg_params,
                    "last_config": json.dumps(last_config_payload, ensure_ascii=False, indent=4) + "\n",
                    "port": str(config.server_port),
                    "subnet_address": artifacts.subnet_address,
                    "transport_proto": config.transport_proto,
                },
                "container": "amnezia-awg",
            }
        ],
        "defaultContainer": "amnezia-awg",
        "description": artifacts.client_name,
        "dns1": config.primary_dns,
        "dns2": config.secondary_dns,
        "hostName": config.server_host,
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = len(payload_bytes).to_bytes(4, byteorder="big") + zlib.compress(payload_bytes)
    return "vpn://" + base64.urlsafe_b64encode(compressed).decode("ascii")
