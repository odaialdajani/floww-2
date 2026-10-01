"""Finite offline exporter to NEW evidence; the historical R11 packet is untouched."""
import json
import socket
from pathlib import Path
from unittest.mock import patch

import httpx

from r11_fixture import generate

ROOT = Path(__file__).resolve().parents[1]
ATTEMPTS = []


def refuse(*args, **kwargs):
    ATTEMPTS.append("external transport")
    raise AssertionError("Fixture exporter attempted external transport")


async def refuse_async(*args, **kwargs):
    refuse()


def export():
    ATTEMPTS.clear()
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex

    def local(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original(sock, address)
        refuse()

    def local_ex(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_ex(sock, address)
        refuse()

    with patch.object(socket.socket, "connect", local), \
         patch.object(socket.socket, "connect_ex", local_ex), \
         patch.object(httpx.HTTPTransport, "handle_request", refuse), \
         patch.object(httpx.AsyncHTTPTransport, "handle_async_request", refuse_async):
        packet = generate()
        packet["secondary_display"] = generate("QQQ", 400)["display"]
        packet["next_display"] = generate(expiry_scope="next")["display"]
    assert not ATTEMPTS, "A provider seam was missed; blocked attempts cannot be swallowed"
    destination = ROOT / "docs/solstice/r13/evidence/vertical-fixture.json"
    destination.write_text(json.dumps(packet, indent=2, default=str, allow_nan=False) + "\n")
    print(f"Wrote {destination.relative_to(ROOT)}; provider transports blocked; no lifespan")


if __name__ == "__main__":
    export()
