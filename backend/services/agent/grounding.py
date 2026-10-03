"""Stable grounded identity, not an execution approval or a broker permission."""

import hashlib

from services.agent.contracts import canonical


def grounding_hash(context, facts):
    return hashlib.sha256(canonical({"context": context, "facts": facts}).encode()).hexdigest()
