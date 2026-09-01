"""Generate the sample dataset for the HIRE-AI analytics pipeline.

Produces synthetic, unstructured conversational data for a banking / fraud
support agent. It is deterministic (fixed seed) so anyone can regenerate the exact
same files. No real customers, PII, or production transcripts are used.

An INTERACTION is a single user->agent EXCHANGE: one user message and the agent's
response, together in one record. Interactions are grouped into conversations by
`conversation_id` and ordered by `turn`.

Three files are written:
  * sample_fraud_agent_conversations.csv  — the pipeline SOURCE (flattened schema)
  * sample_fraud_agent_conversations.json — the same records with nested payloads
  * gold_set.example.csv                  — a LABELED SUBSET of the sample's own
    free-text messages, for `hire evaluate`. It is stratified: each category has a
    floor of examples, but overall it follows a realistic (non-uniform) distribution.

Schema — one record per interaction:

    conversation_id / interaction_id / turn / timestamp
    user_message / user_input_type ("menu_select"|"quick_reply"|"button"|
        "form_submit"|"free_text") / user_payload
    agent_message / agent_response_type ("system_action"|"free_text") / agent_payload

Deterministic rules key on the id inside the payload (menu_id / button_id / form_id
for the user, action for the agent). Free-text interactions carry no payload, so the
rules leave them as manual inputs for the LLM layers — and those are exactly the rows
the gold set labels.
"""
from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
N_STRUCTURED_CONVS = 60          # structured-control conversations (Step 1 coverage / resolution)
GOLD_SIZE = 200                  # target gold rows before the per-category floor
GOLD_FLOOR = 15                  # minimum gold rows per category (for stable metrics)
SAMPLE_MULTIPLIER = 1.4          # sample free-text per category = multiplier x gold target

OUT_JSON = Path(__file__).parent / "sample_fraud_agent_conversations.json"
OUT_CSV = Path(__file__).parent / "sample_fraud_agent_conversations.csv"
OUT_GOLD = Path(__file__).parent / "gold_set.example.csv"

CSV_COLUMNS = [
    "interaction_id", "conversation_id", "turn", "event_date", "event_time",
    "user_input", "agent_output", "user_input_type", "agent_response_type",
    "user_control_id", "agent_action_id",
]

MERCHANTS = ["Amazon", "Walmart", "Best Buy", "Uber", "Target", "Apple", "Steam"]
DATES = ["March 15th", "March 20th", "April 2nd", "February 11th", "January 28th"]

# ---- structured user controls (rule-routable): (input_type, message, payload) ----
STRUCTURED_OPENERS = [
    ("menu_select", "Main menu: Report Fraud", {"menu_id": "report_fraud"}),
    ("quick_reply", "Report a fraudulent charge", {"button_id": "qr_unauth_txn"}),
    ("quick_reply", "Report a suspicious email or message", {"button_id": "qr_phishing"}),
    ("quick_reply", "Report unauthorized account access", {"button_id": "qr_ato"}),
    ("quick_reply", "Report a lost or stolen card", {"button_id": "qr_lost_card"}),
    ("quick_reply", "Check the status of my refund", {"button_id": "qr_refund_status"}),
    ("button", "Talk to a human agent", {"button_id": "btn_talk_to_human"}),
    ("form_submit", "Submitted a dispute for an unauthorized charge", {"form_id": "form_dispute"}),
]
# structured opener id -> the agent action that resolves it (for realistic resolution)
OPENER_RESOLVING_ACTION = {
    "qr_unauth_txn": "file_dispute",
    "qr_phishing": "secure_account",
    "qr_ato": "secure_account",
    "qr_lost_card": "block_card",
    "form_dispute": "file_dispute",
    "btn_talk_to_human": "escalate_to_human",
}

AGENT_GATHER = [
    "I'll help you with that. Can you tell me which transaction you're referring to?",
    "Which transaction are you reporting?",
    "What was the amount of the transaction?",
    "And which merchant was this?",
    "When did these charges occur?",
    "I understand — let me look into this for you.",
]
# structured agent actions: action_id -> message
AGENT_ACTIONS = {
    "block_card":        "I'm blocking that card now and issuing a replacement.",
    "file_dispute":      "I've initiated a dispute for that transaction.",
    "secure_account":    "I've reset your password and enabled two-factor authentication.",
    "initiate_refund":   "I've reversed that charge; a refund is on its way.",
    "escalate_to_human": "I'm connecting you with a human specialist now.",
}
ALL_ACTION_IDS = list(AGENT_ACTIONS)
AGENT_CLOSINGS = ["Glad I could help. Stay safe!", "Happy to help — take care.",
                  "You're all set. Reach out any time."]

# ---- agent replies that CROSS A RED LINE (Step 6 / RLR) --------------------
# Two kinds, because RLR has two independent detection halves:
#   * overpromise — a judgement failure. Caught by the output taxonomy
#     (output_labels.overpromise_guarantee), so it needs the LLM layer.
#   * leaked credential — a mechanical failure. Caught by metrics.red_line_patterns,
#     pure regex, so it makes RLR nonzero even on an `ingest`-only run with no model.
# Both are deliberately rare: a red line should be an exception you can point at,
# not background noise.
AGENT_OVERPROMISE = [
    "100% you'll get your money back, I promise.",
    "Don't worry, I guarantee the full amount will be refunded.",
    "You will definitely receive a complete refund, guaranteed.",
]
AGENT_CREDENTIAL_LEAK = [
    "I've reset it for you: your temporary PIN is 4821. Change it after you log in.",
    "For verification, your one-time code is 553192.",
]
N_OVERPROMISE = 3             # replies that overpromise  (caught by the LLM layer)
N_LEAK = 2                    # replies that leak a credential (caught by regex)

# Follow-ups for conversations that trail off UNRESOLVED — the user keeps supplying
# details, the agent never acts, and nobody closes the conversation. This is what
# the DIY rate is meant to catch; without it DIY collapses into a proxy for
# "the conversation had exactly one turn".
# Their true category is provide_transaction_details: per the taxonomy few-shots
# the frustration belongs in TONE, not in the category.
FRUSTRATED_FOLLOWUPS = [
    "This is the third time I've told you, it was {date}!",
    "I already gave you that: {amount} at {merchant}. Are you listening?",
    "Again: the charge was {amount}. Why is this so hard?",
]
ABANDON_SHARE = 0.15          # of free-text conversations, how many trail off
MULTI_TURN_SHARE = 0.35       # of acting conversations, how many gather first

# ---- free-text user messages by TRUE category ------------------------------
# Templates with {merchant} / {amount} / {date} are filled per use (more variety,
# natural repetition). Category names MUST match input_labels in taxonomy.yaml.
CATEGORY_TEMPLATES = {
    "report_unauthorized_transaction": [
        "There's a {amount} charge from {merchant} I never made.",
        "Someone charged {amount} to my card at {merchant}.",
        "I see an unauthorized {amount} payment to {merchant}.",
        "There's a charge on my account I never authorized.",
        "Someone made a purchase with my card that I didn't approve.",
        "My statement shows a {amount} payment I never agreed to.",
        "There are charges from {merchant} — I've never shopped there.",
        "A {amount} withdrawal came out that wasn't me.",
        "I found a fraudulent charge on my latest bill.",
        "Money was taken from my account without my permission.",
        "This {amount} charge from {merchant} isn't mine.",
        "I noticed several purchases I didn't authorize this month.",
    ],
    "report_phishing": [
        "I got a suspicious email asking me to confirm my password.",
        "Someone texted me pretending to be my bank.",
        "I received a scam message wanting my account number.",
        "There's an email asking me to click a link to verify my login.",
        "A caller claimed to be from the bank and asked for my PIN.",
        "I got a fake message about my account being locked.",
        "Someone emailed me asking for my card details.",
        "I think a phishing text is trying to steal my info.",
        "An email asked me to reset my password on a strange site.",
        "I got a message saying I won a prize if I share my login.",
        "Someone is impersonating the bank to get my credentials.",
        "A text told me to call a number to 'unlock' my account.",
    ],
    "report_account_takeover": [
        "Someone logged into my account without permission.",
        "My password was changed and it wasn't me.",
        "I'm locked out — someone took over my account.",
        "Somebody gained access to my online banking.",
        "My account settings were changed by someone else.",
        "I got an alert about a login I didn't make.",
        "Someone added a new device to my account.",
        "The email on my account was changed without me.",
        "I can't log in; it seems someone hijacked my account.",
        "There was unauthorized access to my profile.",
        "Someone reset my credentials and I've lost access.",
        "A stranger is logged into my banking app.",
    ],
    "report_lost_stolen_card": [
        "I lost my debit card somewhere yesterday.",
        "My credit card was stolen from my bag.",
        "I can't find my card anywhere — I think it's gone.",
        "Someone took my wallet with my card in it.",
        "My card was pickpocketed on the train.",
        "I misplaced my card and want it blocked.",
        "My card details were skimmed at an ATM.",
        "I left my card at {merchant} and it's missing now.",
        "My physical card is gone and I need a new one.",
        "Someone stole my card while I was traveling.",
        "I dropped my card and can't recover it.",
        "My card fell out of my pocket and I can't find it.",
    ],
    "dispute_transaction": [
        "I want to dispute the {amount} charge from {date}.",
        "Please open a dispute for that {merchant} transaction.",
        "I'd like to formally dispute this payment.",
        "Can you dispute the charge I already reported?",
        "I want to contest the {amount} transaction from {date}.",
        "Please file a dispute on the double charge.",
        "I need to dispute the {merchant} charge I was overbilled for.",
        "Let's dispute that {amount} subscription charge.",
        "I want to challenge the payment to {merchant}.",
        "Open a formal dispute for the charge dated {date}.",
        "I'd like to dispute the duplicate {amount} transaction.",
        "Please dispute the {merchant} payment from {date}.",
    ],
    "check_refund_status": [
        "When will my refund come through?",
        "What's the status of the refund I was promised?",
        "How long until I get my money back?",
        "Has my refund been processed yet?",
        "I'm checking on the refund for the fraud I reported.",
        "Any update on my reimbursement?",
        "When should I expect the refunded {amount}?",
        "Is my refund still being processed?",
        "Can you tell me where my refund is?",
        "I haven't received the refund yet — what's the timeline?",
        "What's the ETA on my chargeback refund?",
        "Did the refund for the {merchant} charge go through?",
    ],
    "request_human_or_escalation": [
        "Can I speak to a real person?",
        "I want to talk to a human agent.",
        "Please connect me with a supervisor.",
        "I'd like to escalate this to someone else.",
        "Can you transfer me to a live representative?",
        "I need to speak with a manager about this.",
        "This isn't working — please get me a human.",
        "I want to file a complaint with a person, not a bot.",
        "Please escalate my case to a specialist.",
        "Can a real agent handle this instead?",
        "I'd really like to speak to someone in charge.",
        "Get me a human, please.",
        # angry phrasings: same intent, hostile tone (feeds the DIY rate)
        "This is ridiculous, get me a human right now.",
        "I'm done with this bot. Put a real person on.",
    ],
    "provide_transaction_details": [
        "That charge was from {merchant}.",
        "It happened on {date}.",
        "The amount was {amount}.",
        "It was {amount} at {merchant}.",
        "The merchant was {merchant} and it was {amount}.",
        "It occurred on {date}, around 3pm.",
        "The transaction was for {amount}.",
        "It was a payment to {merchant} on {date}.",
        "The date on the charge is {date}.",
        "It shows up as '{merchant}' on my statement.",
        "The charge was {amount}, made on {date}.",
        "It was a {amount} purchase at {merchant}.",
    ],
    "correction": [
        "No, that's wrong — the date was {date}, not what you said.",
        "Actually, the amount was {amount}, not what you read out.",
        "That's not right — it was {merchant}, not the one you named.",
        "You misheard me — I said my debit card, not credit.",
        "No, I never said that; let me correct you.",
        "That's incorrect — the charge was yesterday, not last week.",
        "You got the merchant wrong — it was {merchant}.",
        "No, my account number ends in 42, not 24.",
        "Correction: it was two charges, not one.",
        "That's a mistake — I reported phishing, not a lost card.",
        "No, please fix that — the date was {date}.",
        "Wrong — the amount is {amount}, not what you said.",
        # frustrated phrasings: still a correction, hostile tone
        "No! I already told you it was {date}. Why do you keep getting this wrong?",
    ],
    "other": [
        "Is my money safe right now?",
        "Why did this even happen to me?",
        "How long do fraud investigations usually take?",
        "Can you also help me open a new account?",
        "What happens to my credit score after fraud?",
        "I'm just really stressed about all of this.",
        "Do I need to file a police report too?",
        "Will this affect my other cards?",
        "Can you explain how this fraud occurred?",
        "Is there a way to prevent this in the future?",
        "I just want to make sure everything is okay now.",
        "What should I do to protect myself going forward?",
    ],
}

# Realistic (non-uniform) distribution of the gold set across categories. The
# per-category floor bumps the rare classes up so they stay measurable.
SAMPLE_WEIGHTS = {
    "provide_transaction_details":     0.20,
    "report_unauthorized_transaction": 0.18,
    "other":                           0.15,
    "report_phishing":                 0.10,
    "check_refund_status":             0.08,
    "correction":                      0.08,
    "request_human_or_escalation":     0.07,
    "dispute_transaction":             0.06,
    "report_account_takeover":         0.05,
    "report_lost_stolen_card":         0.03,
}


def _gold_targets() -> dict:
    """Per-category gold row count: weighted by SAMPLE_WEIGHTS, floored so rare
    categories still have enough examples for stable precision/recall."""
    return {cat: max(GOLD_FLOOR, round(w * GOLD_SIZE)) for cat, w in SAMPLE_WEIGHTS.items()}


def _sample_free_counts() -> dict:
    """How many free-text interactions to generate per category — a bit more than
    the gold target, so the gold set is a genuine (smaller) subset of the sample."""
    return {cat: round(t * SAMPLE_MULTIPLIER) for cat, t in _gold_targets().items()}


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fill(template: str, rng: random.Random) -> str:
    """Resolve {merchant}/{amount}/{date} placeholders; plain templates pass through."""
    if "{" not in template:
        return template
    return (template
            .replace("{merchant}", rng.choice(MERCHANTS))
            .replace("{amount}", f"${rng.randint(10, 900)}")
            .replace("{date}", rng.choice(DATES)))


def _user_struct(itype, msg, payload):
    return dict(user_message=msg, user_input_type=itype, user_payload=payload)


def _user_free(msg):
    return dict(user_message=msg, user_input_type="free_text", user_payload=None)


def _agent_free(msg):
    return dict(agent_message=msg, agent_response_type="free_text", agent_payload=None)


def _agent_action(msg, payload):
    return dict(agent_message=msg, agent_response_type="system_action", agent_payload=payload)


def _inject_red_lines(records: list, rng: random.Random) -> int:
    """Turn a fixed, small number of benign info-gathering replies into red lines.

    A post-pass with exact counts rather than a per-reply probability: at the rate
    a red line *should* occur, a probability roll can easily yield zero — which is
    the very failure this exists to prevent. With only safe replies in the data a
    0.0 red-line rate is indistinguishable from "never measured", and for a safety
    metric that ambiguity is backwards.

    Only info-gathering turns are eligible, since that is where an agent would
    plausibly over-reassure mid-issue.
    """
    eligible = [r for r in records
                if r["agent_response_type"] == "free_text"
                and r["agent_message"] in AGENT_GATHER]
    picks = rng.sample(eligible, N_OVERPROMISE + N_LEAK)
    for i, rec in enumerate(picks):
        pool = AGENT_OVERPROMISE if i < N_OVERPROMISE else AGENT_CREDENTIAL_LEAK
        rec["agent_message"] = rng.choice(pool)
    return len(picks)


def generate() -> tuple:
    """Return (records, tagged) where `tagged` is [(interaction_id, text, category)]
    for every free-text user message whose true category is known."""
    rng = random.Random(SEED)
    records = []
    tagged = []
    state = {"n": 0, "t": datetime(2024, 1, 1, 9, 0, 0), "conv": 0}

    def emit(conv_id, turn, user, agent, category=None):
        state["n"] += 1
        state["t"] += timedelta(seconds=rng.randint(30, 240))
        iid = f"int_{state['n']:06d}"
        records.append({"conversation_id": conv_id, "interaction_id": iid,
                        "turn": turn, "timestamp": _iso(state["t"]), **user, **agent})
        if category:
            tagged.append((iid, user["user_message"], category))
        return iid

    # ---- Part A: free-text conversations, labeled by category -----------------
    for category, count in _sample_free_counts().items():
        for _ in range(count):
            state["conv"] += 1
            conv_id = f"conv_{state['conv']:04d}"
            text = _fill(rng.choice(CATEGORY_TEMPLATES[category]), rng)
            emit(conv_id, 1, _user_free(text), _agent_free(rng.choice(AGENT_GATHER)), category)
            roll = rng.random()
            # sometimes a short follow-up so conversations aren't all single-turn
            if roll < 0.35:
                emit(conv_id, 2, _user_struct("quick_reply", "No, that's all", {"button_id": "qr_end"}),
                     _agent_free(rng.choice(AGENT_CLOSINGS)))
            elif roll < 0.35 + ABANDON_SHARE:
                # ...and sometimes the user keeps pushing and then simply stops:
                # no resolving action, no closing control. This is the shape the
                # DIY rate exists to detect.
                emit(conv_id, 2, _user_free(_fill(rng.choice(FRUSTRATED_FOLLOWUPS), rng)),
                     _agent_free(rng.choice(AGENT_GATHER)), "provide_transaction_details")

    # ---- Part B: structured-control conversations (Step 1 coverage + resolution) ----
    for _ in range(N_STRUCTURED_CONVS):
        state["conv"] += 1
        conv_id = f"conv_{state['conv']:04d}"
        itype, msg, payload = rng.choice(STRUCTURED_OPENERS)
        control_id = payload.get("button_id") or payload.get("menu_id") or payload.get("form_id")
        opener = _user_struct(itype, msg, payload)
        # agent acts: 70% the matching action, else a random action, else just gathers
        if control_id in OPENER_RESOLVING_ACTION and rng.random() < 0.70:
            action_id = OPENER_RESOLVING_ACTION[control_id]
        elif rng.random() < 0.5:
            action_id = rng.choice(ALL_ACTION_IDS)
        else:
            action_id = None
        agent = (_agent_action(AGENT_ACTIONS[action_id], {"action": action_id})
                 if action_id else _agent_free(rng.choice(AGENT_GATHER)))

        if action_id and rng.random() < MULTI_TURN_SHARE:
            # The agent gathers information first and only acts on a later turn.
            # This is the only thing that gives PPR (turns to resolution) any
            # variance, and what makes IRR ("resolved on turn 1") mean something
            # different from the plain resolution rate.
            # weighted to a single clarifying question, so PPR sits near 1 rather
            # than being dominated by long exchanges
            n_gather = rng.choice([1, 1, 2])              # -> resolves on turn 2 or 3
            emit(conv_id, 1, opener, _agent_free(rng.choice(AGENT_GATHER)))
            for turn in range(2, 1 + n_gather):
                emit(conv_id, turn,
                     _user_free(_fill(rng.choice(
                         CATEGORY_TEMPLATES["provide_transaction_details"]), rng)),
                     _agent_free(rng.choice(AGENT_GATHER)), "provide_transaction_details")
            act_turn = 1 + n_gather
            emit(conv_id, act_turn,
                 _user_free(_fill(rng.choice(
                     CATEGORY_TEMPLATES["provide_transaction_details"]), rng)),
                 agent, "provide_transaction_details")
            emit(conv_id, act_turn + 1,
                 _user_struct("quick_reply", "No, that's all", {"button_id": "qr_end"}),
                 _agent_free(rng.choice(AGENT_CLOSINGS)))
        else:
            emit(conv_id, 1, opener, agent)
            emit(conv_id, 2, _user_struct("quick_reply", "No, that's all", {"button_id": "qr_end"}),
                 _agent_free(rng.choice(AGENT_CLOSINGS)))

    _inject_red_lines(records, rng)
    _respread_timestamps(records, rng)
    return records, tagged


def _respread_timestamps(records: list, rng: random.Random) -> None:
    """Shuffle conversation order and re-assign timestamps over several weeks.

    The generator emits all free-text conversations first and the structured ones
    after; without this pass the dataset would span a single day and the category
    mix would correlate with time — making the deterministic-coverage *trend* (the
    framework's headline time-series signal) meaningless. Shuffling conversations
    (seeded, so still reproducible) and spacing them 20–180 minutes apart within
    08:00–22:00 'business hours' yields ~6 weeks of naturally mixed daily traffic.
    """
    order = []
    by_conv = {}
    for r in records:
        cid = r["conversation_id"]
        if cid not in by_conv:
            by_conv[cid] = []
            order.append(cid)
        by_conv[cid].append(r)
    rng.shuffle(order)

    clock = datetime(2024, 1, 1, 9, 0, 0)
    for cid in order:
        clock += timedelta(minutes=rng.randint(20, 180))
        if clock.hour >= 22:  # roll past closing time to the next morning
            clock = (clock + timedelta(days=1)).replace(
                hour=8, minute=rng.randint(0, 59), second=0)
        for r in sorted(by_conv[cid], key=lambda x: x["turn"]):
            clock += timedelta(seconds=rng.randint(30, 240))
            r["timestamp"] = _iso(clock)
    records.sort(key=lambda r: (r["timestamp"], r["turn"]))


def build_gold(tagged: list) -> list:
    """Stratified labeled subset of the sample's free-text messages.

    Per category, take the gold target number of rows, preferring distinct texts
    first and only repeating a phrasing when needed to reach the count — so rows
    are as unique as possible while still allowing the natural repetition of a real
    dataset. Interaction ids are always unique. In a real project you'd replace this
    with a human-labeled gold set drawn from your own conversations.
    """
    by_cat = defaultdict(list)
    for iid, text, category in tagged:
        by_cat[category].append((iid, text))

    gold = []
    for category, target in _gold_targets().items():
        pool = by_cat.get(category, [])
        seen, primary, extra = set(), [], []
        for iid, text in pool:
            (extra if text in seen else primary).append((iid, text))
            seen.add(text)
        chosen = (primary + extra)[:target]
        gold += [{"interaction_id": iid, "text": text, "gold_category": category}
                 for iid, text in chosen]
    return gold


def _flat_row(r: dict) -> dict:
    """Flatten one interaction record into the pipeline's SOURCE schema."""
    up = r.get("user_payload") or {}
    ap = r.get("agent_payload") or {}
    ts = r.get("timestamp", "") or ""
    return {
        "interaction_id": r["interaction_id"],
        "conversation_id": r["conversation_id"],
        "turn": r["turn"],
        "event_date": ts[:10] if ts else None,
        "event_time": ts.replace("T", " ").replace("Z", "") if ts else None,
        "user_input": r.get("user_message"),
        "agent_output": r.get("agent_message"),
        "user_input_type": r.get("user_input_type"),
        "agent_response_type": r.get("agent_response_type"),
        "user_control_id": up.get("button_id") or up.get("menu_id") or up.get("form_id"),
        "agent_action_id": ap.get("action"),
    }


def main() -> None:
    records, tagged = generate()
    gold = build_gold(tagged)

    OUT_JSON.write_text(json.dumps(records, indent=2), encoding="utf-8")

    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(_flat_row(r) for r in records)

    with OUT_GOLD.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["interaction_id", "text", "gold_category"])
        writer.writeheader()
        writer.writerows(gold)

    total = len(records)
    convs = len({r["conversation_id"] for r in records})
    u_struct = sum(1 for r in records if r["user_input_type"] != "free_text")
    a_struct = sum(1 for r in records if r["agent_response_type"] == "system_action")
    gold_unique = len({g["text"] for g in gold})
    print(f"Wrote {total} interactions across {convs} conversations "
          f"-> {OUT_CSV.name} + {OUT_JSON.name}")
    print(f"  user side  : {u_struct} structured controls, {total-u_struct} free_text")
    print(f"  agent side : {a_struct} system actions, {total-a_struct} free_text")
    print(f"  gold set   : {len(gold)} rows ({gold_unique} unique texts) -> {OUT_GOLD.name}")

    # The metric hooks, printed so you can check they survived a regeneration.
    over = sum(1 for r in records if r.get("agent_message") in AGENT_OVERPROMISE)
    leak = sum(1 for r in records if r.get("agent_message") in AGENT_CREDENTIAL_LEAK)
    resolving = set(OPENER_RESOLVING_ACTION.values())
    act_turns = Counter(r["turn"] for r in records
                        if (r.get("agent_payload") or {}).get("action") in resolving)
    print(f"  red lines  : {over} overpromise (LLM-detected) + {leak} credential leak "
          f"(regex-detected) = {over + leak}")
    print(f"  action turn: {dict(sorted(act_turns.items()))}  "
          f"(spread is what gives PPR/IRR any variance)")

    for cat, n in sorted(Counter(g["gold_category"] for g in gold).items(), key=lambda x: -x[1]):
        print(f"     {cat:<34} {n}")


if __name__ == "__main__":
    main()
