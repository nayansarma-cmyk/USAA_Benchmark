"""Streamlit section for the customer-query routing benchmark (rendered inside a tab of app.py)."""
import os
import pandas as pd
import streamlit as st

from . import config, routing as R, viewmodel as vm

GOOD, WARN, BAD = "#1b7f3b", "#b9770e", "#c0392b"


def _color(v):
    v = str(v)
    return (f"color: {GOOD}; font-weight: 600" if v.startswith("✓") else f"color: {BAD}; font-weight: 600" if v.startswith("✗")
            else f"color: {WARN}; font-weight: 600" if v.startswith("~") else "")


def _pct_col(label, help=None):
    return st.column_config.ProgressColumn(label, min_value=0, max_value=100, format="%.0f%%", help=help)


@st.cache_resource(show_spinner=False)
def _load(path, mtime):
    return R.load_scored(path)


def _headline(ms, comps, unit):
    rules = next((m for m in ms if m["label"] == "Q_rules"), None)
    n = max(m["queries"] for m in ms)
    s = f"On **{n} {unit}{'s' if n != 1 else ''}**:"
    if not rules:
        return s + "".join(f"\n- **{m['name']}** routed **{vm.pct(m['accuracy'])}** correctly." for m in ms) + "\n\nNo keyword-rules run is included, so there is nothing to compare against."
    s += f"\n- **{rules['name']}** (the baseline) routed **{vm.pct(rules['accuracy'])}** correctly."
    for m in ms:
        if m["label"] == "Q_rules":
            continue
        v = comps.get(m["label"], {}).get("verdict", "n/a")
        s += (f"\n- **{m['name']}** routed **{vm.pct(m['accuracy'])}** correctly. Overall it " + vm.VERDICT_SENTENCE[v].replace("rules", "keyword rules") + ".")
    return s


def _transcript(history, text=None):
    for h in history:
        with st.chat_message("user" if h["who"] == "customer" else "assistant"):
            st.write(h["text"])
    if text is not None:
        with st.chat_message("user"):
            st.write(text)


def render(mock):
    st.caption("Which way of routing a customer message to the right department works best: fixed keyword rules, an AI model, "
               "or a mix? Same neutral approach as the policy comparison: no assumed winner.")
    st.info("The messages here are synthetic, and their correct departments come from the generator, not from a person or an AI. "
            "Real customer messages can contain personal or regulated data: involve your Data Privacy Officer before using any.",
            icon=":material/shield:")
    avail = {k: bool(R.load_dataset(k)) for k in R.DATASETS}
    ds = st.segmented_control("What to route", [k for k in R.DATASETS if avail[k]] or ["single"], default="convo" if avail["convo"] else "single",
                              required=True, key="rt_ds", format_func=lambda k: R.DATASETS[k],
                              help="Single messages are standalone. Conversations have several turns, so context, follow-ups and corrections matter.")
    unit = "customer turn" if ds == "convo" else "customer message"
    tnames = R.type_names()
    t_run, t_res, t_rev, t_q = st.tabs(["Run", "Results", "Review table", "Browse"])
    path = R.runs_path(mock)
    has_any = path.exists() and path.stat().st_size > 0
    all_rows = _load(str(path), path.stat().st_mtime)[0] if has_any else []
    rows_ds = R.filter_dataset(all_rows, ds)
    has = bool(rows_ds)
    data = R.load_dataset(ds)

    # ---------------------------------------------------------------- run
    with t_run:
        if not data:
            st.error("No data found. Run `python -m src.routing --gen` and `python -m src.convos` first.", icon=":material/error:")
        presets = {"Quick check": dict(n=min(40 if ds == "convo" else 30, len(data)), runs=1,
                                       blurb=f"{min(40 if ds == 'convo' else 30, len(data))} {unit}s, one attempt each. A minute or so."),
                   "Standard": dict(n=len(data), runs=3, blurb=f"All {len(data)} {unit}s, 3 attempts each, to measure consistency.")}
        pick = st.segmented_control("Test size", list(presets), default="Quick check", required=True, key="rt_preset", label_visibility="collapsed")
        n_q, n_runs = presets[pick]["n"], presets[pick]["runs"]
        st.caption(presets[pick]["blurb"])
        options = R.DATASET_ARMS[ds]
        arms_sel = st.pills("Routing methods", options, selection_mode="multi", default=options, key=f"rt_arms_{ds}",
                            format_func=lambda a: R.ARM_NAMES[a]) or []
        with st.expander("What do these mean?", icon=":material/info:"):
            for a in options:
                st.markdown(f"**{R.ARM_NAMES[a]}**: {R.ARM_HELP[a]}")
        has_llm = any(R.ARM_IS_LLM[a] for a in arms_sel)
        judges = []
        if has_llm:
            judges = st.pills("Which AI models?", vm.MODEL_PRESETS, selection_mode="multi", default=["claude-sonnet-5-5"], key="rt_models",
                              format_func=vm.short_model) or []
            if not judges:
                st.warning("Pick at least one AI model.", icon=":material/warning:")
        ready = bool(arms_sel and data and (judges or not has_llm))
        if ready:
            calls = R.plan([a for a in arms_sel if R.ARM_IS_LLM[a]], n_q, n_runs, len(judges)) if has_llm else 0
            with st.container(border=True):
                st.markdown(f"**{n_q}** {unit}s · **{len(arms_sel)}** method(s)" + (f" · **{len(judges)}** AI model(s)" if has_llm else ""))
                st.caption("Practice mode: no AI requests." if mock else
                           (f"Up to **{calls}** AI requests (the hybrid uses the AI only when the rules are unsure). "
                            "Anything already finished is reused." if calls else "No AI requests needed."))
        if st.button("Start the routing test", type="primary", icon=":material/play_arrow:", disabled=not ready, key="rt_go"):
            if not mock and has_llm and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
                st.error("There is no API key. Add one in the sidebar, or switch on Practice mode.", icon=":material/key_off:")
            else:
                bar, status = st.progress(0.0), st.empty()

                def on_progress(done, total, label):
                    bar.progress(done / total if total else 1.0)
                    status.caption(f"Step {done} of {total}: {label}")
                try:
                    r = R.execute(arms_sel, n_q, n_runs, judges or None, mock, progress=on_progress, dataset=ds)
                    bar.progress(1.0); status.empty()
                    st.success(f"Finished ({r['new']} new decisions). Open Results.", icon=":material/check_circle:")
                    if r["errors"]:
                        st.warning(f"{r['errors']} decision(s) failed and were not scored. Start again to retry them.", icon=":material/warning:")
                except Exception as e:
                    st.error(f"The test stopped: {e}", icon=":material/error:")
        if has_any and st.button("Clear all saved routing results", icon=":material/delete:", key="rt_clear"):
            path.unlink()
            if R.errors_path(mock).exists():
                R.errors_path(mock).unlink()
            st.rerun()

    # ---------------------------------------------------------------- results
    with t_res:
        if not has:
            st.info(f"No results for {R.DATASETS[ds].lower()} yet. Run a test first.", icon=":material/info:")
        else:
            rows = rows_ds
            ms, comps = R.summarize(rows), R.compare_to_rules(rows)
            n = max(m["queries"] for m in ms)
            with st.container(border=True):
                st.markdown("#### How the methods compare")
                st.markdown(_headline(ms, comps, unit))
                st.badge(f"Early indication: only {n} {unit}s" if n < 100 else f"Based on {n} {unit}s", color="orange" if n < 100 else "green",
                         icon=":material/hourglass_top:" if n < 100 else ":material/verified:")
                st.caption("The messages and the rules were written by the same team, so rule scores may be higher here than on real traffic. "
                           "Treat the result as a comparison on this test set, not a forecast.")
            n_err = sum(1 for _ in open(R.errors_path(mock), encoding="utf-8")) if R.errors_path(mock).exists() else 0
            if n_err:
                st.warning(f"{n_err} decision(s) failed and are missing from these scores. Start the test again to retry them.", icon=":material/warning:")

            st.markdown("#### Scoreboard")
            rules_acc = next((m["accuracy"] for m in ms if m["label"] == "Q_rules"), None)
            ncol = min(3, len(ms))
            for i in range(0, len(ms), ncol):
                for col, m in zip(st.columns(ncol), ms[i:i + ncol]):
                    c = comps.get(m["label"])
                    with col.container(border=True):
                        if rules_acc is not None and m["label"] != "Q_rules":
                            delta, dc = f"{(m['accuracy'] - rules_acc) * 100:+.0f} points vs keyword rules", "normal"
                        else:
                            delta, dc = ("baseline", "off") if rules_acc is not None else (None, "normal")
                        st.metric(m["name"], vm.pct(m["accuracy"]), delta, delta_color=dc, help=f"Share of {unit}s sent to the correct department.")
                        lbl, color = vm.VERDICT_TEXT[c["verdict"]] if c else ("The baseline", "blue")
                        st.badge(lbl.replace("rules", "keyword rules"), color=color)
                        extra = ""
                        if m["ctx"] is not None:
                            extra += f"Turns that need the conversation: **{vm.pct(m['ctx'])}**  \n"
                        if m["conv_ok"] is not None:
                            extra += f"Whole conversation right: **{vm.pct(m['conv_ok'])}**  \n"
                        st.caption(extra + f"Urgent requests dropped into General inquiries: **{vm.pct(m['dropped'])}**  \n"
                                   f"No usable answer: **{vm.pct(m['invalid'])}**  \n"
                                   + (f"Same answer every attempt: **{vm.pct(m['consistency'])}**  \n" if m["consistency"] is not None else "")
                                   + f"Decided by AI: **{vm.pct(m['ai_share'])}** · avg {m['seconds']:.2f}s per {unit}")

            st.markdown(f"#### Accuracy by type of {unit}")
            st.caption("Methods often differ most where the meaning is not on the surface: no obvious keyword, two topics at once, "
                       "a correction that uses a misleading keyword, or an attempt to steer the router."
                       + (" In a conversation, short follow-ups only make sense with what came before." if ds == "convo" else ""))
            present = [t for t in tnames if any(t in m["tiers"] for m in ms)]
            tdf = pd.DataFrame([{"Method": m["name"], **{tnames[t]: (None if t not in m["tiers"] else 100 * m["tiers"][t]) for t in present}} for m in ms])
            st.dataframe(tdf, hide_index=True, width="stretch", column_config={tnames[t]: _pct_col(tnames[t]) for t in present})

            if ds == "convo":
                st.markdown("#### Does the conversation context matter?")
                st.caption("The same method with and without the conversation, on the turns that cannot be understood from the last message alone.")
                cdf = pd.DataFrame([{"Method": m["name"], "All turns": 100 * m["accuracy"],
                                     "Turns that need context": None if m["ctx"] is None else 100 * m["ctx"],
                                     "Whole conversation right": None if m["conv_ok"] is None else 100 * m["conv_ok"]} for m in ms])
                st.dataframe(cdf, hide_index=True, width="stretch", column_config={
                    "All turns": _pct_col("All turns"), "Turns that need context": _pct_col("Turns that need context"),
                    "Whole conversation right": _pct_col("Whole conversation right", help="Every customer turn in the conversation was routed correctly (complete conversations only).")})

            st.markdown("#### Accuracy by department")
            idf = pd.DataFrame([{"Method": m["name"], **{R.INTENT_NAMES[i]: 100 * v for i, v in R.per_intent(rows, m["label"]).items()}} for m in ms])
            st.dataframe(idf, hide_index=True, width="stretch", column_config={c: _pct_col(c) for c in idf.columns if c != "Method"})
            st.caption("Urgent departments are File a claim, Roadside assistance, Fraud and security, and Complaints. "
                       "Sending one of these to General inquiries counts as 'dropped'.")

            st.markdown("#### What gets mixed up?")
            pick_m = st.selectbox("Method", [m["label"] for m in ms], format_func=R.pretty, key="rt_conf")
            conf = R.confusions(rows, pick_m, 10)
            if conf:
                st.dataframe(pd.DataFrame([{"Should go to": R.INTENT_NAMES[g], "Was sent to": R.INTENT_NAMES[p], "Times": c} for (g, p), c in conf]),
                             hide_index=True, width="stretch")
            else:
                st.success("No mistakes for this method.", icon=":material/check_circle:")

            st.markdown("#### Speed and cost")
            st.dataframe(pd.DataFrame([{"Method": m["name"], f"Avg seconds per {unit}": round(m["seconds"], 3), f"Avg tokens per {unit}": round(m["tokens"]),
                                        "Decided by AI": 100 * m["ai_share"]} for m in ms]), hide_index=True, width="stretch",
                         column_config={"Decided by AI": _pct_col("Decided by AI")})
            st.caption("Rules are effectively instant and free. Tokens are what the AI used; check current pricing for your model to estimate cost. "
                       "Conversations cost more per turn because the AI reads the whole transcript.")

    # ---------------------------------------------------------------- review table
    with t_rev:
        if not has:
            st.info(f"No results for {R.DATASETS[ds].lower()} yet.", icon=":material/info:")
        else:
            full = pd.DataFrame([x for x in R.review_rows(rows_ds)])
            f1, f2 = st.columns([3, 2])
            methods = sorted(full["Method"].unique())
            pm = f1.pills("Methods", methods, selection_mode="multi", default=methods, key="rr_m") or []
            types = sorted(full["Type"].unique())
            pt = f2.multiselect(f"Type of {unit}", types, default=types, key="rr_t", format_func=lambda t: tnames.get(t, t))
            g1, g2 = st.columns([3, 2])
            depts = sorted(full["Correct department"].unique())
            pdp = g1.multiselect("Correct department", depts, default=depts, key="rr_d")
            show = g2.segmented_control("Show", ["Mistakes only", "Everything", "Correct only"], default="Mistakes only", required=True, key="rr_s")
            scope = full[full["Method"].isin(pm) & full["Type"].isin(pt) & full["Correct department"].isin(pdp)]
            view = scope[~scope["_right"]] if show == "Mistakes only" else scope[scope["_right"]] if show == "Correct only" else scope
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Decisions reviewed", len(scope), border=True)
            m2.metric("Correct", int(scope["_right"].sum()), border=True)
            m3.metric("Mistakes", int((~scope["_right"]).sum()), border=True)
            m4.metric("Urgent requests dropped", int(scope["Urgent dropped"].sum()), border=True)
            if view.empty:
                st.success("Nothing to show with these filters.", icon=":material/check_circle:")
            else:
                shown = (["Conversation", "Said so far"] if ds == "convo" else []) + \
                        ["Query", "Correct department", "Type", "Method", "Routed to", "Result", "Why", "Decided by"]
                view = view.assign(Type=view["Type"].map(lambda t: tnames.get(t, t)))
                ev = st.dataframe(view[shown].style.map(_color, subset=["Result"]), hide_index=True, width="stretch", height=480,
                                  on_select="rerun", selection_mode="single-row", key=f"rr_table_{ds}")
                st.download_button("Download these rows (CSV)", view[shown].to_csv(index=False), file_name=f"routing_review_{ds}.csv", icon=":material/download:")
                sel = ev.selection.rows if ev and ev.selection else []
                if sel and ds == "convo":
                    row = view.iloc[sel[0]]
                    with st.container(border=True):
                        st.markdown(f"#### {row['Conversation']} · {row['Method']}: {row['Result']}")
                        st.caption(row["Why"])
                        hist = [dict(who="customer" if p.startswith("Customer:") else "agent", text=p.split(": ", 1)[1]) for p in row["Said so far"].split(" | ")] if row["Said so far"] != "—" else []
                        _transcript(hist, row["Query"])
                        st.caption(f"Correct department: **{row['Correct department']}** · routed to: **{row['Routed to']}**")
                elif ds == "convo":
                    st.caption("Tip: click a row to see the conversation.")
            st.caption("✓ correct   ✗ sent to the wrong department   ~ different between attempts")

    # ---------------------------------------------------------------- browse
    with t_q:
        if not data:
            st.info("Nothing generated yet.", icon=":material/info:")
        elif ds == "convo":
            import json
            from .convos import CONVOS
            convs = json.load(open(CONVOS, encoding="utf-8"))
            scen = sorted({c["scenario"] for c in convs})
            c1, c2 = st.columns(2)
            sc = c1.selectbox("Scenario", scen, format_func=lambda s: s.replace("_", " ").capitalize())
            pool = [c for c in convs if c["scenario"] == sc]
            cid = c2.selectbox("Conversation", [c["id"] for c in pool])
            conv = next(c for c in pool if c["id"] == cid)
            for t in conv["turns"]:
                with st.chat_message("user" if t["who"] == "customer" else "assistant"):
                    st.write(t["text"])
                    if t["who"] == "customer":
                        st.caption(f"Correct department: **{R.INTENT_NAMES[t['gold']]}** · tests: {tnames[t['tag']]}")
            df = pd.DataFrame(data)
            st.markdown("**The whole set**")
            a, b = st.columns(2)
            a.dataframe(df.groupby("tier").size().rename("Turns").rename(index=lambda t: tnames[t]).reset_index().rename(columns={"tier": "Type of turn"}),
                        hide_index=True, width="stretch")
            b.dataframe(df.groupby("turn").size().rename("Conversations reaching this turn").reset_index().rename(columns={"turn": "Customer turn number"}),
                        hide_index=True, width="stretch")
            st.caption(f"{len(convs)} conversations, {len(data)} customer turns, up to {df['turn'].max()} customer turns each. "
                       f"{int(df['needs_context'].sum())} turns cannot be understood without the conversation.")
        else:
            df = pd.DataFrame(data)
            c1, c2 = st.columns(2)
            c1.dataframe(df.groupby("gold").size().rename("Messages").rename(index=R.INTENT_NAMES).reset_index().rename(columns={"gold": "Department"}),
                         hide_index=True, width="stretch")
            c2.dataframe(df.groupby("tier").size().rename("Messages").rename(index=lambda t: tnames[t]).reset_index().rename(columns={"tier": "Type"}),
                         hide_index=True, width="stretch")
            st.dataframe(df.assign(gold=df["gold"].map(R.INTENT_NAMES), tier=df["tier"].map(tnames))
                         .rename(columns={"id": "ID", "text": "Message", "gold": "Correct department", "tier": "Type"})[["ID", "Message", "Correct department", "Type"]],
                         hide_index=True, width="stretch", height=420)
            st.caption("Messages are generated from hand-written templates with random details. The correct department is the one each template was written for.")
