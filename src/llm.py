import hashlib, json, os, random, re, time
from . import config, rules


class LLM:
    def __init__(self, mock=False):
        self.mock = mock
        self.client = None
        config.CACHE.mkdir(parents=True, exist_ok=True)

    def _client(self):
        if self.client is None:
            import anthropic  # needs ANTHROPIC_API_KEY
            self.client = anthropic.Anthropic(max_retries=6)  # ride out 429/529 instead of failing a chain
        return self.client

    def complete(self, model, system, user, nonce=""):
        h = hashlib.sha1(json.dumps([model, system, user, nonce, self.mock]).encode()).hexdigest()
        f = config.CACHE / f"{h}.json"
        if f.exists():
            return json.loads(f.read_text())
        t0 = time.time()
        if self.mock:
            text, tin, tout = _mock(user, h), 0, 0
        else:
            kw = dict(model=model, max_tokens=config.MAX_TOKENS, system=system, messages=[{"role": "user", "content": user}])
            if config.TEMPERATURE is not None:
                kw["temperature"] = config.TEMPERATURE
            r = self._client().messages.create(**kw)
            text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
            tin, tout = r.usage.input_tokens, r.usage.output_tokens
        out = dict(text=text, tin=tin, tout=tout, latency=round(time.time() - t0, 3), model=model)
        f.write_text(json.dumps(out))
        return out


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


# ---- offline mock so the whole pipeline can be tested without an API key ----
def _mock(user, h):
    rng = random.Random(int(h[:8], 16))
    if "[[TASK:rulegen]]" in user:
        return "```python\ndef detect_changes(text_a, text_b):\n    a = dict(l.split(': ',1) for l in text_a.splitlines() if ': ' in l)\n    b = dict(l.split(': ',1) for l in text_b.splitlines() if ': ' in l)\n    return [dict(location=k, change_type='structured', description='diff') for k in a if a[k] != b.get(k)]\n```"
    if "[[TASK:clause_review]]" in user:
        ids = re.findall(r'<SECTION id="([^"]+)">', user)
        return json.dumps({"results": [{"location": i, "material": rng.random() < 0.7, "description": "mock"} for i in ids]})
    if "[[TASK:verify]]" in user:
        cur = parse_json(user.split("<PROPOSED>")[1]).get("changes", [])
        return json.dumps({"changes": [c for c in cur if rng.random() > 0.05]})
    a = re.search(r"<ORIGINAL>\n(.*?)</ORIGINAL>", user, re.S).group(1)
    b = re.search(r"<RENEWAL>\n(.*?)</RENEWAL>", user, re.S).group(1)
    mat = rules.diff(a, b)["material"]
    out = [c for c in mat if rng.random() > 0.2]
    return json.dumps({"changes": out})
