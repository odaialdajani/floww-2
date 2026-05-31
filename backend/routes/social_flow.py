"""
API routes for Social Sentiment & Options Flow data.
Mount these in server.py.
"""

import json
import logging
import os
from datetime import datetime

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/social", tags=["social"])

# Data directory for cached reports
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "social-reports")
os.makedirs(DATA_DIR, exist_ok=True)


@router.get("/sentiment/{ticker}")
async def get_sentiment(ticker: str):
    """Get social sentiment for a ticker."""
    report_path = os.path.join(DATA_DIR, f"{ticker.upper()}_sentiment.json")

    if os.path.exists(report_path):
        with open(report_path) as f:
            data = json.load(f)
        return {"ticker": ticker.upper(), "cached": True, **data}

    return {
        "ticker": ticker.upper(),
        "cached": False,
        "message": "No sentiment data available yet. Run the social flow pipeline first.",
        "sentiment": None,
    }


@router.get("/flow/{ticker}")
async def get_flow(ticker: str, min_premium: float = 50000):
    """Get options flow signals for a ticker."""
    report_path = os.path.join(DATA_DIR, f"{ticker.upper()}_flow.json")

    if os.path.exists(report_path):
        with open(report_path) as f:
            data = json.load(f)
        return {"ticker": ticker.upper(), "cached": True, **data}

    return {
        "ticker": ticker.upper(),
        "cached": False,
        "message": "No flow data available yet. Run the social flow pipeline first.",
        "signals": [],
    }


@router.get("/report/{ticker}")
async def get_full_report(ticker: str):
    """Get combined social + flow + GEX report for a ticker."""
    report_path = os.path.join(DATA_DIR, f"{ticker.upper()}_report.json")

    if os.path.exists(report_path):
        with open(report_path) as f:
            data = json.load(f)
        return {"ticker": ticker.upper(), "cached": True, **data}

    return {
        "ticker": ticker.upper(),
        "cached": False,
        "message": "No report available yet. Run the social flow pipeline first.",
        "report": None,
    }


@router.get("/status")
async def get_pipeline_status():
    """Get status of the social flow pipeline."""
    from social_flow_pipeline import TwitterCollector

    collector = TwitterCollector()
    xurl_auth = collector.is_authenticated()

    # Check for cached reports
    reports = []
    if os.path.exists(DATA_DIR):
        for f in os.listdir(DATA_DIR):
            if f.endswith("_report.json"):
                ticker = f.replace("_report.json", "")
                reports.append(ticker)

    return {
        "xurl_authenticated": xurl_auth,
        "cached_reports": reports,
        "data_dir": DATA_DIR,
        "timestamp": datetime.utcnow().isoformat(),
    }
