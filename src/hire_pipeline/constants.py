"""Constant values shared across the pipeline.

This module contains:

  * OTHER: the residual bucket the steps special-case ('== const.OTHER') and reuse
    as the fallback tone. Its value must match the 'other' label in taxonomy.yaml
    (enforced by config._validate_taxonomy).
  * END_CONVERSATION: the closing intent Step 1 detects to derive resolution. Its
    value must match the qr_end mapping in taxonomy.yaml (also enforced).
  * The status/audit fields: llm_classify.py (Step 2) writes "escalate" and
    escalation.py reads it; audit.py writes "needs_review" and topic_discovery.py
    reads it.
"""
from __future__ import annotations

# Residual bucket: anything that fits no known category (must match taxonomy 'other').
OTHER = "other"

# Closing intent Step 1 special-cases for resolution (must match taxonomy qr_end).
END_CONVERSATION = "end_conversation"

# Step 1 conversation resolution_status.
RESOLVED = "resolved"
UNRESOLVED = "unresolved"
ABANDONED = "abandoned"
UNDETERMINED = "undetermined"  # no intent with a known resolving action -> can't judge

# Step 2 classification outcome: the <role>_status column on the classified table.
AUTO = "auto"          # confident enough to accept as-is
ESCALATE = "escalate"  # low confidence -> stronger-model second opinion

# Step 3 audit output fields
OTHER_CORRECT = "other_correct"  # did the judge confirm 'other' was correct?
NEEDS_REVIEW = "needs_review"    # the judge couldn't settle it -> a human decides
