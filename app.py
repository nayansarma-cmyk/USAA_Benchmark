"""Policy change benchmark: local web UI.   Start with:  streamlit run app.py"""
import contextlib, io, json, os, sys, time
import pandas as pd
import streamlit as st

from src import arms, config, probes, prompts, run as runner, score, viewmodel as vm

st.set_page_config(page_title="Policy change benchmark", page_icon=":material/fact_check:", layout="wide")

GOOD, WARN, BAD = "#1b7f3b", "#b9770e", "#c0392b"


# ============================================================ helpers
def runs_file(mock):
    return config.RESULTS / ("runs_mock.jsonl" if mock else "runs.jsonl")


def err_file(mock):
    return config.RESULTS / ("errors_mock.jsonl" if mock else "errors.jsonl")


def has_results(mock):
    f = runs_file(mock)
    return f.exists() and f.stat().st_size > 0


@st.cache_resource(show_spinner=False)
def load_rows(path, mtime):
    return vm.load_scored(path)


@st.cache_resource(show_spinner=False)
def get_summary(path, mtime, probe, level, cset):
    rows, _ = load_rows(path, mtime)
    rows = vm.filter_set(rows, cset)
    return vm.summarize(rows, probe, level), vm.compare_to_rules(rows, probe, level)


@st.cache_resource(show_spinner=False)
def get_report(path, mtime, mock, cset):
    old = sys.argv
    sys.argv = ["score", "--file", path] + (["--set", cset] if cset else [])
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            score.main()
    finally:
        sys.argv = old
    md = (config.RESULTS / ("report_mock.md" if mock else "report.md")).read_text(encoding="utf-8")
    return md, parse_md_tables(md)


def parse_md_tables(md):
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


def avg_call_seconds():
    f = runs_file(False)
    if not f.exists():
        return 8.0
    lat = [c["latency"] for l in open(f) if l.strip() for c in json.loads(l).get("calls", []) if c.get("latency")]
    return max(2.0, sum(lat) / len(lat)) if lat else 8.0


def ping_models(models):
    import anthropic
    client = anthropic.Anthropic(max_retries=2)
    res = []
    for m in models:
        t0 = time.time()
        try:
            client.messages.create(model=m, max_tokens=8, messages=[{"role": "user", "content": "Reply with OK"}])
            res.append((m, True, f"working ({time.time() - t0:.1f}s)"))
        except Exception as e:
            res.append((m, False, f"{type(e).__name__}: {str(e)[:160]}"))
    return res


def mark_color(v):
    v = str(v)
    return (f"color: {GOOD}; font-weight: 600" if v.startswith(vm.OK_MARK) else
            f"color: {BAD}; font-weight: 600" if v.startswith(vm.MISS_MARK) else
            f"color: {WARN}; font-weight: 600" if v.startswith((vm.FALSE_MARK, vm.MIX_MARK)) else "")


def pct_col(label, help=None):
    return st.column_config.ProgressColumn(label, min_value=0, max_value=100, format="%.0f%%", help=help)


# ============================================================ sidebar: connection
st.sidebar.header("Connection", divider=False)
mock = st.sidebar.toggle(
    "Practice mode", value=not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")),
    help="Uses made-up AI answers so you can explore the app for free, offline. Practice results are NOT meaningful and are kept separate.")
if mock:
    st.sidebar.warning("Practice mode: the AI answers are fake. Use it to learn the app, not to draw conclusions.",
                       icon=":material/science:")
else:
    has_key, has_tok, has_url = (bool(os.environ.get(v)) for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"))
    problems = []
    if has_key:
        k = os.environ["ANTHROPIC_API_KEY"]
        if not k.startswith("sk-ant-"):
            problems.append("does not start with sk-ant-")
        if any(ch.isspace() for ch in k) or any(ch in k for ch in "\"'`"):
            problems.append("contains spaces or quote marks")
        if len(k) < 80:
            problems.append(f"is only {len(k)} characters, so it was probably cut off")
    if has_key and not problems:
        st.sidebar.success("API key found", icon=":material/check_circle:")
    elif has_key:
        st.sidebar.error("API key looks wrong: it " + "; ".join(problems) + ".", icon=":material/error:")
    elif has_tok:
        st.sidebar.warning("Using an access token instead of an API key.", icon=":material/warning:")
    else:
        st.sidebar.error("No API key found. Add one below or switch on Practice mode.", icon=":material/key_off:")
    with st.sidebar.expander("Connection details", icon=":material/settings:", expanded=not (has_key or has_tok) or bool(problems)):
        if config.ENV_LOADED:
            st.caption(f"Loaded from .env: {', '.join(config.ENV_LOADED)}")
        st.caption(f"API key: {'set' if has_key else 'not set'}  \nAccess token: {'set' if has_tok else 'not set'}  \n"
                   f"Custom endpoint: {'set' if has_url else 'not set (uses api.anthropic.com)'}")
        if has_tok:
            st.warning("An access token is set. A stale one causes '401 Invalid bearer token'. Paste a key below to override it.")
        if has_url:
            st.warning("A custom endpoint is set, so a standard Anthropic key will be rejected there.")
        key = st.text_input("Use a different API key", type="password", help="Kept in memory for this session only.")
        if key and st.button("Use this key"):
            os.environ["ANTHROPIC_API_KEY"] = key.strip()
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
            st.rerun()
        if st.button("Test the connection", icon=":material/wifi_tethering:"):
            with st.spinner("Contacting the AI service..."):
                for m, ok, msg in ping_models([config.JUDGE_MODEL]):
                    (st.success if ok else st.error)(f"{vm.short_model(m)}: {msg}")

# ============================================================ header
st.title("Policy change benchmark", icon=":material/fact_check:")
st.caption("How do AI models compare with fixed rules at spotting meaningful changes between two versions of a car insurance policy?")

tab_sum, tab_run, tab_review, tab_cases, tab_route, tab_help = st.tabs([
    ":material/dashboard: Summary", ":material/play_arrow: Run a test", ":material/fact_check: Review table",
    ":material/compare: Case explorer", ":material/alt_route: Customer queries", ":material/help: How it works"])

# ============================================================ RUN
with tab_run:
    sets = vm.case_sets()
    case_set = (st.segmented_control("Which cases?", list(sets), default=list(sets)[0], required=True, key="run_set",
                                     format_func=lambda s: f"{vm.set_name(s)} ({sets[s]})",
                                     help="Results for different case sets are kept apart and never pooled.")
                if len(sets) > 1 else (list(sets)[0] if sets else None))
    total_cases = sets.get(case_set, 0)
    if total_cases == 0:
        st.error("No test cases found. Run `python -m src.mutate --n 20` first.", icon=":material/error:")

    st.subheader("1. How thorough should the test be?")
    PRESETS = {
        "Quick check": dict(cases=min(3, total_cases), runs=1, passes=1, probes=["none"],
                            blurb="3 cases, one attempt each. A few minutes. Best for a first look."),
        "Standard": dict(cases=total_cases, runs=3, passes=1, probes=["none"],
                         blurb=f"All {total_cases} cases, 3 attempts each so we can see how consistent each method is."),
        "Full study": dict(cases=total_cases, runs=3, passes=1, probes=list(probes.PROBES),
                           blurb="Everything in Standard, plus the 'trap' tests that try to mislead the AI. Takes the longest."),
        "Custom": None,
    }
    preset = st.segmented_control("Test size", list(PRESETS), default="Quick check", required=True, label_visibility="collapsed")
    if preset == "Custom":
        c1, c2, c3 = st.columns(3)
        n_case = c1.slider("Number of test cases", 1, max(total_cases, 1), min(3, max(total_cases, 1)))
        n_runs = c2.slider("Attempts per AI method", 1, 5, 2, help="More attempts show how consistent each AI is.")
        n_pass = c3.slider("AI double-check rounds", 0, 3, 1, help="After the AI answers, a second AI can review the answer. 0 = no review.")
        sel_probes = st.pills("Trap tests to include", probes.PROBES, selection_mode="multi", default=["none"],
                              format_func=lambda p: vm.PROBE_NAMES[p])
        sel_probes = sel_probes or ["none"]
    else:
        P = PRESETS[preset]
        n_case, n_runs, n_pass, sel_probes = P["cases"], P["runs"], P["passes"], P["probes"]
        st.caption(P["blurb"])

    st.subheader("2. What should be compared?")
    sel_arms = st.pills("Methods", list(vm.ARM_NAMES), selection_mode="multi", default=["A_rules", "B_llm", "E_hybrid"],
                        format_func=lambda a: vm.ARM_NAMES[a], label_visibility="collapsed")
    with st.expander("What do these methods mean?", icon=":material/info:"):
        for a in vm.ARM_NAMES:
            st.markdown(f"**{vm.ARM_NAMES[a]}**: {vm.ARM_HELP[a]}")
    has_llm = any(arms.ARMS[a][1] for a in sel_arms)
    judges = []
    if has_llm:
        judges = st.pills("Which AI models?", vm.MODEL_PRESETS, selection_mode="multi", default=["claude-sonnet-5-5"],
                          format_func=vm.short_model, help="Pick more than one to compare models side by side.") or []
    else:
        st.caption("No AI method selected, so no AI models are needed.")

    with st.expander("More options", icon=":material/tune:"):
        if has_llm:
            custom = st.text_input("Other model IDs (comma-separated)", placeholder="e.g. claude-sonnet-5-5",
                                   help="Use this for a newly released model that is not in the list above.")
            judges += [m.strip() for m in custom.split(",") if m.strip() and m.strip() not in judges]
            verifier = st.segmented_control("Who double-checks the AI's answer?", ["cross", "same"], default="cross", required=True,
                                            format_func=lambda v: "A different model" if v == "cross" else "The same model",
                                            help="A different model is a more independent check. 'Same model' tests whether an AI is biased toward its own answers.")
            vmodel = st.selectbox("Checking model (when a different model checks)", vm.MODEL_PRESETS,
                                  index=vm.MODEL_PRESETS.index("claude-opus-5-5"), format_func=vm.short_model)
            vmodel = vmodel or config.VERIFIER_CROSS_MODEL
        else:
            verifier, vmodel = "cross", config.VERIFIER_CROSS_MODEL
        needs_gen = [a for a in sel_arms if a.startswith("D") and not (config.GEN_RULES / f"rules_{a[1]}.py").exists()]
        if needs_gen:
            st.warning("The 'AI-written rules' methods need their rule sets created first.")
            rw = st.selectbox("Model that writes the rules", vm.MODEL_PRESETS, index=vm.MODEL_PRESETS.index("claude-opus-5-5"),
                              format_func=vm.short_model)
            if st.button("Create the AI-written rule sets"):
                with st.spinner("Asking the AI to write rules..."):
                    from src.llm import LLM
                    config.RULEWRITER_MODEL = rw
                    arms.generate_rules(LLM(mock=mock), *[runner.load_cases("train")[0][k] for k in ("text_a", "text_b")])
                st.rerun()
        if any(a.startswith("D") for a in sel_arms):
            st.caption("The AI-written rules run as code on this computer. Do this inside a VM or container.")
        if not mock and has_llm and st.button("Test the selected models", icon=":material/wifi_tethering:"):
            with st.spinner("Contacting the AI service..."):
                for m, ok, msg in ping_models(list(dict.fromkeys(judges + ([vmodel] if verifier == "cross" else [])))):
                    (st.success if ok else st.error)(f"{vm.short_model(m)}: {msg}")
        fp = runs_file(mock)
        if fp.exists():
            st.caption(f"Saved results: {sum(1 for _ in open(fp))} rows")
            if st.button("Clear saved results", icon=":material/delete:", help="Removes the saved scores. Cached AI replies are kept, so re-running is cheap."):
                fp.unlink()
                if err_file(mock).exists():
                    err_file(mock).unlink()
                st.rerun()

    st.subheader("3. Review and start")
    ready = bool(sel_arms and total_cases and (judges or not has_llm))
    if has_llm and not judges:
        st.warning("Pick at least one AI model.", icon=":material/warning:")
    if not sel_arms:
        st.warning("Pick at least one method.", icon=":material/warning:")
    if ready:
        nj = len(judges) if has_llm else 1
        chains = runner.plan(sel_arms, sel_probes, n_runs, n_case, nj)
        llm_chains = sum(1 for a in sel_arms if arms.ARMS[a][1]) * n_case * len(sel_probes) * n_runs * nj
        calls = llm_chains * (1 + n_pass)
        with st.container(border=True):
            st.markdown(f"**{n_case}** test cases · **{len(sel_arms)}** methods" + (f" · **{len(judges)}** AI model(s)" if has_llm else "")
                        + f" · **{len(sel_probes)}** condition(s)")
            if mock:
                st.caption("Practice mode: no AI requests will be made. Takes seconds.")
            elif calls:
                mins = calls * avg_call_seconds() / 60
                st.caption(f"About **{calls}** AI requests, roughly **{max(1, round(mins))} minute(s)**. "
                           "Anything already finished is reused, so this is an upper estimate.")
                if calls > 500:
                    st.warning("This is a large run. Consider a Quick check first.", icon=":material/warning:")
            else:
                st.caption("No AI requests needed.")

    if st.button("Start the test", type="primary", icon=":material/play_arrow:", disabled=not ready):
        if not mock and has_llm and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            st.error("There is no API key. Add one in the sidebar, or switch on Practice mode.", icon=":material/key_off:")
        else:
            bar, status = st.progress(0.0), st.empty()

            def on_progress(done, total, label):
                bar.progress(done / total if total else 1.0)
                status.caption(f"Step {done} of {total}: {label}")
            try:
                r = runner.execute(sel_arms, sel_probes, n_runs, n_case, n_pass, verifier, mock, progress=on_progress,
                                   judge_models=judges or None, verifier_model=vmodel, case_set=case_set)
                bar.progress(1.0)
                status.empty()
                st.success(f"Finished. Open the Summary tab to see the results ({r['new']} new result(s) computed).", icon=":material/check_circle:")
                st.toast("Test finished. See the Summary tab.", icon=":material/check_circle:")
                if r["errors"]:
                    st.warning(f"{r['errors']} item(s) failed and were not scored. Start the test again to retry them; "
                               "details are on the Summary tab.", icon=":material/warning:")
            except Exception as e:
                st.error(f"The test stopped: {e}", icon=":material/error:")
                if "AuthenticationError" in str(e):
                    st.info("The AI service rejected the API key before anything was scored, so nothing was saved. "
                            "Open 'Connection details' in the sidebar, test the connection, then start again. Finished work is kept.",
                            icon=":material/key:")

# ============================================================ SUMMARY
with tab_sum:
    if not has_results(mock):
        st.info("No results yet. It takes three steps:", icon=":material/info:")
        a, b, c = st.columns(3)
        for col, icon, t, d in [(a, ":material/tune:", "1. Choose", "Open **Run a test** and pick a Quick check."),
                                (b, ":material/play_arrow:", "2. Run", "Press **Start the test**. Practice mode is free and instant."),
                                (c, ":material/dashboard:", "3. Read", "Come back here for a plain-English verdict.")]:
            with col.container(border=True):
                st.markdown(f"#### {icon} {t}")
                st.write(d)
    else:
        f = runs_file(mock)
        path, mtime = str(f), f.stat().st_mtime
        rows, cases = load_rows(path, mtime)
        set_ids = vm.sets_in(rows)
        cset = st.segmented_control("Case set", set_ids, default=set_ids[0], required=True, format_func=vm.set_name, key="sum_set",
                                    help="Results are never pooled across case sets.") if len(set_ids) > 1 else set_ids[0]
        rows = vm.filter_set(rows, cset)
        md, tables = get_report(path, mtime, mock, cset)

        probe_ids = sorted({r["probe"] for r in rows}, key=lambda p: probes.PROBES.index(p) if p in probes.PROBES else 99)
        opt1, opt2 = st.columns(2)
        probe = "none" if "none" in probe_ids else probe_ids[0]
        if len(probe_ids) > 1:
            probe = opt1.selectbox("Condition", probe_ids, index=probe_ids.index(probe), format_func=lambda p: vm.PROBE_NAMES.get(p, p),
                                   help="Normal = the standard test. Others are trap tests.")
        level = "final"
        if any(r["level"] > 0 for r in rows):
            level = opt2.segmented_control("Which AI answer to score", ["final", "first"], default="final", required=True,
                                           format_func=lambda v: "After double-checking" if v == "final" else "First answer only",
                                           help="Each AI answer can be reviewed by a second AI. Choose whether to score the reviewed answer or the first one.")

        methods, comps = get_summary(path, mtime, probe, level, cset)
        if not methods:
            st.info("No results for this condition yet.", icon=":material/info:")
        else:
            names = vm.unique_names(methods)
            n_cases = max(m["cases"] for m in methods)
            text = vm.headline(methods, names, comps, n_cases)

            with st.container(border=True):
                st.markdown("#### How the methods compare")
                st.markdown(text)
                if n_cases < 20:
                    st.badge(f"Early indication: only {n_cases} case(s) tested", icon=":material/hourglass_top:", color="orange")
                else:
                    st.badge(f"Based on {n_cases} test cases", icon=":material/verified:", color="green")
                if not mock:
                    st.caption("The policies are synthetic, so this describes how the methods behave on this test design, not on real portfolios.")

            n_err = sum(1 for _ in open(err_file(mock))) if err_file(mock).exists() else 0
            bad_parse = sum(1 for r in rows for c in r.get("calls", []) if not c["parse_ok"])
            if n_err:
                st.warning(f"{n_err} item(s) failed and are missing from these scores. Start the test again from the Run tab to retry them.",
                           icon=":material/warning:")
            if bad_parse:
                st.warning(f"{bad_parse} AI reply(ies) could not be read and were counted as 'no change found', which lowers that AI's score.",
                           icon=":material/warning:")

            st.markdown("#### Scoreboard")
            st.caption("Share of the real changes each method found, compared with the rules-only baseline.")
            rules_found = next((m["found"] for m in methods if m["key"] == ("A_rules", "-")), None)
            ncol = min(3, len(methods))
            for i in range(0, len(methods), ncol):
                cols = st.columns(ncol)
                for col, m in zip(cols, methods[i:i + ncol]):
                    c = comps.get(m["key"])
                    with col.container(border=True):
                        if rules_found is not None and m["key"] != ("A_rules", "-"):
                            delta, dcolor = f"{(m['found'] - rules_found) * 100:+.0f} points vs rules only", "normal"
                        elif rules_found is not None:
                            delta, dcolor = "baseline", "off"
                        else:
                            delta, dcolor = None, "normal"
                        st.metric(names[m["key"]], vm.pct(m["found"]), delta, delta_color=dcolor,
                                  help="Share of the real changes this method found.")
                        label, color = vm.VERDICT_TEXT[c["verdict"]] if c else ("The baseline", "blue")
                        st.badge(label, color=color)
                        st.caption(f"Flags that were correct: **{vm.pct(m['correct'])}**  \n"
                                   f"Harmless edits wrongly flagged: **{vm.pct(m['cosmetic'])}**  \n"
                                   f"Same answer every attempt: **{vm.pct(m['consistency'])}**" if m["consistency"] is not None else
                                   f"Flags that were correct: **{vm.pct(m['correct'])}**  \n"
                                   f"Harmless edits wrongly flagged: **{vm.pct(m['cosmetic'])}**")

            chart = pd.DataFrame({"Real changes found": [100 * m["found"] for m in methods],
                                  "Flags that were correct": [100 * m["correct"] for m in methods]},
                                 index=[names[m["key"]] for m in methods])
            st.bar_chart(chart, horizontal=True, y_label="Percent", x_label="")

            st.markdown("#### Where does each method struggle?")
            st.caption("Real changes found, split by how hard they are to spot. Methods often differ most on the 'Hard' changes, "
                       "but each column can favour a different method.")
            tier_df = pd.DataFrame(
                [{"Method": names[m["key"]], **{vm.TIER_NAMES[t]: (None if v is None else 100 * v) for t, v in m["tiers"].items()}} for m in methods])
            st.dataframe(tier_df, hide_index=True, width="stretch",
                         column_config={vm.TIER_NAMES[t]: pct_col(vm.TIER_NAMES[t]) for t in vm.TIER_NAMES})

            dc = vm.double_check_effect(rows, probe)
            if dc:
                st.markdown("#### Does having a second AI double-check help?")
                dcdf = pd.DataFrame([{"Method": names.get(d["key"], vm.pretty_arm(d["key"][0])),
                                      "First answer": 100 * d["first"]["f1"], "After double-checking": 100 * d["final"]["f1"],
                                      "Change (points)": round(100 * (d["final"]["f1"] - d["first"]["f1"]))} for d in dc])
                st.dataframe(dcdf, hide_index=True, width="stretch", column_config={
                    "First answer": pct_col("First answer (overall score)"), "After double-checking": pct_col("After double-checking (overall score)")})
                st.caption("Overall score combines how many real changes were found with how many flags were correct. "
                           "A negative change means the extra check made the answer worse.")

            trap = dict(parse_md_tables(md)).get("4. Bias probes: change vs probe=none (same arm / verifier / passes)")
            if trap is not None and len(trap):
                st.markdown("#### Can the AI be misled?")
                st.caption("How often a misleading addition changed the AI's answer, compared with how much its answers vary anyway between attempts.")
                t = trap.sort_values("passes").groupby(["arm", "verifier", "probe"], as_index=False).last()
                fr_s, bf_s = pd.to_numeric(t["flip rate"], errors="coerce"), pd.to_numeric(t["baseline flip"], errors="coerce")
                tdf = pd.DataFrame({"Method": [vm.pretty_arm(a) for a in t["arm"]],
                                    "Trap": [vm.PROBE_NAMES.get(p, p) for p in t["probe"]],
                                    "Answer changed": 100 * fr_s, "Normal variation": 100 * bf_s,
                                    "Misled?": ["Can't tell (needs 2+ attempts)" if bf != bf else "Yes, likely" if fr > bf + 0.05 else "No"
                                                for fr, bf in zip(fr_s, bf_s)]})
                st.dataframe(tdf, hide_index=True, width="stretch", column_config={
                    "Answer changed": pct_col("Answer changed by the trap"), "Normal variation": pct_col("Changes anyway between attempts")})

            st.download_button("Download a one-page summary", vm.summary_markdown(methods, names, comps, n_cases, text),
                               file_name="benchmark_summary.md", icon=":material/download:",
                               help="Review and validate before sharing outside the team.")

            with st.expander("For analysts: full statistics", icon=":material/query_stats:"):
                st.caption("Precision, recall, F1, confidence intervals, consistency and verification effects exactly as computed.")
                for title, df in tables:
                    with st.expander(title):
                        st.dataframe(df, hide_index=True, width="stretch")
                st.download_button("Download full report (markdown)", md, file_name="report.md", icon=":material/download:")

# ============================================================ REVIEW TABLE
@st.cache_resource(show_spinner=False)
def get_review(path, mtime, probe, level, cset):
    rows, cases = load_rows(path, mtime)
    rows = vm.filter_set(rows, cset)
    methods = vm.summarize(rows, probe, level)
    names = vm.unique_names(methods)
    return pd.DataFrame(vm.review_table(rows, cases, probe, level, names)), [names[m["key"]] for m in methods], cases


with tab_review:
    if not has_results(mock):
        st.info("No results yet. Run a test first, then review every case here.", icon=":material/info:")
    else:
        f = runs_file(mock)
        path, mtime = str(f), f.stat().st_mtime
        rows, _ = load_rows(path, mtime)
        st.caption("Every item in every case study, for every method: where it is in the policy, what changed, "
                   "what the method did, and why that was right or wrong. Select a row to see the actual policy text.")
        rset_ids = vm.sets_in(rows)
        rset = st.segmented_control("Case set", rset_ids, default=rset_ids[0], required=True, format_func=vm.set_name, key="rv_set") \
            if len(rset_ids) > 1 else rset_ids[0]
        rows = vm.filter_set(rows, rset)
        probe_ids = sorted({r["probe"] for r in rows}, key=lambda p: probes.PROBES.index(p) if p in probes.PROBES else 99)
        k1, k2 = st.columns(2)
        rprobe = "none" if "none" in probe_ids else probe_ids[0]
        if len(probe_ids) > 1:
            rprobe = k1.selectbox("Condition", probe_ids, index=probe_ids.index(rprobe), format_func=lambda p: vm.PROBE_NAMES.get(p, p), key="rv_probe")
        rlevel = "final"
        if any(r["level"] > 0 for r in rows):
            rlevel = k2.segmented_control("Which AI answer", ["final", "first"], default="final", required=True, key="rv_level",
                                          format_func=lambda v: "After double-checking" if v == "final" else "First answer only")
        full, method_names, cases_all = get_review(path, mtime, rprobe, rlevel, rset)
        if full.empty:
            st.info("No results for this condition yet.", icon=":material/info:")
        else:
            f1c, f2c = st.columns([3, 2])
            pick_methods = f1c.pills("Methods", method_names, selection_mode="multi", default=method_names, key="rv_methods")
            case_labels = sorted(full["Case"].unique(), key=lambda c: int(c.split()[1]))
            pick_cases = f2c.multiselect("Case studies", case_labels, default=case_labels, key="rv_cases")
            g1, g2 = st.columns([3, 2])
            diffs = sorted(full["Difficulty"].unique())
            pick_diff = g1.pills("Type of item", diffs, selection_mode="multi", default=diffs, key="rv_diff",
                                 help="easy / medium / hard = real changes; 'harmless edit' = rewording or formatting that should be ignored.")
            show = g2.segmented_control("Show", ["Mistakes only", "Everything", "Correct only"], default="Mistakes only", required=True, key="rv_show")

            edge_all = sorted(full["Edge case"].unique())
            pick_edge = st.multiselect("Edge case", edge_all, default=edge_all, key="rv_edge",
                                       help="The specific kind of difficulty an item was built to test (for example 'Meaning flips: and or' or 'Trap: ...').") \
                if len(edge_all) > 2 else edge_all
            full = full[full["Edge case"].isin(pick_edge or [])]
            df = full[full["Method"].isin(pick_methods or []) & full["Case"].isin(pick_cases or []) & full["Difficulty"].isin(pick_diff or [])]
            if show == "Mistakes only":
                df = df[~df["_right"]]
            elif show == "Correct only":
                df = df[df["_right"]]
            scope = full[full["Method"].isin(pick_methods or []) & full["Case"].isin(pick_cases or []) & full["Difficulty"].isin(pick_diff or [])]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Items reviewed", len(scope), border=True)
            m2.metric("Correct", int(scope["_right"].sum()), border=True)
            m3.metric("Mistakes", int((~scope["_right"]).sum()), border=True)
            m4.metric("Cases covered", scope["Case"].nunique(), border=True)

            with st.expander("Summary of mistakes", icon=":material/bar_chart:"):
                if len(scope):
                    kinds = scope.assign(**{k: (scope["_outcome"] == k) for k in ["Missed", "Wrongly flagged", "Inconsistent"]})
                    by_m = kinds.groupby("Method").agg(Correct=("_right", "sum"), Missed=("Missed", "sum"),
                                                       **{"Wrongly flagged": ("Wrongly flagged", "sum"), "Inconsistent": ("Inconsistent", "sum")}).reset_index()
                    st.markdown("**By method**")
                    st.dataframe(by_m, hide_index=True, width="stretch")
                    bad = scope[~scope["_right"]]
                    if len(bad):
                        st.markdown("**Where methods go wrong most often** (how many selected methods got this item wrong)")
                        hot = bad.groupby(["Case", "Where", "Difficulty"]).agg(Methods_wrong=("Method", "nunique"),
                                                                              Which=("Method", lambda s: ", ".join(sorted(set(s))))).reset_index() \
                                 .sort_values("Methods_wrong", ascending=False).head(10)
                        st.dataframe(hot.rename(columns={"Methods_wrong": "Methods wrong", "Which": "Which methods"}), hide_index=True, width="stretch")

            if df.empty:
                st.success("Nothing to show with these filters. " + ("No mistakes found." if show == "Mistakes only" else ""), icon=":material/check_circle:")
            else:
                shown = ["Case", "Where", "Difficulty", "Edge case", "Original wording", "Renewal wording", "Method", "Result", "Why", "What the method said"]
                view = df.reset_index(drop=True)
                st.caption(f"{len(view)} row(s). {vm.OK_MARK} correct   {vm.MISS_MARK} missed a real change   "
                           f"{vm.FALSE_MARK} flagged something that is not a real change   {vm.MIX_MARK} different between attempts")
                ev = st.dataframe(view[shown].style.map(mark_color, subset=["Result"]), hide_index=True, width="stretch", height=480,
                                  on_select="rerun", selection_mode="single-row", key="rv_table")
                st.download_button("Download these rows (CSV)", view[shown].to_csv(index=False), file_name="review_table.csv", icon=":material/download:")
                sel = ev.selection.rows if ev and ev.selection else []
                if sel:
                    row = view.iloc[sel[0]]
                    head, orig, renew = vm.excerpt(cases_all[row["_case"]], row["_loc"])
                    with st.container(border=True):
                        st.markdown(f"#### {row['Case']} · {head}")
                        st.markdown(f"**{row['Method']}**: {row['Result']}. {row['Why']}")
                        if row["What the method said"]:
                            st.caption(f"The method said: {row['What the method said']}")
                        st.caption(f"Changed phrase: **{row['Original wording']}** → **{row['Renewal wording']}**")
                        o, r_ = st.columns(2)
                        o.text_area("Original policy text", orig, height=170, key=f"o_{sel[0]}_{row['_case']}")
                        r_.text_area("Renewal policy text", renew, height=170, key=f"r_{sel[0]}_{row['_case']}")
                else:
                    st.caption("Tip: click a row to see the exact policy text it refers to.")

# ============================================================ CASE EXPLORER
with tab_cases:
    files = vm.case_files()
    if not files:
        st.info("No test cases yet.", icon=":material/info:")
    else:
        ids = [os.path.basename(f)[:-5] for f in files]
        rows, cases = (load_rows(str(runs_file(mock)), runs_file(mock).stat().st_mtime) if has_results(mock) else ([], {}))
        sel1, sel2, sel3 = st.columns(3)
        case_id = sel1.selectbox("Test case", ids, format_func=lambda i: f"Case {i.split('_')[1]}")
        case = json.load(open(files[ids.index(case_id)]))
        have = sorted({r["probe"] for r in rows if r["case"] == case_id}, key=lambda p: probes.PROBES.index(p) if p in probes.PROBES else 99)

        n_real = sum(e["expected"] for e in case["key"])
        st.caption(f"This case contains **{n_real} real changes** and **{len(case['key']) - n_real} harmless edits** "
                   "(rewording or formatting that should be ignored). That list is the answer key.")

        if not have:
            st.info("No results for this case yet. Run a test first to compare the methods here.", icon=":material/info:")
        else:
            pr = sel2.selectbox("Condition", have, index=have.index("none") if "none" in have else 0,
                                format_func=lambda p: vm.PROBE_NAMES.get(p, p))
            runs_here = sorted({r["run"] for r in rows if r["case"] == case_id and r["probe"] == pr})
            run_id = sel3.selectbox("Attempt (for AI methods)", runs_here, format_func=lambda i: f"Attempt {i + 1}",
                                    disabled=len(runs_here) < 2, help="AI answers can differ from attempt to attempt.")
            combos = sorted({(r["arm"], r["verifier"]) for r in rows if r["case"] == case_id and r["probe"] == pr})
            nm = vm.unique_names([dict(key=k, arm=k[0]) for k in combos])
            chosen = st.pills("Methods to compare", combos, selection_mode="multi", default=combos, format_func=lambda k: nm[k])
            t1, t2, t3 = st.columns(3)
            only_issues = t1.toggle("Only show mistakes", value=True, help="Hide items every selected method got right.")
            every = t2.toggle("Show each double-check step", value=False)
            detail = t3.toggle("Show what each method said", value=False)

            if chosen:
                table, mcols = vm.side_by_side(rows, case, pr, [(k[0], k[1], nm[k]) for k in chosen], run_id, every, detail, only_issues)
                df = pd.DataFrame(table)
                if only_issues and len(df) == 3:
                    st.success("None of the selected methods made a mistake on this case.", icon=":material/check_circle:")
                st.dataframe(df.style.map(mark_color, subset=mcols), hide_index=True, width="stretch",
                             height=min(900, 38 * (len(df) + 1)))
                st.caption(f"{vm.OK_MARK} correct   {vm.MISS_MARK} missed a real change   {vm.FALSE_MARK} flagged something that is not a real change. "
                           "'Rules only' and other rule-based methods run once; AI methods show the selected attempt.")
                st.download_button("Download this table (CSV)", df.to_csv(index=False), file_name=f"{case_id}_comparison.csv",
                                   icon=":material/download:")
            else:
                st.info("Pick at least one method.", icon=":material/info:")

            with st.expander("Step by step: how one method reached its answer", icon=":material/timeline:"):
                lab = sorted({r["arm"] for r in rows if r["case"] == case_id and r["probe"] == pr})
                arm_label = st.selectbox("Method", lab, format_func=vm.pretty_arm)
                cand = [r for r in rows if r["case"] == case_id and r["arm"] == arm_label and r["probe"] == pr]
                rid = st.selectbox("Attempt", sorted({r["run"] for r in cand}), format_func=lambda i: f"Attempt {i + 1}", key="step_run")
                chain = sorted([r for r in cand if r["run"] == rid], key=lambda r: r["level"])
                base_name = arm_label.split(" @ ")[0]
                if base_name in ("B_llm", "C_llm_plus_rules"):
                    ta, tb, swap = probes.apply(pr, case["text_a"], case["text_b"], seed=case["seed"])
                    s_, u_ = prompts.judge(ta, tb, swap, base_name == "C_llm_plus_rules")
                    st.caption("The exact instructions the AI received:")
                    st.code(s_, language="text")
                prev = None
                for r in chain:
                    s = r["s"]
                    title = ("First answer" if r["level"] == 0 else f"After AI double-check {r['level']}") if len(chain) > 1 else "Result"
                    with st.container(border=True):
                        st.markdown(f"**{title}**: found {s['tp']} real change(s), missed {s['fn']}, wrongly flagged {s['fp']}.")
                        if prev is not None:
                            gained, lost = s["TP"] - prev["s"]["TP"], prev["s"]["TP"] - s["TP"]
                            fa, fr = s["FP"] - prev["s"]["FP"], prev["s"]["FP"] - s["FP"]
                            msg = ([f"Now finds: {', '.join(sorted(gained))}"] if gained else []) + \
                                  ([f"Dropped real change(s): {', '.join(sorted(lost))}"] if lost else []) + \
                                  ([f"Removed wrong flag(s): {', '.join(sorted(fr))}"] if fr else []) + \
                                  ([f"Added wrong flag(s): {', '.join(sorted(fa))}"] if fa else [])
                            st.caption(" · ".join(msg) if msg else "No change from the previous step.")
                        ex = pd.DataFrame(score.explain(r["pred"], case)).rename(columns={
                            "status": "Result", "location": "Item", "tier": "Difficulty", "truth": "Answer key", "model_said": "Method said"})
                        if not ex.empty:
                            ex["Result"] = ex["Result"].map({"HIT": f"{vm.OK_MARK} Found", "MISSED": f"{vm.MISS_MARK} Missed",
                                                             "FALSE ALARM": f"{vm.FALSE_MARK} Wrongly flagged",
                                                             "COSMETIC FALSE ALARM": f"{vm.FALSE_MARK} Wrongly flagged (harmless edit)"})
                            st.dataframe(ex.style.map(mark_color, subset=["Result"]), hide_index=True, width="stretch")
                        for c in r.get("calls", []):
                            with st.expander(f"Raw AI reply · {vm.short_model(c['model'])} · {c['tin']} in / {c['tout']} out tokens · {c['latency']}s"
                                             + ("" if c["parse_ok"] else " · COULD NOT BE READ")):
                                st.code(c["text"], language="json")
                    prev = r

        with st.expander("The answer key and the two documents", icon=":material/description:"):
            key_df = pd.DataFrame(case["key"]).rename(columns={"location": "Item", "tier": "Difficulty", "expected": "Should be flagged?",
                                                              "old": "Before", "new": "After"})[["Item", "Should be flagged?", "Difficulty", "Before", "After"]]
            st.dataframe(key_df, hide_index=True, width="stretch")
            d1, d2 = st.columns(2)
            d1.text_area("Original policy", case["text_a"], height=380)
            d2.text_area("Renewal policy", case["text_b"], height=380)

# ============================================================ CUSTOMER QUERY ROUTING
with tab_route:
    from src import routing_ui
    routing_ui.render(mock)

# ============================================================ HELP
with tab_help:
    st.markdown("""
### In one sentence
We measure how AI models compare with a fixed set of if-then rules at spotting the changes that matter between two versions of a car insurance policy. There is no assumed winner: the aim is to see where each approach is strong or weak.

### Two tests in one app
The **Summary, Run a test, Review table and Case explorer** tabs compare methods at finding changes between two policy versions (you can choose the original cases, the USAA cases, or the complex edge cases). The **Customer queries** tab compares methods at routing a customer message, or a whole multi-turn conversation, to the right department. Both use the same neutral approach and the same models.

### How the policy test works
1. **We build tests where we know the answer.** A script creates a policy, then a renewal copy with deliberate edits. Some are **real changes** (a limit, a deadline, a removed exclusion). Others are **harmless** (reworded text, different date or currency formatting). Because the script made every edit, it knows the exact answer. No AI or person marks the answers.
2. **Different methods try to find the real changes.** *Rules only* follows fixed rules. *AI only* asks an AI model. *AI guided by rules* gives the AI the rules too. *Rules + AI together* lets rules handle the obvious fields and the AI judge reworded clauses.
3. **A second AI can double-check** the first answer, so we can see whether extra checking helps or hurts.
4. **Every answer is scored against the answer key.**
5. **Trap tests** add misleading text (for example, a fake 'Compliance approved' note) to see whether the AI is swayed by something irrelevant.

### How to read the results
| Term | Plain meaning |
|---|---|
| **Real changes found** | Of the changes that truly matter, how many did the method catch? |
| **Flags that were correct** | Of everything it flagged, how much was a real change? |
| **Harmless edits wrongly flagged** | How often it raised an alarm over rewording or formatting. |
| **Hard changes** | The meaning changed but there is no obvious word or number to spot. A good place to see where methods differ. |
| **No reliable difference** | The gap between two methods could be down to chance. Run more cases to settle it. |
| **Same answer every attempt** | Whether the method gives consistent answers when asked again. |

### Good to know
- The policies are **synthetic**. Results show how the methods behave on this test design, not how they would perform on real portfolios.
- **Practice mode** uses fake AI answers and is only for learning the app.
- Results are saved with the exact AI model used, so you can switch models and compare them safely.
- AI-assisted analysis: **review and validate results before sharing them outside the team.**
""")
