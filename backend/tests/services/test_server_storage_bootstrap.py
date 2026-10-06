"""Exercise the real server import order with an isolated settings file/store."""

import os
import subprocess
import sys
from pathlib import Path


def test_dotenv_storage_is_opened_before_services_and_survives_restart(tmp_path):
    store = tmp_path / "history.duckdb"
    settings = tmp_path / ".env"
    settings.write_text(f"DUCKDB_PATH={store.as_posix()}\nFLOWW_AGENT_DEPLOYMENT=local\n")
    script = """
import os
import sys
import dotenv
load = dotenv.load_dotenv
dotenv.load_dotenv = lambda *args, **kwargs: load(sys.argv[1], override=False)
import server
from services.duckdb_engine import db
assert os.environ['FLOWW_AGENT_DEPLOYMENT'] == 'local'
backing = [row[2] for row in db.conn.execute('PRAGMA database_list').fetchall()]
assert any(backing), 'Server opened temporary storage before reading its settings'
if sys.argv[2] == 'write':
    db.conn.execute('CREATE TABLE bootstrap_probe AS SELECT 42 AS reading')
else:
    assert db.conn.execute('SELECT reading FROM bootstrap_probe').fetchone()[0] == 42
db.close()
server.client.close()
print('permanent history verified')
"""
    env = dict(os.environ)
    env.pop("DUCKDB_PATH", None)
    env.pop("FLOWW_AGENT_DEPLOYMENT", None)
    env.update(TESTING="1", DB_NAME="test_storage_bootstrap", MONGO_URL="mongodb://127.0.0.1:27017")
    for mode in ("write", "read"):
        result = subprocess.run(
            [sys.executable, "-c", script, str(settings), mode],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "permanent history verified" in result.stdout
    assert store.is_file()
