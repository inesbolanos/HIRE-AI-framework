"""Prompt construction and the strict-JSON response contract.

Key design choices:
  * reason FIRST, then category: making the model justify before committing is
    the biggest accuracy lever on ambiguous inputs.
  * an explicit 'other' category and a 'confidence' score are always required.
  * tone folds into the same call (user role) rather than a second pass.
  * few-shot examples are real misclassifications for the confused pairs.

The label set, few-shot examples, tone labels, and agent description all come from
the data-driven taxonomy ('cfg.taxonomy' / taxonomy.yaml).
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import constants as const

def _labels_for(cfg, role: str) -> dict:
    """Category labels for a role: 'user' -> input labels, 'agent' -> output labels."""
    return cfg.taxonomy.input_labels if role == "user" else cfg.taxonomy.output_labels


def _examples_for(cfg, role: str) -> list:
    """Few-shot examples for a role (each a {text, category, reason} dict)."""
    return cfg.taxonomy.input_examples if role == "user" else cfg.taxonomy.output_examples


def _role_line(cfg, role: str) -> str:
    desc = cfg.taxonomy.agent_description or "support agent"
    if role == "user":
        return (f"You label a single USER message sent to a {desc}, "
                "by what the user is trying to do.")
    return (f"You label a single AGENT reply produced by a {desc}, "
            "by what the agent delivered.")


def build_prompt(cfg, role: str, language_hint: str = "", include_tone: bool = True) -> str:
    """Build the classification prompt for a role ('user' or 'agent').

    include_tone is True for the user role (tone folds into the same call); pass
    False for the agent role. Labels/examples/tones come from ``cfg.taxonomy``.
    """
    labels = _labels_for(cfg, role)
    examples = _examples_for(cfg, role)

    cats = "\n".join(f"- {k}: {v}" for k, v in labels.items())

    examples_block = ""
    if examples:
        rendered = "\n".join(
            f'- TEXT: "{e["text"]}"\n  -> {{"reason": "{e["reason"]}", "category": "{e["category"]}"}}'
            for e in examples
        )
        examples_block = f"\n\nEXAMPLES:\n{rendered}"

    if include_tone:
        json_spec = ('{"reason": "<one short sentence>", "category": "<one label>", '
                     '"confidence": <0.0-1.0>, "tone": "<one tone label>"}')
        tone_cats = "\n".join(f"- {k}: {v}" for k, v in cfg.taxonomy.tone_labels.items())
        tone_block = (
            "\n\nALSO detect the USER'S TONE. Assign EXACTLY ONE tone label from the "
            "list below (use \"other\" if none fit). Judge tone independently of the "
            "category.\nTONE LABELS:\n" + tone_cats
        )
    else:
        json_spec = ('{"reason": "<one short sentence>", "category": "<one label>", '
                     '"confidence": <0.0-1.0>}')
        tone_block = ""

    lang = f"{language_hint}\n" if language_hint else ""

    return (
        f"{_role_line(cfg, role)}\n"
        "Assign it to EXACTLY ONE of the categories below. These are the only valid "
        "categories — do NOT invent new ones. If it clearly fits none, use \"other\".\n"
        "Classify by INTENT, not by keywords.\n"
        "If the text is NOT an actionable request or question directed at the agent "
        "— e.g. pasted error messages, raw logs, or a bare status observation — "
        "classify it as \"other\".\n"
        f"{lang}"
        "Respond with STRICT JSON only: " + json_spec + ".\n"
        "Think through the reason BEFORE choosing the category. confidence = how sure you are.\n"
        f"{examples_block}"
        f"{tone_block}\n\n"
        f"CATEGORIES:\n{cats}"
    )


def response_schema(include_tone: bool = True) -> Dict[str, Any]:
    """The JSON-schema 'properties' contract the classifier must satisfy."""
    props: Dict[str, Any] = {
        "reason": {"type": "string"},
        "category": {"type": "string"},
        "confidence": {"type": "number"},
    }
    required = ["reason", "category", "confidence"]
    if include_tone:
        props["tone"] = {"type": "string"}
        required.append("tone")
    return {"type": "object", "properties": props, "required": required}


# Step 3 prompts: audit the 'other' bucket
def build_other_audit_prompt(cfg, role: str, language_hint: str = "") -> str:
    """Stronger model audits an 'other' row and proposes a free-form theme.

    Two jobs: (1) judge whether 'other' was correct — catching KNOWN categories
    wrongly sent to 'other'; (2) generate a free-form reason_theme (no predefined
    list) so themes emerge from the data. 'role' is 'user' or 'agent'.
    """
    labels = _labels_for(cfg, role)
    cats = "\n".join(f"- {k}: {v}" for k, v in labels.items() if k != const.OTHER)
    lang = f"{language_hint}\n" if language_hint else ""
    subject = "user message" if role == "user" else "agent reply"
    return (
        f"A weaker model labeled this {subject} as 'other' (fits no known category).\n"
        "Do THREE things and return STRICT JSON.\n"
        "1. Decide whether 'other' was CORRECT. If the text actually fits one of the "
        "KNOWN categories below, set other_correct=false and name it in "
        "corrected_category; otherwise other_correct=true and corrected_category=null.\n"
        "2. Write a short free-form reason_theme (2-5 words) describing what the text is "
        "really about. Do NOT pick from a list — let the theme emerge.\n"
        "3. If you CANNOT confidently make the call in (1) — the text is ambiguous, "
        "garbled, or genuinely borderline — set needs_review=true so a human decides; "
        "otherwise needs_review=false.\n"
        f"{lang}"
        f'Respond with STRICT JSON only: {{"{const.OTHER_CORRECT}": <true|false>, '
        '"corrected_category": "<known label or null>", "reason_theme": "<2-5 words>", '
        f'"{const.NEEDS_REVIEW}": <true|false>}}.\n\n'
        f"KNOWN CATEGORIES:\n{cats}"
    )


# Step 5 prompts: name the discovered topics
def build_topic_naming_prompt(cfg, keywords: List[str], samples: List[str]) -> str:
    """Ask the stronger model to NAME one discovered cluster (labels only; the
    clustering itself is done by embeddings + HDBSCAN for reproducibility)."""
    desc = cfg.taxonomy.agent_description or "support agent"
    kw = ", ".join(keywords)
    ex = "\n".join(f"- {s}" for s in samples[:8])
    return (
        f"You are naming a cluster of user messages that all fall OUTSIDE a {desc}'s "
        "known capabilities. Give a short, specific, human-readable label "
        "(3-6 words) describing the shared unmet need.\n"
        f"Top keywords: {kw}\n"
        f"Representative messages:\n{ex}\n\n"
        'Respond with STRICT JSON only: {"label": "<3-6 words>"}.'
    )
