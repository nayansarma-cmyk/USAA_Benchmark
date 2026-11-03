"""Executes an LLM-written ruleset in a separate isolated interpreter (python -I)."""
import importlib.util, json, sys

path = sys.argv[1]
payload = json.loads(sys.stdin.read())
spec = importlib.util.spec_from_file_location("gen_rules", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
res = mod.detect_changes(payload["text_a"], payload["text_b"])
print(json.dumps([dict(r) for r in res]))
