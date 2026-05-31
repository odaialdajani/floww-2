#!/usr/bin/env python3
"""
backend/services/memory/voice_embeddings.py — Voice memo transcription via Whisper.

Watches iOS Voice Memos sync folder for new .m4a files.
Transcribes via whisper-base (local model, ~150MB).
Inserts transcript into mem0 with tags [source:voice_memo, audio].
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# iOS Voice Memos iCloud sync path (configurable via env var)
VOICE_MEMOS_DIR = Path(os.environ.get(
    "VOICE_MEMOS_DIR",
    str(Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Voice Memos")
))

# State file to track processed memos
PROCESSED_STATE = Path.home() / ".hermes" / "voice_memos_processed.json"


