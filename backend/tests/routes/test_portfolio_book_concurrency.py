"""Stored-book deletion must reject stale reads and concurrent changes."""

import copy
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from routes.portfolio import router


@pytest.fixture
def book_api(monkeypatch):
    class Books:
        def __init__(self):
            self.book = {"name": "main", "positions": [
                {"symbol": "SPY", "quantity": 0, "entry_price": None},
                {"symbol": "QQQ", "quantity": -2, "entry_price": 1.5},
            ]}
            self.writes = []
            self.before_update = None

        async def find_one(self, query, projection=None):
            return copy.deepcopy(self.book)

        async def update_one(self, query, update):
            if self.before_update:
                self.before_update()
            matched = all(self.book.get(key) == value for key, value in query.items())
            if matched:
                self.book.update(copy.deepcopy(update["$set"]))
                self.writes.append(copy.deepcopy(update))
            return SimpleNamespace(matched_count=int(matched))

    books = Books()
    summary = AsyncMock(return_value={"name": "main", "positions": 2, "pnl": {"total_pnl": None}})
    monkeypatch.setitem(sys.modules, "server", SimpleNamespace(
        db=SimpleNamespace(portfolios=books), calc_portfolio_summary=summary,
    ))
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app, books, summary


@pytest.mark.asyncio
async def test_read_supplies_revision_without_changing_stored_rows(book_api):
    app, books, _ = book_api
    before = copy.deepcopy(books.book)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        raw = (await client.get("/api/portfolio/main")).json()
        priced = (await client.get("/api/portfolio/main?spot=100")).json()
    assert len(raw["book_revision"]) == 64
    assert priced["book_revision"] == raw["book_revision"]
    assert priced["pnl"]["total_pnl"] is None
    assert raw["positions"] == before["positions"]
    assert books.book == before
    assert books.writes == []


@pytest.mark.asyncio
async def test_unconditional_delete_is_refused(book_api):
    app, books, _ = book_api
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.delete("/api/portfolio/main/position/0")
    assert response.status_code == 428
    assert len(books.book["positions"]) == 2
    assert books.writes == []


@pytest.mark.asyncio
async def test_unchanged_book_can_remove_the_displayed_row(book_api):
    app, books, _ = book_api
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        revision = (await client.get("/api/portfolio/main")).json()["book_revision"]
        response = await client.delete("/api/portfolio/main/position/1", params={"expected_revision": revision})
    assert response.status_code == 200
    assert books.book["positions"] == [{"symbol": "SPY", "quantity": 0, "entry_price": None}]
    assert len(books.writes) == 1


@pytest.mark.asyncio
async def test_after_display_reorder_cannot_delete_another_row(book_api):
    app, books, _ = book_api
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        revision = (await client.get("/api/portfolio/main")).json()["book_revision"]
        books.book["positions"].reverse()
        response = await client.delete("/api/portfolio/main/position/0", params={"expected_revision": revision})
    assert response.status_code == 409
    assert [row["symbol"] for row in books.book["positions"]] == ["QQQ", "SPY"]
    assert books.writes == []


@pytest.mark.asyncio
async def test_concurrent_change_between_server_read_and_write_is_preserved(book_api):
    app, books, _ = book_api
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        revision = (await client.get("/api/portfolio/main")).json()["book_revision"]
        books.before_update = lambda: books.book["positions"].append({"symbol": "NEW", "quantity": 1})
        response = await client.delete("/api/portfolio/main/position/0", params={"expected_revision": revision})
    assert response.status_code == 409
    assert [row["symbol"] for row in books.book["positions"]] == ["SPY", "QQQ", "NEW"]
    assert books.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("positions", [None, {}, "unavailable"])
async def test_malformed_book_is_never_treated_as_empty(book_api, positions):
    app, books, _ = book_api
    books.book["positions"] = positions
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.get("/api/portfolio/main")
    assert response.status_code == 503
    assert books.writes == []
