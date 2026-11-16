"""ContractNLI loader. Read-only access to data/raw; returns gold contracts, labels and evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from nda_review.config import EXCLUDED_TRAIN_IDS, PLAYBOOK_DIR, RAW_DIR, RAW_FILES_DIR
from nda_review.schemas import Contract, Hypothesis, Playbook, Span

SPLITS = ("train", "dev", "test")


@dataclass
class GoldDoc:
    doc_id: str
    file_name: str
    document_type: str
    contract: Contract  # gold text + gold spans
    labels: dict[str, str]  # hypothesis id -> gold label
    evidence: dict[str, list[int]] = field(default_factory=dict)  # hypothesis id -> gold span ids

    @property
    def raw_path(self) -> Path:
        return RAW_FILES_DIR / self.file_name


@lru_cache(maxsize=4)
def _load_json(split: str) -> dict:
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}")
    return json.loads((RAW_DIR / f"{split}.json").read_text(encoding="utf-8"))


def gold_spans(text: str, offsets: list[list[int]]) -> list[Span]:
    return [Span(id=i, start=s, end=e, text=text[s:e]) for i, (s, e) in enumerate(offsets)]


def load_split(split: str, limit: int | None = None) -> list[GoldDoc]:
    """Load a split. Train excludes documents that duplicate test documents."""
    docs = []
    for d in _load_json(split)["documents"]:
        doc_id = str(d["id"])
        if split == "train" and doc_id in EXCLUDED_TRAIN_IDS:
            continue
        ann = d["annotation_sets"][0]["annotations"]
        docs.append(
            GoldDoc(
                doc_id=f"{split}/{doc_id}",
                file_name=d["file_name"],
                document_type=d["document_type"],
                contract=Contract(
                    doc_id=f"{split}/{doc_id}",
                    text=d["text"],
                    spans=gold_spans(d["text"], d["spans"]),
                ),
                labels={h: a["choice"] for h, a in ann.items()},
                evidence={h: list(a["spans"]) for h, a in ann.items()},
            )
        )
    return docs[:limit] if limit else docs


def load_hypotheses() -> list[Hypothesis]:
    labels = _load_json("train")["labels"]
    return [
        Hypothesis(id=h, short=v["short_description"], text=v["hypothesis"])
        for h, v in sorted(labels.items(), key=lambda kv: int(kv[0].split("-")[1]))
    ]


def load_playbook(name: str) -> Playbook:
    """`name` is a file stem in playbooks/, e.g. 'disclosing_party'."""
    raw = yaml.safe_load((PLAYBOOK_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    return Playbook.model_validate(raw)


def list_playbooks() -> list[str]:
    return sorted(p.stem for p in PLAYBOOK_DIR.glob("*.yaml"))
