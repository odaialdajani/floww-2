"""B20 flow. Synthetic only."""
def test_buckets():
    from services.chart_flow import bucket_hash, bucketize
    assert bucket_hash("b", "w", {"x": 1}) == bucket_hash("b", "w", {"x": 1})
    out = bucketize([{"side": "call", "premium": 100}, {"side": "put", "premium": 40}, {"side": "?", "premium": 5}])
    assert out["call_premium"] == 100
    assert out["put_premium"] == -40
    assert out["unknown"] == 1
    assert out["top"][0]["premium"] == 100
