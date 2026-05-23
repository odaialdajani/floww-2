#!/usr/bin/env python3
"""
compile_greeks.py  —  AOT-compile the Numba Greek kernels into a shared object.

Run this **once** during the Docker build phase (or locally after any change
to ``numba_greeks_aot.py``).  After compilation the ``.so`` file is placed
next to ``numba_greeks_aot.py`` so that ``numba_greeks.py`` can import the
compiled functions at runtime with zero JIT overhead.

Usage::

    $ python scripts/compile_greeks.py

The compiled artifact is::

    backend/services/numba_greeks_compiled.cpython-3XX-{arch}-{platform}.so

On Apple Silicon this produces an arm64 shared object.  On Linux amd64 it
produces an x86_64 shared object.  The import in ``numba_greeks.py`` works
transparently on either architecture via the native ``.so`` extension.
"""

from __future__ import annotations

import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("compile_greeks")


def main() -> int:
    """Compile the AOT Greek kernels and return exit code."""
    logger.info("Starting Numba AOT compilation of Greek kernels …")

    # Ensure we're in the project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(project_root)

    # Add the target module directory to sys.path so numba finds the source
    services_dir = os.path.join(project_root, "backend", "services")
    sys.path.insert(0, os.path.join(project_root, "backend"))

    t0 = time.perf_counter()

    try:
        # Import the CC registry — the import triggers compilation
        from services import numba_greeks_aot  # noqa: F401

        # Run the compiler
        numba_greeks_aot.cc.compile()
    except Exception as e:
        logger.error("AOT compilation failed: %s", e)
        return 1

    elapsed = time.perf_counter() - t0

    # Locate the compiled .so — check backend/ (top-level) first, then services/
    backend_dir = os.path.join(project_root, "backend")
    so_files = [
        f
        for f in os.listdir(backend_dir)
        if f.startswith("numba_greeks_compiled") and f.endswith(".so")
    ]
    if not so_files:
        # Fallback: check services/ (some numba versions place it there)
        so_files = [
            f
            for f in os.listdir(services_dir)
            if f.startswith("numba_greeks_compiled") and f.endswith(".so")
        ]
    else:
        # If it ended up in services/, move it to backend/
        for f in so_files:
            src = os.path.join(services_dir if os.path.exists(os.path.join(services_dir, f)) else backend_dir, f)
            dst = os.path.join(backend_dir, f)
            if src != dst and os.path.exists(src):
                import shutil
                shutil.move(src, dst)
                so_files = [f]
                break

    if so_files:
        so_path = os.path.join(backend_dir, so_files[0])
        so_size = os.path.getsize(so_path)
        logger.info(
            "AOT compilation successful  —  %.3fs  |  %s  (%.1f KB)",
            elapsed,
            so_files[0],
            so_size / 1024,
        )
    else:
        logger.warning(
            "Compilation completed but no .so found. "
            "Check numba_greeks_aot.py for errors."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
