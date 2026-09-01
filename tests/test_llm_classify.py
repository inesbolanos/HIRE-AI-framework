"""Step 2 with a fake LLM: threshold routing (auto vs escalate) + incrementality."""
from hire_pipeline import deterministic_categorization as step1
from hire_pipeline import llm_classify
from hire_pipeline import constants as const
from hire_pipeline.llm import LLMClient

from helpers import interaction, seed_source


class FakeLLM(LLMClient):
    """Returns a canned (category, confidence) per text; records every call."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def classify(self, prompt, text_value, schema, model=None):
        self.calls.append(text_value)
        category, confidence = self.answers.get(text_value, (const.OTHER, 0.9))
        return {"category": category, "confidence": confidence,
                "reason": "canned", "tone": "neutral"}


def _prepare(store, cfg):
    seed_source(store, cfg, [
        interaction("i1", "c1", 1, user_input="strange charge on my statement"),
        interaction("i2", "c1", 2, user_input="asdf gibberish maybe"),
        interaction("i3", "c2", 1, control="qr_end"),  # routed: no LLM needed
    ])
    step1.apply_rules(store, cfg)


def test_classify_writes_auto_and_escalate_statuses(store, cfg):
    _prepare(store, cfg)
    llm = FakeLLM({
        "strange charge on my statement": ("report_unauthorized_transaction", 0.95),
        "asdf gibberish maybe": ("test_or_noise", 0.30),  # below threshold 0.6
    })
    written = llm_classify.classify(store, cfg, llm)
    assert written == 2  # only the residual rows, never the routed one

    out = store.read(cfg.tables.classified).set_index("interaction_id")
    assert out.loc["i1", "input_category"] == "report_unauthorized_transaction"
    assert out.loc["i1", "input_status"] == const.AUTO
    assert out.loc["i2", "input_status"] == const.ESCALATE
    assert out.loc["i1", "input_tone"] == "neutral"


def test_classify_is_incremental(store, cfg):
    _prepare(store, cfg)
    llm = FakeLLM({})
    assert llm_classify.classify(store, cfg, llm) == 2
    calls_first = len(llm.calls)
    # second run: everything already classified -> no new rows, no new LLM calls
    assert llm_classify.classify(store, cfg, llm) == 0
    assert len(llm.calls) == calls_first


def test_classify_truncates_to_max_chars(store, cfg):
    long_text = "x" * (cfg.run.max_chars + 500)
    seed_source(store, cfg, [interaction("i1", "c1", 1, user_input=long_text)])
    step1.apply_rules(store, cfg)
    llm = FakeLLM({})
    llm_classify.classify(store, cfg, llm)
    assert len(llm.calls) == 1
    assert len(llm.calls[0]) == cfg.run.max_chars
