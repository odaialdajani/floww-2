"""Regression test: gex_history iterates Motor cursors with async for."""
import inspect
import re

import pytest


def test_gex_history_uses_async_for_on_cursors():
    """The bars_cur and chains_cur loops must be async for, not sync for."""
    import services.gex_history as gh
    src = inspect.getsource(gh)
    # No sync iteration on the *_cur variables (check `for b in` not preceded by `async`)
    assert not re.search(r'(?<!async )for b in bars_cur', src), \
        "bars_cur must be iterated with `async for`"
    assert not re.search(r'(?<!async )for chain in chains_cur', src), \
        "chains_cur must be iterated with `async for`"
    # And the async version IS present
    assert 'async for b in bars_cur' in src, \
        "async for b in bars_cur not found"
    assert 'async for chain in chains_cur' in src, \
        "async for chain in chains_cur not found"
