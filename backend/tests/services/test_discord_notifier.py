import logging

import httpx
import pytest

from services.discord_notifier import DiscordNotifier


@pytest.mark.asyncio
async def test_environment_does_not_activate_notifier(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test/secret")
    notifier = DiscordNotifier()
    assert not notifier.available
    assert not await notifier.send_alert("test", "message")


@pytest.mark.asyncio
async def test_explicit_send_preserves_unknowns_and_blocks_mentions(caplog):
    caplog.set_level(logging.INFO)
    captured = []

    def handler(request):
        import json
        captured.append(json.loads(request.content))
        return httpx.Response(204)

    async with httpx.MockTransport(handler) as transport:
        notifier = DiscordNotifier("https://discord.com/api/webhooks/test/secret", transport=transport)
        assert await notifier.send_position_alert(
            "STOP_LOSS", "SPY", "LONG", 1.5, 10, None, None, None, "@everyone", severity="CRITICAL",
        )
    payload = captured[0]
    assert payload["allowed_mentions"] == {"parse": []}
    fields = {f["name"]: f["value"] for f in payload["embeds"][0]["fields"]}
    assert fields["Current"] == "Unavailable"
    assert fields["P&L"] == "Unavailable"
    assert fields["Qty"] == "1.5"
    assert "secret" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 429, 500])
async def test_failed_send_is_false_without_retry(status):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, text="secret should not be logged")
    async with httpx.MockTransport(handler) as transport:
        notifier = DiscordNotifier("https://discord.com/api/webhooks/test/secret", transport=transport)
        assert not await notifier.send_alert("test", "message")
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_network_error_does_not_expose_webhook(caplog):
    def handler(request):
        raise httpx.ConnectError("secret-url", request=request)
    async with httpx.MockTransport(handler) as transport:
        notifier = DiscordNotifier("https://discord.com/api/webhooks/test/secret", transport=transport)
        assert not await notifier.send_alert("test", "message")
    assert "secret-url" not in caplog.text


def test_embed_has_bounded_total_text_and_unknown_number():
    payload = DiscordNotifier.build_payload("x" * 1000, "y" * 5000,
        fields=[{"name": "n" * 500, "value": "v" * 2000}] * 30, footer="f" * 3000)
    embed = payload["embeds"][0]
    size = len(embed["title"]) + len(embed["description"]) + len(embed.get("footer", {}).get("text", ""))
    size += sum(len(f["name"]) + len(f["value"]) for f in embed.get("fields", []))
    assert size <= 6000
    assert len(embed.get("fields", [])) <= 25
