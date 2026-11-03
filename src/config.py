import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path=None):
    """Load KEY=VALUE lines from .env into os.environ (no dependency, never prints values).
    Values in .env win over stale shell variables. If .env supplies an API key but no auth token,
    any inherited ANTHROPIC_AUTH_TOKEN is dropped for this process so a stale bearer token
    can't shadow the key (the cause of '401 Invalid bearer token')."""
    p = Path(path) if path else ROOT / ".env"
    if not p.is_file():
        return []
    loaded = []
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.replace("export ", "", 1).strip(), v.strip().strip("'\"")
        if k and v:
            os.environ[k] = v
            loaded.append(k)
    if "ANTHROPIC_API_KEY" in loaded and "ANTHROPIC_AUTH_TOKEN" not in loaded:
        os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
    return loaded


ENV_LOADED = load_env()
DATA = ROOT / "data"
CASES = DATA / "cases"
GEN_RULES = DATA / "generated_rules"
RESULTS = ROOT / "results"
CACHE = RESULTS / "cache"

# --- Models (override with env vars). Use different models for judge vs. verifier
# so you can separate "self-enhancement" from genuine verification gains.
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-sonnet-5-5")
VERIFIER_CROSS_MODEL = os.environ.get("VERIFIER_MODEL", "claude-opus-5-5")
RULEWRITER_MODEL = os.environ.get("RULEWRITER_MODEL", "claude-opus-5-5")

TEMPERATURE = float(os.environ["TEMPERATURE"]) if "TEMPERATURE" in os.environ else None
MAX_TOKENS = 4096

N_TEST_CASES = 20
N_TRAIN_CASES = 2          # used only to show the rule-writing LLM an example
GEN_RULE_SAMPLES = 3       # independent LLM-written rulesets (arms D1..D3)
VERIFY_PASSES = 3
