"""Owned in-memory alert fixtures using actual production save/read functions.

No market refresh or production-store claim. Frozen clocks affect only this
isolated evaluation process while the synchronous fixture operation holds a lock.
"""
from __future__ import annotations

import copy
import math
import os
import threading
from contextlib import ExitStack
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

_CLOCK_LOCK = threading.RLock()
_LABELS = {'controlled_empty_alerts': 'CONTROLLED_EMPTY_STORE',
           'controlled_alert_error': 'CONTROLLED_QUERY_FAILURE',
           'derived_alerts_unknown': 'DERIVED_FROM_RECORDED_PUBLIC_CHAINS',
           'synthetic_alerts_positive': 'SYNTHETIC_CONTRACT_TEST',
           'unbound': 'NO_RECORDED_ALERT_STORE_SUPPLIED'}


class AlertFixture:
    def __init__(self, item):
        self.item = copy.deepcopy(item)
        self.mode = self.item['alerts']['mode']
        if self.mode not in _LABELS:
            raise ValueError('Unknown alert fixture mode')
        self.label = _LABELS[self.mode]
        if self.mode == 'synthetic_alerts_positive':
            params = self.item['alerts'].get('parameters', {})
            if set(params) - {'variant', 'rows'}:
                raise ValueError('Unknown synthetic alert parameter')
            if not self.item.get('chains'):
                raise ValueError('Positive alert fixture requires ticker scope')
        self.at = datetime.fromisoformat(item['clock']['at'].replace('Z', '+00:00'))
        if self.at.utcoffset() is None:
            raise ValueError('Alert clock requires timezone')
        self.receipts = []
        self.population = []
        self.engine = None
        self.cleanup = ExitStack()

    def __enter__(self):
        # The module's incidental singleton must also be in-memory on first
        # import. The actual fixture below always owns a separate connection.
        with patch.dict(os.environ, {'DUCKDB_PATH': ':memory:'}):
            from services import flow_alerts, public_scanner, research_data_seam
            from services.duckdb_engine import DuckDBEngine
        self.fa, self.scanner, self.seam = flow_alerts, public_scanner, research_data_seam
        self.engine = DuckDBEngine(':memory:')
        self.cleanup.callback(self.engine.close)
        try:
            if self.mode not in {'controlled_alert_error', 'unbound'}:
                self.fa.init_flow_alert_tables(self.engine)
            with _CLOCK_LOCK, self.frozen():
                self.populate()
        except BaseException:
            self.cleanup.close()
            self.engine = None
            raise
        return self

    def frozen(self):
        at = self.at
        class ClockType(type):
            def __instancecheck__(cls, instance):
                # DuckDB returns ordinary datetimes, not this clock subclass.
                return isinstance(instance, datetime)
        class Frozen(datetime, metaclass=ClockType):
            @classmethod
            def now(cls, tz=None):
                return at.astimezone(tz) if tz is not None else at.replace(tzinfo=None)
        stack = ExitStack()
        stack.enter_context(patch.object(self.fa, 'datetime', Frozen))
        stack.enter_context(patch.object(self.seam, 'datetime', Frozen))
        return stack

    def populate(self):
        for ticker, chain in self.item.get('chains', {}).items():
            alerts = []
            scanned = None
            if self.mode == 'derived_alerts_unknown':
                rows, extras = self.scanner.unusual_rows_from_chain(chain, now=self.at.timestamp())
                normalized = self.fa.norm_rows(rows)
                self.fa.apply_quote_truth(normalized, extras)
                alerts = self.fa.eval_institutional(normalized)
                scanned = len(rows)
            elif self.mode == 'synthetic_alerts_positive':
                params = self.item['alerts'].get('parameters', {})
                variant = params.get('variant', 'mixed')
                if variant not in {'mixed', 'aligned_bullish'}:
                    raise ValueError('Unknown synthetic alert variant')
                directions = [('bullish', 80), ('bearish', 40)] if variant == 'mixed' else [('bullish', 80), ('bullish', 60)]
                for i, (bias, conviction) in enumerate(directions):
                    alerts.append({'key': f'synthetic-{ticker}-{i}', 'rule': 'SYNTHETIC_CONTRACT_TEST',
                                   'tier': 'TEST', 'under': ticker, 'bias': bias, 'conviction': conviction,
                                   'exp': '2026-10-02',
                                   'asof': self.at.astimezone(ZoneInfo('America/New_York')).isoformat(),
                                   'context': {'source_quality': 'ok',
                                               'source': 'SYNTHETIC_CONTRACT_TEST',
                                               'source_event_time': f'2026-09-28T14:29:{30 + i * 10}Z'}})
                if 'rows' in params:
                    alerts = copy.deepcopy(params['rows'])
                    if not isinstance(alerts, list) or len(alerts) != 2 or any(a.get('under') != ticker for a in alerts):
                        raise ValueError('Synthetic rows require the declared two-row ticker scope')
            if self.mode == 'synthetic_alerts_positive':
                self.validate_positive(alerts, ticker, variant)
            if alerts:
                count = self.fa.persist_alerts(self.engine, alerts, snapshot_date=self.at.date().isoformat())
                self.population.append({'ticker': ticker, 'scan_rows': scanned, 'persisted_rows': count,
                                        'label': self.label, 'optional_live_inputs': 'Not supplied: historical baselines, regimes, calibration, desk pass'})

    def validate_positive(self, rows, ticker, variant):
        if not isinstance(rows, list) or len(rows) != 2 or any(not isinstance(row, dict) for row in rows):
            raise ValueError('Positive fixture requires two explicit rows')
        keys, biases, observed_times = set(), [], []
        for row in rows:
            key, value = row.get('key'), row.get('conviction')
            if not isinstance(key, str) or not key or key in keys or row.get('under') != ticker:
                raise ValueError('Positive rows require distinct keys and matching ticker')
            keys.add(key)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100 or value != int(value):
                raise ValueError('Positive conviction must be an integer within0to100')
            context = row.get('context')
            if not isinstance(context, dict) or context.get('source_quality') != 'ok':
                raise ValueError('Synthetic positive source quality missing')
            labels = [context[k] for k in ('source', 'fixture_source') if k in context]
            if not labels or any(label != 'SYNTHETIC_CONTRACT_TEST' for label in labels):
                raise ValueError('Positive rows must be explicitly labeled synthetic')
            try:
                observed = datetime.fromisoformat(context['source_event_time'].replace('Z', '+00:00'))
                created = datetime.fromisoformat(row['asof'].replace('Z', '+00:00'))
                valid = (observed.utcoffset() is not None and created.utcoffset() is not None
                         and observed <= created <= self.at and 0 <= (self.at - observed).total_seconds() <= 900
                         # Legacy alert storage strips the zone and reads ET wall time.
                         and created.utcoffset() == created.astimezone(ZoneInfo('America/New_York')).utcoffset())
            except (KeyError, TypeError, AttributeError, ValueError):
                valid = False
            if not valid:
                raise ValueError('Positive source and creation times must be aware, ordered and current')
            observed_times.append(observed)
            biases.append(str(row.get('bias')).lower())
        expected = ['bearish', 'bullish'] if variant == 'mixed' else ['bullish', 'bullish']
        if sorted(biases) != expected or (max(observed_times) - min(observed_times)).total_seconds() > 120:
            raise ValueError('Positive rows disagree with declared direction or coherence')

    def query(self, sql, params):
        receipt = {'ticker': params[0], 'params': list(params), 'query': sql,
                   'label': self.label, 'clock': self.at.isoformat(), 'status': 'entered', 'rows': None}
        self.receipts.append(receipt)
        try:
            rows = self.engine.query_strict(sql, params)
        except Exception as exc:
            receipt.update(status='error', error_class=type(exc).__name__)
            raise
        receipt.update(status='ok', rows=len(rows))
        return rows

    def read(self, ticker):
        if self.engine is None:
            raise RuntimeError('Alert fixture is not open')
        if self.mode == 'unbound':
            raise RuntimeError('No recorded alert store was supplied; absence is unknown')
        with _CLOCK_LOCK, self.frozen():
            return self.seam.stored_research_alerts(self.query, ticker)

    def __exit__(self, *exc):
        self.cleanup.close()
        self.engine = None
