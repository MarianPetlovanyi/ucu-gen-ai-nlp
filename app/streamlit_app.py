"""NDA Playbook Reviewer: demo UI. Calls only nda_review.pipeline.

Run: uv run streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import html
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from nda_review.data import list_playbooks, load_hypotheses, load_playbook, load_split
from nda_review.pipeline import ReviewResult, review_file, review_text

st.set_page_config(page_title="NDA Playbook Reviewer", layout="wide")

STATUS_COLOR = {
    "VIOLATION": "#e5534b",
    "MISSING": "#d29922",
    "REVIEW": "#539bf5",
    "OK": "#57ab5a",
    "INFO": "#768390",
}
STATUS_ICON = {"VIOLATION": "🔴", "MISSING": "🟠", "REVIEW": "🔵", "OK": "🟢", "INFO": "⚪"}
COMPONENTS = [
    ("C1 Ingestion", "tool", "PDF/HTML/TXT → text (PyMuPDF, HTML parser, reflow)"),
    ("C2 Segmentation", "tool", "text → numbered spans (rules)"),
    ("C3 Retrieval", "local model", "rule → top spans (bge-small exemplar kNN)"),
    ("C4 NLI + evidence", "LLM gpt-oss-120b", "contract × 17 hypotheses → label + span ids"),
    ("C5 Playbook", "deterministic", "labels × playbook → status, risk, recommendation"),
    ("C6 Redlines", "LLM gpt-oss-120b", "issues → replacement / inserted clauses"),
    ("C7 Memo", "LLM gpt-oss-120b", "report → negotiation memo with citations"),
]


@st.cache_data(show_spinner=False)
def example_docs() -> dict[str, str]:
    docs = load_split("dev")
    return {f"{d.doc_id} · {d.file_name[:60]}": str(d.raw_path) for d in docs[:40]}


@st.cache_data(show_spinner=False, max_entries=20)
def run_file(path: str, playbook: str, redlines: bool, memo: bool) -> dict:
    return review_file(path, playbook, with_redlines=redlines, with_memo=memo).model_dump()


@st.cache_data(show_spinner=False, max_entries=20)
def run_text(text: str, playbook: str, redlines: bool, memo: bool) -> dict:
    return review_text(text, playbook, with_redlines=redlines, with_memo=memo).model_dump()


def highlight(res: ReviewResult, only_rule: str | None) -> str:
    color_of: dict[int, str] = {}
    for f in reversed(res.report.findings):  # most severe wins (findings are sorted)
        if only_rule and f.rule_id != only_rule:
            continue
        for i in f.evidence:
            color_of[i] = STATUS_COLOR[f.status]
    text, out, pos = res.contract.text, [], 0
    for s in res.contract.spans:
        out.append(html.escape(text[pos : s.start]))
        seg = html.escape(text[s.start : s.end])
        if s.id in color_of:
            seg = (
                f'<mark style="background:{color_of[s.id]}33;border-bottom:2px solid '
                f'{color_of[s.id]}" title="span {s.id}">{seg}</mark>'
            )
        out.append(f'<span title="span {s.id}">{seg}</span>')
        pos = s.end
    out.append(html.escape(text[pos:]))
    body = "".join(out).replace("\n", "<br>")
    return f'<div style="max-height:640px;overflow-y:auto;font-size:0.9rem;line-height:1.5">{body}</div>'


# --- sidebar --------------------------------------------------------------------------------
st.sidebar.title("NDA Playbook Reviewer")
pb_names = list_playbooks()
pb_name = st.sidebar.selectbox(
    "Our perspective (playbook)", pb_names, format_func=lambda n: load_playbook(n).name
)
mode = st.sidebar.radio(
    "Contract", ["Example (ContractNLI dev split)", "Upload file", "Paste text"]
)
path = text = None
if mode.startswith("Example"):
    ex = example_docs()
    path = ex[st.sidebar.selectbox("Example NDA", list(ex))]
elif mode == "Upload file":
    up = st.sidebar.file_uploader("PDF, HTML or TXT", type=["pdf", "htm", "html", "txt"])
    if up:
        tmp = Path(tempfile.gettempdir()) / f"nda_upload_{up.name}"
        tmp.write_bytes(up.getvalue())
        path = str(tmp)
else:
    text = st.sidebar.text_area("NDA text", height=200)
with_redlines = st.sidebar.checkbox("Draft redlines (C6)", value=True)
with_memo = st.sidebar.checkbox("Write memo (C7)", value=True)
go = st.sidebar.button("Review contract", type="primary", disabled=not (path or text))
st.sidebar.caption("Output is a draft for a lawyer, not legal advice.")

if go:
    with st.spinner("Reviewing… (C1→C7, ~20–60 s; cached re-runs are instant)"):
        try:
            data = (
                run_file(path, pb_name, with_redlines, with_memo)
                if path
                else run_text(text, pb_name, with_redlines, with_memo)
            )
            st.session_state["result"] = data
        except Exception as e:  # noqa: BLE001 - show any pipeline failure to the user
            st.error(f"Review failed: {e}")

if "result" not in st.session_state:
    st.title("NDA Playbook Reviewer")
    st.write("Pick a perspective and a contract in the sidebar, then **Review contract**.")
    st.dataframe(
        pd.DataFrame(COMPONENTS, columns=["component", "type", "what it does"]),
        hide_index=True,
        width="stretch",
    )
    st.stop()

res = ReviewResult.model_validate(st.session_state["result"])
rep = res.report
hyp = {h.id: h for h in load_hypotheses()}
pb = load_playbook(res.playbook)
rules = {r.id: r for r in pb.rules}

st.title(f"Review · {res.contract.doc_id}")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Risk score", f"{rep.risk_score:.0f}/100")
c2.metric("Recommendation", rep.recommendation.upper())
c3.metric("Issues", len(rep.issues))
c4.metric("Time", f"{sum(res.timings_s.values()):.0f} s")
c5.metric("LLM cost", f"${res.cost_usd:.4f}")
st.caption(f"Playbook: {rep.playbook} · {len(res.contract.spans)} spans")

tabs = st.tabs(["Findings", "Contract", "Redlines", "Memo", "Pipeline & traces"])
span_text = {s.id: " ".join(s.text.split()) for s in res.contract.spans}

with tabs[0]:
    df = pd.DataFrame(
        [
            {
                "": STATUS_ICON[f.status],
                "status": f.status,
                "rule": f.rule_id,
                "topic": f.title,
                "severity": f.severity,
                "contract says": f.label,
                "evidence": ", ".join(map(str, f.evidence)),
            }
            for f in rep.findings
        ]
    )
    st.dataframe(df, hide_index=True, width="stretch")
    for f in rep.findings:
        if f.status in ("OK", "INFO"):
            continue
        with st.expander(f"{STATUS_ICON[f.status]} {f.rule_id} · {f.title} — {f.status}"):
            st.markdown(f"**Hypothesis ({f.hypothesis_id}):** {hyp[f.hypothesis_id].text}")
            st.markdown(f"**Model label:** {f.label} — {f.rationale}")
            st.markdown(f"**Why it matters to us:** {rules[f.rule_id].rationale}")
            for i in f.evidence:
                st.markdown(f"> [{i}] {span_text[i]}")
            if f.status == "MISSING":
                cands = res.retrieval[f.hypothesis_id].hits[:3]
                st.caption(
                    "Closest clauses found by retrieval (C3): "
                    + " · ".join(f"[{h.span_id}] {span_text[h.span_id][:120]}" for h in cands)
                )

with tabs[1]:
    sel = st.selectbox("Highlight evidence of", ["all rules"] + [f.rule_id for f in rep.findings])
    st.markdown(highlight(res, None if sel == "all rules" else sel), unsafe_allow_html=True)

with tabs[2]:
    if not res.redlines:
        st.info("Redlines were not requested.")
    elif not res.redlines.redlines:
        st.success("No issues: nothing to redline.")
    else:
        for r in res.redlines.redlines:
            st.markdown(f"#### {r.rule_id} · {rules[r.rule_id].title} ({r.action})")
            if r.action == "replace":
                orig = " ".join(span_text[i] for i in r.target_span_ids)
                st.markdown(
                    f'<div style="color:#e5534b"><del>{html.escape(orig)}</del></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption(
                    f"insert after [{r.target_span_ids[0]}] {span_text[r.target_span_ids[0]][:160]}"
                )
            st.markdown(
                f'<div style="color:#57ab5a">{html.escape(r.new_text)}</div>',
                unsafe_allow_html=True,
            )
            st.caption(r.explanation)
        st.download_button(
            "Download revised contract (.txt)", res.revised_text or "", file_name="revised_nda.txt"
        )

with tabs[3]:
    if not res.memo:
        st.info("Memo was not requested.")
    else:
        m = res.memo
        st.markdown(f"**Recommendation: {m.recommendation.upper()}**\n\n{m.summary}")
        md = [
            f"# Negotiation memo — {res.contract.doc_id}",
            f"**Recommendation:** {m.recommendation}",
            m.summary,
        ]
        for it in m.issues:
            st.markdown(f"#### {it.rule_id} · {it.headline}")
            st.markdown(
                f"{it.explanation}\n\n**Ask:** {it.ask}"
                + (f"\n\n**Fallback:** {it.fallback}" if it.fallback else "")
            )
            for c in it.citations:
                st.markdown(f"> [{c}] {span_text.get(c, '?')}")
            md += [
                f"## {it.rule_id} · {it.headline}",
                it.explanation,
                f"**Ask:** {it.ask}",
                f"**Fallback:** {it.fallback}" if it.fallback else "",
                *[f"> [{c}] {span_text.get(c, '?')}" for c in it.citations],
            ]
        st.download_button("Download memo (.md)", "\n\n".join(md), file_name="nda_memo.md")

with tabs[4]:
    st.subheader("Components")
    st.dataframe(
        pd.DataFrame(COMPONENTS, columns=["component", "type", "what it does"]),
        hide_index=True,
        width="stretch",
    )
    st.subheader("Timings (s)")
    st.bar_chart(pd.Series(res.timings_s))
    st.subheader("LLM calls")
    if res.traces:
        st.dataframe(
            pd.DataFrame(res.traces)[
                [
                    "component",
                    "model",
                    "cache_hit",
                    "latency_s",
                    "prompt_tokens",
                    "completion_tokens",
                    "cost_usd",
                ]
            ],
            hide_index=True,
            width="stretch",
        )
    if res.ingest:
        st.subheader("C1 ingestion")
        st.write(
            f"format: {res.ingest.source_format}, pages: {res.ingest.n_pages}, "
            f"chars: {len(res.ingest.text)}"
        )
        for w in res.ingest.warnings:
            st.warning(w)
