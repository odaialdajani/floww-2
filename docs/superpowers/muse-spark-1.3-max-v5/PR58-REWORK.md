# PR58 attribution rework — 2026-09-10

Reviewed remote head: 76d771784bf019cdb99c721b7d7c538e9618a79d.
Local reproduction: b9d611aa2c2b0b222296fcd9a3433841786dc7f3.
`git diff b9d611a..76d7717 -- backend/routes/alpaca.py backend/services/journal_store.py`
was empty. This is a local reproduction of identical relevant code, NOT a
claim that the entire current remote head was tested.

Command:
`/Users/nav/Documents/GitHub/floww/backend/.venv/bin/python3 /private/tmp/floww-pr58-attribution-repro.py`

The fixture inserts an open SPY call card into an in-memory DuckDB journal.
Only broker transport is mocked; its order has symbol QQQ, side sell, one filled
share and average price 400. Calling reconcile_pending_close('SPY', 'qqq-order')
produced:

```text
reconciled=True, journal_closed=1
SPY exit_price=400.0
AssertionError: QQQ order must never close SPY journal cards
exit code 1
```

Blocking: supplied symbol and broker order identity are not bound. The helper
closes all open cards for the supplied symbol. Also inspect same-symbol entry
orders, reused old close orders, option/equity distinctions and new cards opened
between repeated reconciliation attempts. Symbol matching alone is insufficient.

The first fixture used equity strike=0 and did not close its card. Source review
shows close_open_by_symbol serializes zero strike as an empty key component.
This was not a passing attribution guard; the option fixture then reproduced
the wrong-symbol mutation. Preserve this additional equity-key concern for
targeted reproduction rather than declaring it repaired.

No production changes, live broker calls or journal writes outside the in-memory
fixture. No GSD approval: this is a source/reproduction rework receipt.
A durable close-intent / exact-target schema needs an explicit architecture
contract before implementation; ambiguous legacy associations must stay pending.
