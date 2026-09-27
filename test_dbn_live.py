import os
import sys

import databento as db


def main() -> None:
    # Live-connectivity probe. Key comes from the environment only;
    # never paste a live key into this file (repo is public).
    api_key = os.environ.get("DATABENTO_API_KEY", "")
    if not api_key:
        print("SKIP: DATABENTO_API_KEY is not set; refusing to connect.")
        sys.exit(0)
    client = db.Live(key=api_key)
    client.subscribe(
        dataset="OPRA.PILLAR",
        schema="trades",
        stype_in="parent",
        symbols="SPY.OPT",
    )
    client.add_callback(print)
    client.start()
    client.block_for_close(timeout=10)


if __name__ == "__main__":
    main()
