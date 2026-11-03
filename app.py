"""Local web UI for the policy-diff benchmark.   Start with:  streamlit run app.py"""
import contextlib, glob, io, json, os, sys, time
import pandas as pd
import streamlit as st

from src import arms, config, probes, prompts, run as runner, score

st.set_page_config(page_title="Policy Diff Benchmark", page_icon="📋", layout="wide")

MODEL_PRESETS = ["claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
ARM_INFO = {
    "A_rules": "Deterministic ruleset (no AI)",
    "B_llm": "AI reads both versions and lists changes",
    "C_llm_plus_rules": "AI + your ruleset as guidance",
    "E_hybrid": "Rules for structure, AI judges changed clauses",
    "D1_llm_written_rules": "Rules written by AI (sample 1)",
    "D2_llm_written_rules": "Rules written by AI (sample 2)",
    "D3_llm_written_rules": "Rules written by AI (sample 3)",
}
PROBE_INFO = {
    "none": "Baseline (no bias test)",
    "swap": "Swap document order",
    "authority": "Fake compliance sign-off",
    "bandwagon": "Fake prior reviewers",
    "padding": "Long identical boilerplate",
    "distraction": "Reordered / reflowed text",
}
STATUS_COLOR = {"HIT": "#1b7f3b", "MISSED": "#c0392b", "FALSE ALARM": "#c0392b", "COSMETIC FALSE ALARM": "#b9770e"}


def case_files():
    return sorted(glob.glob(str(config.CASES / "test_*.json")), key=lambda f: int(os.path.basename(f)[5:-5]))


def runs_file(mock):
    return config.RESULTS / ("runs_mock.jsonl" if mock else "runs.jsonl")


def err_file(mock):
    return config.RESULTS / ("errors_mock.jsonl" if mock else "errors.jsonl")


def parse_md_tables(md):
    """Split report markdown into [(heading, DataFrame)]."""
    out, title, rows = [], None, []

    def flush():
        if title and len(rows) > 2:
            hdr = [c.strip() for c in rows[0].strip("|").split("|")]
            data = [[c.strip() for c in r.strip("|").split("|")] for r in rows[2:]]
            df = pd.DataFrame(data, columns=hdr)
            for c in df.columns:
                conv = pd.to_numeric(df[c], errors="coerce")
                if conv.notna().all():
                    df[c] = conv
            out.append((title, df))
    for line in md.splitlines():
        if line.startswith("## "):
            flush(); title, rows = line[3:], []
        elif line.startswith("|"):
            rows.append(line)
    flush()
    return out


def build_report(mock):
    f = runs_file(mock)
    if not f.exists() or f.stat().st_size == 0:
        return None
    old = sys.argv
    sys.argv = ["score", "--file", str(f)]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            score.main()
    finally:
        sys.argv = old
    return (config.RESULTS / ("report_mock.md" if mock else "report.md")).read_text(encoding="utf-8")


@st.cache_resource(show_spinner=False)
def load_rows(path, mtime):
    cases = {c["id"]: c for c in (json.load(open(f)) for f in case_files())}
    rows = [score.label_row(json.loads(l)) for l in open(path) if l.strip()]
    for r in rows:
        r["s"] = score.score_one(r["pred"], cases[r["case"]])
        r["f1"] = score.prf(r["s"]["tp"], r["s"]["fp"], r["s"]["fn"])[2]
    return rows, cases


def models_input(label, default, key, multi=True, help=None):
    """Preset picker + free-text box so newly released model IDs can be used without code changes."""
    if multi:
        picked = st.multiselect(label, MODEL_PRESETS, default=default, key=key, help=help)
    else:
        picked = [st.selectbox(label, MODEL_PRESETS, index=MODEL_PRESETS.index(default[0]) if default[0] in MODEL_PRESETS else 0,
                               key=key, help=help)]
    extra = st.text_input("…or custom model ID(s), comma-separated", key=key + "_x", placeholder="e.g. claude-sonnet-5-5")
    picked += [m.strip() for m in extra.split(",") if m.strip() and m.strip() not in picked]
    return picked


def ping_models(models):
    import anthropic
    client = anthropic.Anthropic(max_retries=2)
    res = []
    for m in models:
        t0 = time.time()
        try:
            r = client.messages.create(model=m, max_tokens=8, messages=[{"role": "user", "content": "Reply with OK"}])
            res.append((m, True, f"OK ({time.time() - t0:.1f}s)"))
        except Exception as e:
            res.append((m, False, f"{type(e).__name__}: {str(e)[:160]}"))
    return res


# ======================= sidebar =======================
st.sidebar.title("⚙️ Settings")
mock = st.sidebar.toggle("Demo mode (no API calls)", value=not os.environ.get("ANTHROPIC_API_KEY"),
                         help="Fake AI so you can try the app offline. Demo numbers are NOT meaningful and are stored separately.")
if mock:
    st.sidebar.warning("Demo mode: results are fake and only prove the pipeline runs.")
else:
    # Show which credential sources the SDK will see (presence only, never values).
    has_key, has_tok, has_url = (bool(os.environ.get(v)) for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"))
    if config.ENV_LOADED:
        st.sidebar.caption(f"Loaded from .env: {', '.join(config.ENV_LOADED)}")
    st.sidebar.caption(f"ANTHROPIC_API_KEY:{'set' if has_key else 'not set'}  \n"
                       f"ANTHROPIC_AUTH_TOKEN: {'set' if has_tok else 'not set'}  \n"
                       f"ANTHROPIC_BASE_URL: {'set (custom endpoint)' if has_url else 'not set (api.anthropic.com)'}")
    if has_key:
        k = os.environ["ANTHROPIC_API_KEY"]
        problems = []
        if not k.startswith("sk-ant-"):
            problems.append("does not start with `sk-ant-` (not a standard Anthropic API key)")
        if k != k.strip() or any(ch.isspace() for ch in k):
            problems.append("contains whitespace or a line break")
        if any(ch in k for ch in "\"'`"):
            problems.append("contains quote characters")
        if len(k) < 80:
            problems.append(f"is only {len(k)} characters (standard keys are ~100+, likely truncated)")
        if problems:
            st.sidebar.error("API key format problem: it " + "; and ".join(problems) + ".")
        else:
            st.sidebar.caption(f"Key format looks valid ({len(k)} chars). If it is still rejected, it is revoked, "
                               "from another account, or needs a different endpoint.")
    if has_url:
        st.sidebar.warning("ANTHROPIC_BASE_URL is set: requests go to a custom endpoint, not api.anthropic.com. "
                           "A direct Anthropic key will be rejected there. Remove that line from .env to use Anthropic directly.")
    if has_tok:
        st.sidebar.warning("ANTHROPIC_AUTH_TOKEN is set; the SDK sends it as a Bearer token and a stale one causes "
                           "'401 Invalid bearer token'. Paste a key below to override it for this session.")
    with st.sidebar.expander("Use a different API key", expanded=not (has_key or has_tok)):
        key = st.text_input("Anthropic API key", type="password", help="Kept in memory for this session only.")
        if key and st.button("Use this key"):
            os.environ["ANTHROPIC_API_KEY"] = key.strip()
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)   # this process only, so the bearer token can't shadow the key
            st.rerun()
    if not (has_key or has_tok):
        st.sidebar.error("Enter an API key or switch on Demo mode.")

st.title("📋 Policy Diff Benchmark")
st.caption("Do AI models spot material changes between two auto-policy versions better than a deterministic ruleset?")

tab_run, tab_res, tab_proc, tab_cases, tab_help = st.tabs(
    ["▶️ Run", "📊 Scores", "🔬 Process breakdown", "🔍 Browse cases", "❓ How it works"])

# ======================= Run tab =======================
with tab_run:
    total_cases = len(case_files())
    if total_cases == 0:
        st.error("No test cases found. Run `python -m src.mutate --n 20` first.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Methods")
        sel_arms = st.multiselect("Methods to compare", list(ARM_INFO), default=["A_rules", "B_llm", "E_hybrid"],
                                  format_func=lambda a: f"{a} — {ARM_INFO[a]}",
                                  help="A_rules is the deterministic baseline. Include it to compare AI against it.")
        sel_probes = st.multiselect("Bias tests", probes.PROBES, default=["none"],
                                    format_func=lambda p: f"{p} — {PROBE_INFO.get(p, '')}")
        has_llm = any(arms.ARMS[a][1] for a in sel_arms)
        st.markdown("##### Models")
        judges = models_input("AI judge model(s) — each is run and scored separately", ["claude-sonnet-5-5"], "judges",
                              help="Pick several to compare models side by side in one run.")
        verifier = st.radio("Verifier", ["cross", "same"], horizontal=True,
                            help="cross = a different model checks the answer; same = each judge checks itself")
        vmodels = models_input("Verifier model (used when Verifier = cross)", ["claude-opus-5-5"], "vmodel", multi=False)
        vmodel = vmodels[-1]
    with c2:
        st.markdown("##### Size of the run")
        k = st.slider("Number of test cases", 1, max(total_cases, 1), min(3, max(total_cases, 1)))
        runs = st.slider("Repeats per AI method", 1, 5, 2, help="Used to measure run-to-run consistency.")
        passes = st.slider("AI verification passes", 0, 3, config.VERIFY_PASSES)
        if has_llm and not judges:
            st.error("Pick at least one judge model.")
        if not mock and has_llm:
            if st.button("🔌 Test connection to selected models"):
                with st.spinner("Pinging models..."):
                    for m, ok, msg in ping_models(list(dict.fromkeys(judges + ([vmodel] if verifier == "cross" else [])))):
                        (st.success if ok else st.error)(f"`{m}` — {msg}")

    needs_gen = [a for a in sel_arms if a.startswith("D") and not (config.GEN_RULES / f"rules_{a[1]}.py").exists()]
    if needs_gen:
        st.warning(f"{', '.join(needs_gen)} need AI-written rulesets that don't exist yet.")
        rw = models_input("Model that writes the rulesets", ["claude-opus-5-5"], "rulewriter", multi=False)
        if st.button("Generate AI-written rulesets"):
            with st.spinner("Asking the AI to write rules..."):
                from src.llm import LLM
                config.RULEWRITER_MODEL = rw[-1]
                t = runner.load_cases("train")[0]
                arms.generate_rules(LLM(mock=mock), t["text_a"], t["text_b"])
            st.rerun()
    if any(a.startswith("D") for a in sel_arms):
        st.caption("⚠️ D arms execute AI-written code. Run inside a VM/container.")

    ready = bool(sel_arms and sel_probes and total_cases and (judges or not has_llm))
    if ready:
        nj = len(judges) if has_llm else 1
        chains = runner.plan(sel_arms, sel_probes, runs, k, nj)
        llm_chains = sum(1 for a in sel_arms if arms.ARMS[a][1]) * k * len(sel_probes) * runs * nj
        calls = llm_chains * (1 + passes)
        st.info(f"**{chains}** chains · up to **{calls}** API calls (cached/already-finished chains are skipped)"
                if calls and not mock else f"**{chains}** chains · no API calls")

    if st.button("▶️ Start benchmark", type="primary", disabled=not ready):
        if not mock and has_llm and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            st.error("Set an API key in the sidebar or enable Demo mode.")
        else:
            bar, status = st.progress(0.0), st.empty()

            def on_progress(done, total, label):
                bar.progress(done / total if total else 1.0)
                status.text(f"{done}/{total} — {label}")
            try:
                r = runner.execute(sel_arms, sel_probes, runs, k, passes, verifier, mock, progress=on_progress,
                                   judge_models=judges or None, verifier_model=vmodel)
                bar.progress(1.0)
                st.success(f"Done. {r['new']} new chains computed. See **Scores** and **Process breakdown**.")
                if r["errors"]:
                    st.warning(f"{r['errors']} chain(s) failed and were NOT scored — details on the Scores tab. Re-run to retry them.")
            except Exception as e:
                st.error(f"Run stopped: {e}")
                if "AuthenticationError" in str(e):
                    st.info("Authentication failed before any chain was scored, so nothing was saved. Check the credential "
                            "status in the sidebar, use *Test connection*, then start again; finished work is cached.")

    st.divider()
    fpath = runs_file(mock)
    if fpath.exists():
        st.caption(f"Saved results: `{fpath.name}` ({sum(1 for _ in open(fpath))} rows)")
        if st.button("🗑️ Clear saved results (API response cache is kept)"):
            fpath.unlink()
            if err_file(mock).exists():
                err_file(mock).unlink()
            st.rerun()

# ======================= Scores tab =======================
with tab_res:
    f = runs_file(mock)
    try:
        md = build_report(mock)
    except Exception as e:
        md = None
        st.error(f"Could not score results: {type(e).__name__}: {e}")
    if md is None:
        st.info("No results yet — run a benchmark first.")
    else:
        rows, cases = load_rows(str(f), f.stat().st_mtime)
        tables = dict(parse_md_tables(md))

        # ---- reliability panel ----
        n_calls = sum(len(r["calls"]) for r in rows if r["level"] == 0 and r.get("calls")) if rows else 0
        bad_parse = sum(1 for r in rows for c in r.get("calls", []) if not c["parse_ok"])
        n_err = sum(1 for _ in open(err_file(mock))) if err_file(mock).exists() else 0
        n_case_used = len({r["case"] for r in rows})
        with st.container(border=True):
            st.markdown("##### Data health")
            h1, h2, h3, h4 = st.columns(4)
            h1.metric("Cases scored", n_case_used)
            h2.metric("Failed chains (not scored)", n_err)
            h3.metric("Unparseable AI replies", bad_parse)
            h4.metric("Models", len({r.get("judge") for r in rows if r.get("judge", "-") != "-"}) or "-")
            if n_err:
                with st.expander("Show errors"):
                    st.dataframe(pd.DataFrame([json.loads(l) for l in open(err_file(mock))]), width="stretch", hide_index=True)
            if bad_parse:
                st.warning("Some AI replies were not valid JSON and were scored as 'no change' (or the prior answer was kept). "
                           "This lowers that model's recall — see the Process breakdown tab for the raw replies.")
            if n_case_used < 20:
                st.caption(f"Only {n_case_used} case(s) scored. Treat differences as indicative until the confidence intervals in table 2 exclude zero.")

        # ---- headline ----
        acc = tables.get("1. Accuracy (pooled TP/FP/FN over all cases and runs)")
        if acc is not None:
            st.subheader("Headline: model & method scores")
            c1, c2 = st.columns(2)
            probe_pick = c1.selectbox("Bias test", sorted(acc["probe"].unique()), index=sorted(acc["probe"].unique()).index("none") if "none" in set(acc["probe"]) else 0)
            maxp = int(acc["passes"].max())
            level_pick = c2.selectbox("After AI verification pass", ["final"] + list(range(maxp + 1)),
                                      help="0 = the model's first answer; 1..N = after each extra AI check. Rules always show their single result.")
            sub = acc[acc["probe"] == probe_pick]
            if level_pick == "final":
                sub = sub.sort_values("passes").groupby(["arm", "verifier"], as_index=False).last()
            else:
                sub = sub[(sub["passes"] == level_pick) | (sub["verifier"] == "-")]
            sub = sub.sort_values("F1", ascending=False)
            cols = [c for c in ["arm", "verifier", "passes", "precision", "recall", "F1", "cosmetic false-alarm rate",
                                "structured recall", "lexical recall", "semantic recall", "added/removed recall",
                                "cases x runs", "tokens/chain"] if c in sub.columns]
            st.dataframe(sub[cols], width="stretch", hide_index=True, column_config={
                "F1": st.column_config.ProgressColumn("F1", min_value=0, max_value=1, format="%.3f"),
                "recall": st.column_config.ProgressColumn("recall", min_value=0, max_value=1, format="%.3f"),
                "precision": st.column_config.ProgressColumn("precision", min_value=0, max_value=1, format="%.3f")})
            st.bar_chart(sub.set_index("arm")[["precision", "recall", "F1"]])
            st.caption("Rows labelled `@ model` are AI arms. `A_rules` / `D*` are deterministic. "
                       "Semantic recall (changes with no lexical tell) is where AI-vs-rules is decided.")

        # ---- per-case matrix ----
        with st.expander("Per-case F1 matrix (final answer, baseline probe)"):
            base = [r for r in rows if r["probe"] == "none"]
            last = {}
            for r in base:
                kk = (r["case"], r["arm"], r["verifier"], r["run"])
                if kk not in last or r["level"] > last[kk]["level"]:
                    last[kk] = r
            m = pd.DataFrame([dict(case=r["case"], arm=r["arm"], f1=r["f1"]) for r in last.values()])
            if not m.empty:
                piv = m.groupby(["case", "arm"])["f1"].mean().unstack()
                st.dataframe(piv, width="stretch", column_config={c: st.column_config.ProgressColumn(c, min_value=0, max_value=1, format="%.2f") for c in piv.columns})

        st.subheader("All report tables")
        for title, df in tables.items():
            with st.expander(title, expanded=title.startswith("2.")):
                st.dataframe(df, width="stretch", hide_index=True)
        st.download_button("Download report.md", md, file_name="report.md")

# ======================= Process breakdown tab =======================
with tab_proc:
    f = runs_file(mock)
    if not f.exists() or f.stat().st_size == 0:
        st.info("Run a benchmark first.")
    else:
        rows, cases = load_rows(str(f), f.stat().st_mtime)
        p1, p2, p3, p4 = st.columns(4)
        case_id = p1.selectbox("Case", sorted({r["case"] for r in rows}, key=lambda x: int(x.split("_")[1])))
        arm_label = p2.selectbox("Method / model", sorted({r["arm"] for r in rows if r["case"] == case_id}))
        pr = p3.selectbox("Bias test", sorted({r["probe"] for r in rows if r["case"] == case_id and r["arm"] == arm_label}), key="proc_probe")
        cand = [r for r in rows if r["case"] == case_id and r["arm"] == arm_label and r["probe"] == pr]
        run_ids = sorted({r["run"] for r in cand})
        run_id = p4.selectbox("Repeat #", run_ids, format_func=lambda i: f"run {i + 1}")
        chain = sorted([r for r in cand if r["run"] == run_id], key=lambda r: r["level"])
        case = cases[case_id]

        # ---------- side-by-side: golden standard vs deterministic vs LLM ----------
        st.markdown("##### Side-by-side: golden standard vs deterministic vs LLM")
        combos = sorted({(r["arm"], r["verifier"]) for r in rows if r["case"] == case_id and r["probe"] == pr})

        def cname(a, v):
            return a if sum(1 for x in combos if x[0] == a) == 1 else f"{a} [{v}]"
        opts = {cname(a, v): (a, v) for a, v in combos}
        sc1, sc2, sc3 = st.columns([3, 1, 1])
        chosen = sc1.multiselect("Methods to show", list(opts), default=list(opts))
        every = sc2.checkbox("Every verification pass", value=False, help="One column per AI check pass instead of just the final answer.")
        detail = sc3.checkbox("Show what each said", value=False, help="Adds the method's own description to each flagged cell.")

        lab = case["labels"]
        key_items = [(e, score.canon(e["location"], lab)) for e in case["key"]]
        key_canon = {c for _, c in key_items}
        cols = {}   # column title -> (canon->description, canon->location as written, run-row)
        for nm in chosen:
            a, v = opts[nm]
            cand = [r for r in rows if r["case"] == case_id and r["probe"] == pr and r["arm"] == a and r["verifier"] == v]
            rn = run_id if run_id in {r["run"] for r in cand} else min(r["run"] for r in cand)
            ch = sorted([r for r in cand if r["run"] == rn], key=lambda r: r["level"])
            for r in (ch if every else ch[-1:]):
                title = nm if len(ch) == 1 else (f"{nm} · {'first answer' if r['level'] == 0 else f'after check {r['level']}'}" if every else f"{nm} (final)")
                P = {score.canon(c.get("location", ""), lab): c.get("description", "") for c in r["pred"]}
                L = {score.canon(c.get("location", ""), lab): c.get("location", "") for c in r["pred"]}
                cols[title] = (P, L, r)

        table = []
        for e, c in key_items:
            row = {"Location": e["location"],
                   "Golden standard": ("MATERIAL change" if e["expected"] else "NOT material (should be ignored)") + f" · {e['tier']}",
                   "What actually changed": f"{e['old']} → {e['new']}"}
            for title, (P, L, r) in cols.items():
                hit = c in P
                txt = ("✅ Found" if hit else "❌ Missed") if e["expected"] else ("⚠️ False alarm" if hit else "✅ Ignored")
                row[title] = txt + (f" — {P[c]}" if detail and hit and P[c] else "")
            table.append(row)
        extras = {}
        for title, (P, L, r) in cols.items():
            for c, loc in L.items():
                if c not in key_canon:
                    extras.setdefault(c, loc)
        for c, loc in extras.items():
            row = {"Location": loc, "Golden standard": "Not a change in the answer key", "What actually changed": "—"}
            for title, (P, L, r) in cols.items():
                row[title] = ("⚠️ False alarm" + (f" — {P[c]}" if detail and P.get(c) else "")) if c in P else "—"
            table.append(row)
        n_exp = sum(e["expected"] for e in case["key"])
        for lbl, fn in [("SCORE · real changes found", lambda s: f"{s['tp']}/{n_exp}"),
                        ("SCORE · false alarms", lambda s: str(s["fp"])),
                        ("SCORE · F1", lambda s: f"{score.prf(s['tp'], s['fp'], s['fn'])[2]:.2f}")]:
            row = {"Location": lbl, "Golden standard": f"{n_exp} real changes", "What actually changed": ""}
            for title, (P, L, r) in cols.items():
                row[title] = fn(r["s"])
            table.append(row)
        if cols:
            sbs = pd.DataFrame(table)

            def color(v):
                v = str(v)
                return ("color: #1b7f3b; font-weight: 600" if v.startswith("✅") else
                        "color: #c0392b; font-weight: 600" if v.startswith("❌") else
                        "color: #b9770e; font-weight: 600" if v.startswith("⚠️") else "")
            st.dataframe(sbs.style.map(color, subset=list(cols)), width="stretch", hide_index=True, height=min(900, 38 * (len(sbs) + 1)))
            st.caption("✅ Found / Ignored = correct · ❌ Missed = real change not flagged · ⚠️ False alarm = flagged something that is not a real change. "
                       f"Showing {case_id}, bias test '{pr}', repeat {run_id + 1} for AI methods (deterministic methods run once).")
            st.download_button("Download this table (CSV)", sbs.to_csv(index=False), file_name=f"{case_id}_{pr}_side_by_side.csv")
        else:
            st.info("Pick at least one method.")

        st.markdown("##### 1 · Ground truth (answer key)")
        st.dataframe(pd.DataFrame(case["key"])[["location", "tier", "expected", "old", "new"]], width="stretch", hide_index=True)

        base_name = arm_label.split(" @ ")[0]
        if base_name in ("B_llm", "C_llm_plus_rules"):
            with st.expander("What the judge model was asked (exact prompt)"):
                ta, tb, swap = probes.apply(pr, case["text_a"], case["text_b"], seed=case["seed"])
                s, u = prompts.judge(ta, tb, swap, base_name == "C_llm_plus_rules")
                st.caption("System prompt"); st.code(s, language="text")
                st.caption("User message (both policy versions)"); st.code(u, language="text", height=300)

        st.markdown("##### 2 · Step by step")
        prev = None
        for r in chain:
            s = r["s"]
            title = ("Initial answer" if r["level"] == 0 else f"After AI verification pass {r['level']}") \
                if len(chain) > 1 else "Result"
            with st.container(border=True):
                st.markdown(f"**{title}** — F1 {r['f1']:.2f} · found {s['tp']} real · missed {s['fn']} · false alarms {s['fp']} "
                            f"(of which cosmetic {s['cos_fp']})")
                if prev is not None:
                    gained, lost = s["TP"] - prev["s"]["TP"], prev["s"]["TP"] - s["TP"]
                    fp_add, fp_rm = s["FP"] - prev["s"]["FP"], prev["s"]["FP"] - s["FP"]
                    msg = []
                    if gained: msg.append(f"✅ now finds: {', '.join(sorted(gained))}")
                    if lost: msg.append(f"❌ dropped real change(s): {', '.join(sorted(lost))}")
                    if fp_rm: msg.append(f"🧹 removed false alarm(s): {', '.join(sorted(fp_rm))}")
                    if fp_add: msg.append(f"⚠️ added false alarm(s): {', '.join(sorted(fp_add))}")
                    st.write("  \n".join(msg) if msg else "No change vs previous step.")
                ex = pd.DataFrame(score.explain(r["pred"], case))
                if not ex.empty:
                    st.dataframe(ex.style.map(lambda v: f"color: {STATUS_COLOR.get(v, 'inherit')}; font-weight: 600", subset=["status"]),
                                 width="stretch", hide_index=True)
                for c in r.get("calls", []):
                    with st.expander(f"Model call · `{c['model']}` · {c['tin']} in / {c['tout']} out tokens · {c['latency']}s"
                                     + ("" if c["parse_ok"] else " · ⚠️ UNPARSEABLE REPLY")):
                        st.code(c["text"], language="json")
                if r["level"] == 0 and base_name in ("A_rules", "D1_llm_written_rules", "D2_llm_written_rules", "D3_llm_written_rules"):
                    st.caption("Rule triggers: " + "; ".join(f"{p.get('location')}: {p.get('description')}" for p in r["pred"]))
            prev = r
        last = chain[-1]
        st.caption(f"Chain total: {last['tin']} input + {last['tout']} output tokens, {last['latency']}s model time.")

        st.markdown("##### 3 · Compare methods on this same case")
        cmp = {}
        for r in rows:
            if r["case"] == case_id and r["probe"] == pr:
                cmp.setdefault((r["arm"], r["verifier"], r["run"]), []).append(r)
        table = []
        for (a, v, rn), lst in cmp.items():
            L = max(lst, key=lambda x: x["level"])
            table.append(dict(method=a, verifier=v, run=rn + 1, F1=L["f1"], found=L["s"]["tp"], missed=L["s"]["fn"],
                              false_alarms=L["s"]["fp"], tokens=L["tin"] + L["tout"]))
        st.dataframe(pd.DataFrame(table).sort_values(["method", "run"]), width="stretch", hide_index=True,
                     column_config={"F1": st.column_config.ProgressColumn("F1", min_value=0, max_value=1, format="%.2f")})

# ======================= Browse cases tab =======================
with tab_cases:
    files = case_files()
    if not files:
        st.info("No cases generated.")
    else:
        pick = st.selectbox("Case", files, format_func=lambda f: os.path.basename(f)[:-5], key="browse")
        case = json.load(open(pick))
        st.subheader("Answer key (what really changed)")
        st.dataframe(pd.DataFrame(case["key"]), width="stretch", hide_index=True)
        a, b = st.columns(2)
        a.text_area("Original", case["text_a"], height=400)
        b.text_area("Renewal", case["text_b"], height=400)

# ======================= Help tab =======================
with tab_help:
    st.markdown("""
**Workflow**
1. **Run** — choose methods (include `A_rules` as the deterministic baseline), one or more Claude models, and a small case count. Use *Test connection* first.
2. **Scores** — precision / recall / F1 per method *and per model*, per-tier recall, and the statistical comparison against the rules.
3. **Process breakdown** — pick any case + method + model and see exactly what it flagged, what it missed, how each AI check pass changed the answer, and the raw model replies.

**How results are kept trustworthy**
- Every AI result is stored with the judge and verifier model that produced it; switching models never reuses another model's results.
- A chain is saved only if every step finished. Failures are logged (Scores → Data health) and are never silently scored as zero.
- Answer keys are generated by the mutation script, not by an AI. `python -m tests.test_pipeline` checks the scorer (a perfect answer scores 1.0, an empty one 0) and the multi-model bookkeeping.
- Demo-mode results are kept in separate files and are meaningless.

**Reading the numbers**
- **Recall** – share of real material changes found. **Precision** – share of flagged items that were real.
- **Cosmetic false-alarm rate** – wording/format-only edits wrongly flagged.
- **Semantic recall** – changes with no lexical tell; the key test for AI vs rules.
- **Consistency** – similarity of answers across repeats. **Flip rate** – how often a bias probe changes the answer vs normal noise.

Review and validate results before sharing outside the team.
""")
