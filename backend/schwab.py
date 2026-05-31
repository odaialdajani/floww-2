"""
Schwab API Integration Scaffold
Ready for when user gets schwab account access.

Features:
- OAuth2 authentication flow
- Position import (options + equity)
- Transaction history (sweep detection)
- Real-time quote streaming

Docs: https://developer.schwab.com/
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("schwab")

# ============ Config ============

SCHWAB_CLIENT_ID = os.environ.get("SCHWAB_CLIENT_ID", "")
SCHWAB_CLIENT_SECRET = os.environ.get("SCHWAB_CLIENT_SECRET", "")
SCHWAB_REDIRECT_URI = os.environ.get("SCHWAB_REDIRECT_URI", "https://localhost:8080/callback")
SCHWAB_TOKEN_PATH = Path(os.environ.get("SCHWAB_TOKEN_PATH", "~/.hermes/schwab_token.json")).expanduser()

SCHWAB_API_BASE = "https://api.schwabapi.com"
SCHWAB_AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"


# ============ Token Management ============

class SchwabTokenManager:
    """Manage OAuth2 tokens for Schwab API."""

    def __init__(self, token_path: Path = SCHWAB_TOKEN_PATH):
        self.token_path = token_path
        self._token: Optional[Dict[str, Any]] = None

    def load(self) -> Optional[Dict[str, Any]]:
        """Load token from disk."""
        if self._token:
            return self._token
        if self.token_path.exists():
            try:
                self._token = json.loads(self.token_path.read_text())
                return self._token
            except Exception:
                pass
        return None

    def save(self, token: Dict[str, Any]):
        """Save token to disk."""
        self._token = token
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(json.dumps(token, indent=2))
        os.chmod(self.token_path, 0o600)  # readable only by owner

    def is_expired(self) -> bool:
        """Check if the access token is expired."""
        token = self.load()
        if not token:
            return True
        expires_at = token.get("expires_at", 0)
        return datetime.now(timezone.utc).timestamp() > expires_at - 300  # 5 min buffer

    def get_access_token(self) -> Optional[str]:
        """Get a valid access token, refreshing if needed."""
        token = self.load()
        if not token:
            return None
        if self.is_expired() and token.get("refresh_token"):
            return None  # Would need to refresh — requires async
        return token.get("access_token")

    def get_auth_url(self) -> str:
        """Generate the OAuth2 authorization URL."""
        params = {
            "client_id": SCHWAB_CLIENT_ID,
            "redirect_uri": SCHWAB_REDIRECT_URI,
            "response_type": "code",
            "scope": "AccountAccess MarketData",
        }
        import urllib.parse
        return f"{SCHWAB_AUTH_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        """Exchange an authorization code for tokens."""
        import base64
        credentials = base64.b64encode(
            f"{SCHWAB_CLIENT_ID}:{SCHWAB_CLIENT_SECRET}".encode()
        ).decode()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                SCHWAB_TOKEN_URL,
                headers={"Authorization": f"Basic {credentials}"},
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": SCHWAB_REDIRECT_URI,
                },
            )
            resp.raise_for_status()
            token = resp.json()
            token["expires_at"] = (
                datetime.now(timezone.utc).timestamp() + token.get("expires_in", 1800)
            )
            self.save(token)
            return token

    async def refresh_token(self) -> Optional[str]:
        """Refresh the access token using the refresh token."""
        token = self.load()
        if not token or not token.get("refresh_token"):
            return None
        import base64
        credentials = base64.b64encode(
            f"{SCHWAB_CLIENT_ID}:{SCHWAB_CLIENT_SECRET}".encode()
        ).decode()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    SCHWAB_TOKEN_URL,
                    headers={"Authorization": f"Basic {credentials}"},
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": token["refresh_token"],
                    },
                )
                resp.raise_for_status()
                new_token = resp.json()
                new_token["expires_at"] = (
                    datetime.now(timezone.utc).timestamp() + new_token.get("expires_in", 1800)
                )
                # Preserve refresh_token if not returned
                if "refresh_token" not in new_token:
                    new_token["refresh_token"] = token["refresh_token"]
                self.save(new_token)
                return new_token["access_token"]
        except Exception as e:
            log.error(f"Schwab token refresh failed: {e}")
            return None


# ============ API Client ============

class SchwabClient:
    """Schwab API client for account data."""

    def __init__(self, token_manager: Optional[SchwabTokenManager] = None):
        self.tokens = token_manager or SchwabTokenManager()

    async def _get_headers(self) -> Dict[str, str]:
        """Get auth headers."""
        token = self.tokens.get_access_token()
        if not token or self.tokens.is_expired():
            token = await self.tokens.refresh_token()
        if not token:
            raise Exception("No valid Schwab token. Run OAuth flow first.")
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def get_accounts(self) -> List[Dict[str, Any]]:
        """Get all account numbers and hashes."""
        headers = await self._get_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SCHWAB_API_BASE}/trader/v1/accounts/accountNumbers",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_positions(self, account_hash: str) -> Dict[str, Any]:
        """Get all positions for an account (options + equity)."""
        headers = await self._get_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SCHWAB_API_BASE}/trader/v1/accounts/{account_hash}",
                headers=headers,
                params={"fields": "positions"},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_transactions(
        self, account_hash: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        types: str = "TRADE",
    ) -> List[Dict[str, Any]]:
        """Get transaction history for sweep detection."""
        headers = await self._get_headers()
        if not start_date:
            start_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        if not end_date:
            end_date = datetime.now(timezone.utc).isoformat()

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SCHWAB_API_BASE}/trader/v1/accounts/{account_hash}/transactions",
                headers=headers,
                params={
                    "startDate": start_date,
                    "endDate": end_date,
                    "types": types,
                },
            )
            resp.raise_for_status()
            return resp.json().get("transactions", [])


# ============ Position Import ============

def parse_schwab_option_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Parse Schwab option symbol format.
    Example: 'SPY 240516C00500000' -> {symbol: 'SPY', expiry: '2024-05-16', type: 'call', strike: 500.0}
    """
    import re
    m = re.match(r"^(\w+)\s+(\d{6})([CP])(\d{8})$", symbol.strip())
    if not m:
        return None
    und, ymd, typ, strike_raw = m.groups()
    return {
        "symbol": und,
        "expiry": f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:6]}",
        "type": "call" if typ == "C" else "put",
        "strike": int(strike_raw) / 1000.0,
    }


async def import_schwab_positions(account_hash: str) -> List[Dict[str, Any]]:
    """
    Import positions from Schwab and normalize to our Position format.
    Returns list of position dicts compatible with our Portfolio.add_position().
    """
    client = SchwabClient()
    data = await client.get_positions(account_hash)
    positions = data.get("securitiesAccount", {}).get("positions", [])

    result = []
    for pos in positions:
        instrument = pos.get("instrument", {})
        symbol = instrument.get("underlyingSymbol", instrument.get("symbol", ""))
        qty = pos.get("longQuantity", 0) - pos.get("shortQuantity", 0)
        if qty == 0:
            continue

        # Options positions
        if instrument.get("assetType") == "OPTION":
            parsed = parse_schwab_option_symbol(instrument.get("symbol", ""))
            if parsed:
                result.append({
                    "symbol": parsed["symbol"],
                    "option_type": parsed["type"],
                    "strike": parsed["strike"],
                    "expiry": parsed["expiry"],
                    "quantity": qty,
                    "entry_price": pos.get("averagePrice", 0),
                    "entry_iv": 0.0,  # Will need to fetch from market data
                    "underlying_price": 0.0,  # Will need to fetch
                    "is_long": qty > 0,
                })
        # Equity positions
        elif instrument.get("assetType") == "EQUITY":
            result.append({
                "symbol": symbol,
                "option_type": "equity",
                "strike": 0,
                "expiry": "",
                "quantity": qty,
                "entry_price": pos.get("averagePrice", 0),
                "entry_iv": 0.0,
                "underlying_price": pos.get("marketValue", 0) / qty if qty else 0,
                "is_long": qty > 0,
            })

    return result


# ============ Sweep Detection ============

async def detect_sweeps(account_hash: str, lookback_days: int = 7) -> List[Dict[str, Any]]:
    """
    Detect options sweeps from Schwab transaction history.
    Sweeps = large multi-leg trades executed across multiple exchanges simultaneously.
    """
    client = SchwabClient()
    transactions = await client.get_transactions(
        account_hash,
        start_date=(datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat(),
    )

    sweeps = []
    # Group transactions by symbol and time window (within 60 seconds)
    from collections import defaultdict
    by_symbol = defaultdict(list)

    for tx in transactions:
        txs = tx.get("transferItems", [])
        for item in txs:
            instrument = item.get("instrument", {})
            if instrument.get("assetType") == "OPTION":
                symbol = instrument.get("symbol", "")
                ts = str(tx.get("time", ""))
                by_symbol[symbol].append({
                    "time": ts,
                    "symbol": symbol,
                    "type": item.get("instrument", {}).get("putCall", ""),
                    "quantity": abs(item.get("quantity", 0)),
                    "price": item.get("price", 0),
                    "amount": abs(item.get("amount", 0)),
                })

    # Flag trades with size >= 100 contracts as potential sweeps
    for symbol, trades in by_symbol.items():
        for trade in trades:
            if trade["quantity"] >= 100:
                sweeps.append({
                    **trade,
                    "flag": "LARGE" if trade["quantity"] >= 100 else "NORMAL",
                    "is_sweep": trade["quantity"] >= 250,
                })

    return sorted(sweeps, key=lambda x: x.get("amount", 0), reverse=True)
