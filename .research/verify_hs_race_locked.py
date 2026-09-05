import sys, os, threading, collections, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
import duckdb
from services.heatseeker_snapshots import (
    create_snapshot_table, contracts_to_recordbatch, bulk_insert,
    get_latest_snapshot, get_top_movers_from_db)

conn = duckdb.connect(":memory:")
create_snapshot_table(conn)
for snap in range(2):
    chain = {"ticker":"SPY","contracts":[{"expiry":"2026-09-19","strike":400.0+i,"type":"C",
        "oi":1000+i+snap*10,"volume":500+i,"iv":0.2,"delta":0.5,"gamma":0.02} for i in range(400)]}
    bulk_insert(conn, contracts_to_recordbatch(chain)); time.sleep(0.01)

lock = threading.Lock()
latest_counts = collections.Counter(); movers_counts = collections.Counter()
def wl():
    for _ in range(20):
        with lock: latest_counts[len(get_latest_snapshot(conn,"SPY"))]+=1
def wm():
    for _ in range(20):
        with lock: movers_counts[len(get_top_movers_from_db(conn,"SPY",top_n=10))]+=1
ts=[threading.Thread(target=wl) for _ in range(6)]+[threading.Thread(target=wm) for _ in range(6)]
for t in ts: t.start()
for t in ts: t.join()
print("CONTROL: same code WITH a conn lock held around each call")
print("  /latest:", dict(latest_counts), "-> wrong:", sum(v for k,v in latest_counts.items() if k!=400), "/", sum(latest_counts.values()))
print("  /movers:", dict(movers_counts), "-> wrong:", sum(v for k,v in movers_counts.items() if k!=10), "/", sum(movers_counts.values()))
