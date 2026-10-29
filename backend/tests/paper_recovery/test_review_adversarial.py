import math
import random

import pytest

from services.paper_broker import PaperBroker, Position
from services.paper_trader import PaperPosition, PaperTrader
from services.paper_trading import PaperTradingEngine


def engine():
    e = PaperTradingEngine(initial_capital=1000, commission_per_contract=0)
    e.cash = 900
    e.positions = {'SPY_buy': {'symbol': 'SPY', 'side': 'buy', 'quantity': 1, 'avg_cost': 100}}
    e.trade_history = [{'symbol': 'SPY', 'side': 'buy', 'quantity': 1, 'fill_price': 100, 'commission': 0}]
    return e

@pytest.mark.parametrize('mark', [True, -1.0, float('inf'), float('nan')], ids=['boolean','negative','infinity','nan'])
def test_attribution_invalid_marks_are_unknown(mark):
    v = engine().get_pnl_attribution({'SPY': mark})
    assert v['total_unrealized_pnl'] is None, repr(v)
    assert v['unmarked_symbols'] == ['SPY']

def test_broker_missing_basis_does_not_hide_known_equity():
    b = PaperBroker()
    b.cash = 900
    b.positions['SPY'] = Position('SPY', 1, None)
    p = b.get_pnl({'SPY': 100})
    assert p['equity'] == 1000
    assert p['unrealized_pnl'] is None
    assert p['total_pnl'] is None

def test_trader_missing_basis_does_not_hide_known_equity():
    t = PaperTrader(initial_capital=1000)
    t.cash = 900
    t.positions['SPY'] = PaperPosition('SPY','LONG',1,None,'unknown')
    p = t.get_portfolio_summary({'SPY': 100})
    assert p['total_value'] == 1000
    assert p['unrealized_pnl'] is None
    assert p['total_pnl'] is None

def test_mounted_summary_exposes_unknown_observed_equity():
    p = engine().get_portfolio_summary()
    assert 'equity' in p and p['equity'] is None, repr(p)
    assert p['cost_basis_value'] == 1000

@pytest.mark.asyncio
async def test_real_portfolio_and_status_route_with_isolated_app(monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from routes import paper_trading as routes
    e = engine()
    monkeypatch.setattr(routes, '_paper_engine', e)
    app = FastAPI()
    app.include_router(routes.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/paper-trading/portfolio')
        print('PORTFOLIO', response.status_code, response.json())
        status = await client.get('/api/paper-trading/status')
        print('STATUS', status.status_code, status.json())
        attribution = await client.get('/api/paper-trading/attribution')
        print('ATTRIBUTION', attribution.status_code, attribution.json())
    assert response.status_code == status.status_code == attribution.status_code == 200
    assert response.json()['valuation_basis'] == 'historical_cost'
    assert status.json()['open_positions'] == 1
    assert attribution.json()['total_unrealized_pnl'] is None


def test_reopened_position_has_remaining_lot_cost():
    e = engine()
    e.cash = 810
    e.positions = {'SPY_buy': {'symbol': 'SPY', 'side': 'buy', 'quantity': 2, 'avg_cost': 150},
                   'SPY_sell': {'symbol': 'SPY', 'side': 'sell', 'quantity': 1, 'avg_cost': 110}}
    e.trade_history = [
        {'symbol': 'SPY', 'side': 'buy', 'quantity': 1, 'fill_price': 100, 'commission': 0},
        {'symbol': 'SPY', 'side': 'sell', 'quantity': 1, 'fill_price': 110, 'commission': 0},
        {'symbol': 'SPY', 'side': 'buy', 'quantity': 1, 'fill_price': 200, 'commission': 0},
    ]
    a = e.get_pnl_attribution({'SPY': 200})
    assert a['total_unrealized_pnl'] == 0, repr(a)


def test_zero_is_accepted_for_attribution():
    p = engine().get_pnl_attribution({'SPY': 0})
    assert p['total_unrealized_pnl'] == -100
    assert p['unmarked_symbols'] == []


@pytest.mark.parametrize('fills,mark,realized,unrealized', [
    ([('buy', 2, 100), ('sell', 1, 110), ('sell', 3, 120)], 115, 30, 10),
    ([('sell', 2, 100), ('buy', 1, 90), ('buy', 3, 80)], 85, 30, 10),
    ([('buy', 2, 100), ('buy', 2, 120), ('sell', 3, 130)], 120, 60, 10),
])
def test_open_lot_cost_survives_partial_close_and_direction_reversal(fills, mark, realized, unrealized):
    e = PaperTradingEngine(initial_capital=1000, commission_per_contract=0)
    e.trade_history = [dict(symbol='SPY', side=side, quantity=qty, fill_price=px, commission=0)
                       for side, qty, px in fills]
    result = e.get_pnl_attribution({'SPY': mark})
    assert result['total_realized_pnl'] == realized
    assert result['total_unrealized_pnl'] == unrealized


def test_mounted_summary_exposes_equity_when_explicitly_marked():
    p = engine().get_portfolio_summary({'SPY': 110})
    assert p['equity'] == 1010
    assert p['total_unrealized'] == 10
    assert p['marks_coverage'] == {'known': 1, 'missing': 0}
    assert p['basis_coverage'] == {'known': 1, 'missing': 0}


def test_reopened_summary_does_not_count_closed_lot_in_open_cost():
    e = engine()
    e.cash = 810
    e.positions = {'SPY_buy': {'symbol': 'SPY', 'side': 'buy', 'quantity': 2, 'avg_cost': 150},
                   'SPY_sell': {'symbol': 'SPY', 'side': 'sell', 'quantity': 1, 'avg_cost': 110}}
    e.trade_history = [dict(symbol='SPY', side=s, quantity=1, fill_price=p, commission=0)
                       for s, p in [('buy', 100), ('sell', 110), ('buy', 200)]]
    summary = e.get_portfolio_summary({'SPY': 200})
    assert summary['positions'][0]['avg_cost'] == 200
    assert summary['equity'] == 1010
    assert summary['total_unrealized'] == 0


def test_incomplete_fill_history_does_not_produce_full_attribution():
    e = engine()
    e.trade_history.append(dict(symbol='SPY', side='sell', quantity=1, fill_price=None, commission=0))
    result = e.get_pnl_attribution({'SPY': 110})
    assert result['total_realized_pnl'] is None
    assert result['total_unrealized_pnl'] is None
    assert result['incomplete_history_symbols'] == ['SPY']


def test_missing_commission_is_unknown_rather_than_fabricated_zero():
    e = engine()
    del e.trade_history[0]['commission']
    result = e.get_pnl_attribution({'SPY': 110})
    assert result['total_realized_pnl'] is None
    assert result['total_unrealized_pnl'] is None
    assert result['symbols'][0]['commissions'] is None


def test_mark_and_cost_basis_coverage_are_independent_in_mounted_summary():
    e = engine()
    e.positions['SPY_buy']['avg_cost'] = None
    e.trade_history = []
    result = e.get_portfolio_summary({'SPY': 110})
    assert result['equity'] == 1010
    assert result['total_unrealized'] is None
    assert result['cost_basis_value'] is None
    assert result['marks_coverage'] == {'known': 1, 'missing': 0}
    assert result['basis_coverage'] == {'known': 0, 'missing': 1}


def test_replayed_pnl_reconciles_to_cash_and_marked_positions_across_mixed_fills():
    rng = random.Random(7812)
    for _ in range(100):
        e = PaperTradingEngine(initial_capital=10000, commission_per_contract=0)
        quantities = {'SPY': 0, 'QQQ': 0}
        fees = 0.0
        marks = {'SPY': 104.5, 'QQQ': 90.25}
        for _ in range(30):
            symbol = rng.choice(list(quantities))
            side = rng.choice(['buy', 'sell'])
            quantity = rng.randint(1, 5)
            price = rng.randint(50, 150)
            fee = rng.choice([0, 0.25, 0.5])
            change = quantity if side == 'buy' else -quantity
            quantities[symbol] += change
            e.cash -= change * price + fee
            fees += fee
            e.trade_history.append(dict(symbol=symbol, side=side, quantity=quantity,
                                        fill_price=price, commission=fee))
        pnl = e.get_pnl_attribution(marks)
        equity = e.cash + sum(quantities[s] * marks[s] for s in quantities)
        reconciled = 10000 + pnl['total_realized_pnl'] + pnl['total_unrealized_pnl'] - fees
        assert equity == pytest.approx(reconciled, abs=0.02)
