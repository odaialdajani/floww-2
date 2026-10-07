import json
from datetime import timedelta

from test_related_price_series import NOW, payload

from routes.related_tickers import build_snapshot, registry_related
from services.related_price_series import RelatedSeriesStore, validate_daily_payload


def registry(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "coverage": {"complete": False},
                "products": [
                    {
                        "symbol": "UPAA",
                        "underlying": "AAA",
                        "benchmark": None,
                        "issuer": "Issuer",
                        "product_type": "single_stock_etf",
                        "daily_target": 2,
                        "reset": "daily",
                        "source_urls": ["https://issuer.example/upaa"],
                        "verified_at": "2026-10-07",
                    },
                    {
                        "symbol": "DNAA",
                        "underlying": "AAA",
                        "benchmark": None,
                        "issuer": "Issuer",
                        "product_type": "single_stock_etf",
                        "daily_target": -1,
                        "reset": "daily",
                        "source_urls": ["https://issuer.example/dnaa"],
                        "verified_at": "2026-10-07",
                    },
                    {
                        "symbol": "QQQ",
                        "underlying": None,
                        "benchmark": "NASDAQ100",
                        "issuer": "Issuer",
                        "product_type": "benchmark_etf",
                        "daily_target": 1,
                        "reset": "none",
                        "source_urls": ["https://issuer.example/qqq"],
                        "verified_at": "2026-10-07",
                    },
                    {
                        "symbol": "SQQQ",
                        "underlying": None,
                        "benchmark": "NASDAQ100",
                        "issuer": "Issuer",
                        "product_type": "benchmark_etf",
                        "daily_target": -3,
                        "reset": "daily",
                        "source_urls": ["https://issuer.example/sqqq"],
                        "verified_at": "2026-10-07",
                    },
                ],
            }
        ),
        encoding="utf8",
    )
    return path


def cat(names):
    return {"available": True, "stale": False, "asof": "2026-10-07T12:00:00Z", "symbols": names}


def test_verified_reverse_relationships_include_underlying_and_siblings_without_prefix_guesses(tmp_path):
    path = registry(tmp_path)
    rows, coverage = registry_related("UPAA", cat(["AAA", "UPAA", "DNAA"]), registry_path=path)
    assert {r["symbol"] for r in rows} == {"AAA", "DNAA"}
    assert all(r["provider_listed"] is True for r in rows)
    assert coverage["complete"] is False
    rows, _ = registry_related("QQQ", cat(["QQQ", "SQQQ"]), registry_path=path)
    assert [r["symbol"] for r in rows] == ["SQQQ"]
    rows, _ = registry_related("AAAUP", cat(["AAAUP", "UPAA"]), registry_path=path)
    assert not rows


def test_all_scope_uses_every_cached_provider_equity_not_only_option_enabled_names(tmp_path):
    store = RelatedSeriesStore(tmp_path / "never-created.sqlite3")
    result = build_snapshot(
        "AAA",
        window=30,
        scope="all",
        store=store,
        catalog=cat(["AAA", "BBB", "NOOPT"]),
        registry_path=registry(tmp_path),
        now=NOW,
    )
    assert result["coverage"]["eligible"] == 2 and result["coverage"]["pending"] == 2
    assert {r["symbol"] for r in result["comparisons"]} == {"BBB", "NOOPT"}
    assert all(r["coefficient"] is None for r in result["comparisons"])
    assert not (tmp_path / "never-created.sqlite3").exists()


def test_rankings_use_actual_paired_return_counts_and_keep_unknowns_separate(tmp_path):
    store = RelatedSeriesStore(tmp_path / "cache.sqlite3")
    for symbol in ("AAA", "BBB"):
        assert store.save(validate_daily_payload(symbol, payload(symbol), now=NOW, received_at=NOW), now=NOW)
    result = build_snapshot(
        "AAA",
        window=90,
        scope="all",
        store=store,
        catalog=cat(["AAA", "BBB", "UNKNOWN"]),
        registry_path=registry(tmp_path),
        now=NOW,
    )
    assert (
        result["coverage"]["eligible"] == 2 and result["coverage"]["usable"] == 1 and result["coverage"]["partial"] == 1
    )
    assert result["positive"][0]["paired_returns"] == 30 and result["positive"][0]["requested_returns"] == 90
    assert result["coverage"]["complete"] is False
    assert next(r for r in result["comparisons"] if r["symbol"] == "UNKNOWN")["coefficient"] is None
    store.close()


def test_pagination_is_bounded_and_a_missing_registry_is_explicit(tmp_path):
    result = build_snapshot(
        "AAA",
        scope="all",
        limit=2,
        offset=2,
        store=RelatedSeriesStore(":memory:"),
        catalog=cat(["AAA", "BBB", "CCC", "DDD", "EEE"]),
        registry_path=tmp_path / "missing.json",
        now=NOW,
    )
    assert len(result["comparisons"]) == 2 and result["comparisons_total"] == 4
    assert result["registry_coverage"]["available"] is False


def test_missing_directory_and_caret_index_are_unavailable_without_substituting_a_proxy(tmp_path):
    result = build_snapshot(
        "^NDX", scope="all", store=RelatedSeriesStore(":memory:"), catalog=cat(["QQQ", "SPY"]), now=NOW
    )
    assert result["status"] == "unavailable" and result["reason"] == "unsupported_symbol" and not result["comparisons"]
    result = build_snapshot(
        "AAA",
        scope="all",
        store=RelatedSeriesStore(":memory:"),
        catalog={"available": False, "stale": True, "symbols": []},
        now=NOW,
    )
    assert result["reason"] == "provider_directory_unavailable" and result["coverage"]["complete"] is False
