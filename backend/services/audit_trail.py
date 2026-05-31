"""
backend/services/audit_trail.py

Immutable, hash-chained audit trail for every write action.
Fields: timestamp, actor, action_type, target, before_state, after_state, ip, user_agent, request_id
Retention: 7 years (SEC Rule 17a-4 inspired)

Reference: SEC Rule 17a-4, FINRA Rule 4511, NIST SP 800-53
"""

from __future__ import annotations

import logging

logger = logging.getLogger("audit_trail")


