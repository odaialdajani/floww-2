import sys, os, threading, collections, traceback
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
import duckdb
from services.heatseeker_snapshots import (
    create_snapshot_table, contracts_to_recordbatch, bulk_insert,
    get_latest_snapshot, get_top_movers_from_db, get_history,
)

conn = duckdb.connect(":memory:")
create_snapshot_table(conn)

# two snapshots of 400 contracts each for SPY
import time
for snap in range(2):
    chain = {"ticker": "SPY", "contracts": [
        {"expiry": "2026-09-19", "strike": 400.0 + i, "type": "C",
         "oi": 1000 + i + snap*10, "volume": 500 + i, "iv": 0.2,
         "delta": 0.5, "gamma": 0.02} for i in range(400)]}
    bulk_insert(conn, contracts_to_recordbatch(chain))
    time.sleep(0.01)

# baseline single-threaded truth
truth_latest = len(get_latest_snapshot(conn, "SPY"))
truth_movers = len(get_top_movers_from_db(conn, "SPY", top_n=10))
print("single-threaded baseline: latest rows =", truth_latest, " movers =", truth_movers)

N_THREADS = 6
N_ITER = 20
latest_counts = collections.Counter()
movers_counts = collections.Counter()
errors = []

def worker_latest():
    for _ in range(N_ITER):
        try:
            latest_counts[len(get_latest_snapshot(conn, "SPY"))] += 1
        except Exception as e:
            errors.append(repr(e))

def worker_movers():
    for _ in range(N_ITER):
        try:
            movers_counts[len(get_top_movers_from_db(conn, "SPY", top_n=10))] += 1
        except Exception as e:
            errors.append(repr(e))

ts = [threading.Thread(target=worker_latest) for _ in range(N_THREADS)] + \
     [threading.Thread(target=worker_movers) for _ in range(N_THREADS)]
for t in ts: t.start()
for t in ts: t.join()

print("UNLOCKED shared conn, 6+6 threads x", N_ITER)
print("  /latest   row-count distribution:", dict(latest_counts), "-> wrong:",
      sum(v for k, v in latest_counts.items() if k != truth_latest), "/", sum(latest_counts.values()))
print("  /movers   row-count distribution:", dict(movers_counts), "-> wrong:",
      sum(v for k, v in movers_counts.items() if k != truth_movers), "/", sum(movers_counts.values()))
print("  exceptions:", len(errors), errors[:3])
