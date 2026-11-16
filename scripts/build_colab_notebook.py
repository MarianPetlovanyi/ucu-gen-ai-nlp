"""Generates notebooks/finetune_colab.ipynb (self-contained: downloads data, trains, predicts).

Usage: uv run python scripts/build_colab_notebook.py
"""

import json
from pathlib import Path

CELLS = [
    (
        "md",
        """# C4 baseline: fine-tuned DeBERTa span-NLI on ContractNLI (Colab, T4)

Self-contained. **Runtime → Change runtime type → T4 GPU**, then *Run all* (~35–45 min).

What it does (span-level NLI, the approach of the ContractNLI paper, simplified):
1. Downloads ContractNLI (CC BY 4.0) from the official site.
2. Builds (hypothesis, span) training pairs from the **train split only**: gold evidence spans get the
   document label (entailment / contradiction), other spans of the same document are `neutral`.
   Train document 538 is excluded (exact duplicate of test 537).
3. Zero-shot pass: scores every span of dev+test with the *un-tuned* MNLI model (zero-shot baseline).
4. Fine-tunes `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` for 2 epochs.
5. Scores every (span, hypothesis) of dev+test with the fine-tuned model.
6. Saves `span_probs.json` (P(entail), P(contradict) per span) and downloads it.
   Put it into `data/processed/finetuned/` locally. Thresholds are tuned on dev in `evals/eval_nli.py`.""",
    ),
    (
        "code",
        """!nvidia-smi --query-gpu=name,memory.total --format=csv
!pip -q install -U "transformers>=4.44" accelerate sentencepiece""",
    ),
    (
        "code",
        """import json, random, zipfile, urllib.request, os, time, math
import numpy as np, torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup
SEED = 13
random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
DEV = 'cuda'
MODEL = 'MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli'   # id2label: 0 entailment, 1 neutral, 2 contradiction
URL = 'https://stanfordnlp.github.io/contract-nli/resources/contract-nli.zip'
if not os.path.exists('contract-nli'):
    urllib.request.urlretrieve(URL, 'cnli.zip'); zipfile.ZipFile('cnli.zip').extractall('.')
D = {s: json.load(open(f'contract-nli/{s}.json')) for s in ('train', 'dev', 'test')}
HYP = {k: v['hypothesis'] for k, v in D['train']['labels'].items()}
EXCLUDED_TRAIN = {'538'}
train_docs = [d for d in D['train']['documents'] if str(d['id']) not in EXCLUDED_TRAIN]
print({s: len(D[s]['documents']) for s in D}, 'train used:', len(train_docs), 'hypotheses:', len(HYP))""",
    ),
    (
        "code",
        """# ---- training pairs (train split only) ----
LAB = {'Entailment': 0, 'Contradiction': 2}
NEG_PER_PAIR = 3          # random neutral spans per (doc, hypothesis)
def span_text(d, i):
    s, e = d['spans'][i]; return d['text'][s:e].strip()
pairs = []
for d in train_docs:
    n = len(d['spans'])
    for h, a in d['annotation_sets'][0]['annotations'].items():
        ev = set(a['spans'])
        if a['choice'] in LAB:
            for i in ev: pairs.append((HYP[h], span_text(d, i), LAB[a['choice']]))
        cand = [i for i in range(n) if i not in ev and len(span_text(d, i)) > 20]
        for i in random.sample(cand, min(NEG_PER_PAIR, len(cand))):
            pairs.append((HYP[h], span_text(d, i), 1))
random.shuffle(pairs)
from collections import Counter
print(len(pairs), Counter(p[2] for p in pairs))""",
    ),
    (
        "code",
        """tok = AutoTokenizer.from_pretrained(MODEL)
MAXLEN = 256
class PairDS(Dataset):
    def __init__(self, pairs): self.p = pairs
    def __len__(self): return len(self.p)
    def __getitem__(self, i): return self.p[i]
def collate(batch):
    enc = tok([b[0] for b in batch], [b[1] for b in batch], truncation='only_second', max_length=MAXLEN,
              padding=True, return_tensors='pt')
    if len(batch[0]) > 2: enc['labels'] = torch.tensor([b[2] for b in batch])
    return enc

@torch.no_grad()
def score_split(model, split, bs=128):
    \"\"\"Returns {doc_id: {hyp: [[p_entail, p_contradict], ...per span]}}\"\"\"
    model.eval(); out = {}
    items = []
    for d in D[split]['documents']:
        for h in HYP:
            for i in range(len(d['spans'])):
                items.append((str(d['id']), h, i, HYP[h], span_text(d, i) or '.'))
    items.sort(key=lambda x: len(x[4]))   # length bucketing = faster
    probs = np.zeros((len(items), 2), dtype=np.float32)
    t0 = time.time()
    for k in range(0, len(items), bs):
        chunk = items[k:k+bs]
        enc = tok([c[3] for c in chunk], [c[4] for c in chunk], truncation='only_second',
                  max_length=MAXLEN, padding=True, return_tensors='pt').to(DEV)
        with torch.autocast('cuda', dtype=torch.float16):
            p = model(**enc).logits.float().softmax(-1).cpu().numpy()
        probs[k:k+len(chunk)] = p[:, [0, 2]]
    for (doc, h, i, _, _), pr in zip(items, probs):
        out.setdefault(doc, {}).setdefault(h, {})[i] = [round(float(pr[0]), 4), round(float(pr[1]), 4)]
    out = {doc: {h: [v[i] for i in sorted(v)] for h, v in hs.items()} for doc, hs in out.items()}
    print(split, len(items), 'pairs', round(time.time() - t0), 's')
    return out""",
    ),
    (
        "code",
        """# ---- zero-shot baseline: the un-tuned MNLI model ----
model = AutoModelForSequenceClassification.from_pretrained(MODEL).float().to(DEV)  # fp32 master weights for AMP
results = {'zeroshot': {s: score_split(model, s) for s in ('dev', 'test')}}""",
    ),
    (
        "code",
        """# ---- fine-tune ----
EPOCHS, BS, LR = 2, 32, 2e-5
dl = DataLoader(PairDS(pairs), batch_size=BS, shuffle=True, collate_fn=collate)
opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
steps = EPOCHS * len(dl)
sched = get_linear_schedule_with_warmup(opt, int(0.06 * steps), steps)
scaler = torch.cuda.amp.GradScaler()
model.train(); t0 = time.time()
for ep in range(EPOCHS):
    tot = 0
    for step, batch in enumerate(dl):
        batch = {k: v.to(DEV) for k, v in batch.items()}
        with torch.autocast('cuda', dtype=torch.float16):
            loss = model(**batch).loss
        scaler.scale(loss).backward(); scaler.unscale_(opt)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(opt); scaler.update(); opt.zero_grad(); sched.step()
        tot += loss.item()
        if step % 200 == 0: print(f'ep {ep} step {step}/{len(dl)} loss {tot/(step+1):.4f} {time.time()-t0:.0f}s')
print('trained in', round(time.time() - t0), 's')""",
    ),
    (
        "code",
        """results['finetuned'] = {s: score_split(model, s) for s in ('dev', 'test')}
results['meta'] = {'model': MODEL, 'epochs': EPOCHS, 'batch_size': BS, 'lr': LR, 'max_len': MAXLEN,
                   'neg_per_pair': NEG_PER_PAIR, 'n_train_pairs': len(pairs), 'seed': SEED,
                   'excluded_train_ids': sorted(EXCLUDED_TRAIN)}
json.dump(results, open('span_probs.json', 'w'))
print(os.path.getsize('span_probs.json') / 1e6, 'MB')
from google.colab import files
files.download('span_probs.json')""",
    ),
    (
        "code",
        """# optional: keep the fine-tuned weights in Google Drive
# from google.colab import drive; drive.mount('/content/drive')
# model.save_pretrained('/content/drive/MyDrive/nda-deberta-spannli'); tok.save_pretrained('/content/drive/MyDrive/nda-deberta-spannli')""",
    ),
]


def cell(kind: str, src: str) -> dict:
    lines = src.splitlines(keepends=True)
    if kind == "md":
        return {"cell_type": "markdown", "metadata": {}, "source": lines}
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": lines,
    }


nb = {
    "cells": [cell(k, s) for k, s in CELLS],
    "metadata": {
        "accelerator": "GPU",
        "colab": {"provenance": []},
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}
Path("notebooks/finetune_colab.ipynb").write_text(json.dumps(nb, indent=1))
print("wrote notebooks/finetune_colab.ipynb")
