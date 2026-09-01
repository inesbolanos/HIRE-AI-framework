"""Prompt building + the strict-JSON response schema."""
from hire_pipeline import prompts


def test_user_prompt_contains_every_label_and_fewshots(cfg):
    p = prompts.build_prompt(cfg, "user", cfg.run.language_hint, include_tone=True)
    for label in cfg.taxonomy.input_labels:
        assert label in p
    for ex in cfg.taxonomy.input_examples:
        assert ex["text"] in p
    assert cfg.run.language_hint in p
    for tone in cfg.taxonomy.tone_labels:
        assert tone in p


def test_agent_prompt_uses_output_labels_without_tone(cfg):
    p = prompts.build_prompt(cfg, "agent", include_tone=False)
    for label in cfg.taxonomy.output_labels:
        assert label in p
    # tone is a user-side concept; the agent prompt must not ask for it
    assert "angry" not in p


def test_response_schema_required_fields():
    with_tone = prompts.response_schema(include_tone=True)
    assert {"reason", "category", "confidence", "tone"} == set(with_tone["required"])
    assert with_tone["properties"]["confidence"]["type"] == "number"

    without = prompts.response_schema(include_tone=False)
    assert "tone" not in without["required"]
    assert "tone" not in without["properties"]


def test_other_audit_prompt_mentions_other(cfg):
    p = prompts.build_other_audit_prompt(cfg, "user")
    assert "other" in p
