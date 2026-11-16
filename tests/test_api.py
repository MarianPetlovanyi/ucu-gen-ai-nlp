"""API tests for the Next.js backend (app/api.py). No network: the LLM is faked as in test_pipeline_e2e."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import api
from tests.test_pipeline_e2e import CONTRACT, PLAYBOOK, check_invariants, fake_llm  # noqa: F401

client = TestClient(api.app)


def test_playbooks_lists_rules_and_thresholds():
    r = client.get("/api/playbooks")
    assert r.status_code == 200
    pbs = {p["id"]: p for p in r.json()}
    assert PLAYBOOK in pbs
    pb = pbs[PLAYBOOK]
    assert pb["rules"] and {"id", "title", "severity", "stance", "hypothesis"} <= set(
        pb["rules"][0]
    )
    assert pb["sign_max_risk"] < pb["reject_min_risk"]


def test_review_pasted_text(fake_llm):  # noqa: F811
    r = client.post("/api/review", data={"playbook": PLAYBOOK, "text": CONTRACT})
    assert r.status_code == 200, r.text
    body = r.json()
    res = api.pipeline.ReviewResult.model_validate(body["result"])
    check_invariants(res)
    assert body["source"]["kind"] == "text"
    assert body["playbook"]["id"] == PLAYBOOK
    assert {f.hypothesis_id for f in res.report.findings} <= set(body["hypotheses"])


def test_review_upload(fake_llm, tmp_path):  # noqa: F811
    r = client.post(
        "/api/review",
        data={"playbook": PLAYBOOK, "with_memo": "false"},
        files={"file": ("my nda.txt", CONTRACT.encode(), "text/plain")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == {"kind": "file", "name": "my_nda.txt"}
    assert body["result"]["memo"] is None


@pytest.mark.parametrize(
    "data",
    [
        {"playbook": PLAYBOOK},  # no source
        {"playbook": PLAYBOOK, "text": "x", "example_id": "dev/1"},  # two sources
        {"playbook": "nope", "text": "x"},  # unknown playbook
    ],
)
def test_review_rejects_bad_requests(data):
    assert client.post("/api/review", data=data).status_code == 400


def test_review_rejects_unsupported_file():
    r = client.post(
        "/api/review",
        data={"playbook": PLAYBOOK},
        files={"file": ("nda.docx", b"x", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_eval_summary_shape():
    r = client.get("/api/eval-summary")
    assert r.status_code == 200
    body = r.json()
    assert [c["id"] for c in body["components"]] == ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
    for c in body["components"]:
        for p in c["panels"]:
            keys = {s["key"] for s in p["series"]}
            for row in p["rows"]:
                assert set(row["values"]) <= keys
