# Data flow

Legend: 🟦 tool / deterministic code · 🟩 local model (CPU/GPU) · 🟥 LLM call (Groq) · 🟨 configuration

```mermaid
flowchart LR
    F[/"NDA file<br/>PDF · HTML · TXT<br/>or pasted text"/] --> C1
    subgraph Review pipeline
    C1["🟦 C1 Ingestion<br/>PyMuPDF blocks, HTML parser,<br/>reflow heuristics"] -->|"plain text,<br/>1 paragraph per line"| C2
    C2["🟦 C2 Segmentation<br/>rule-based splitter"] -->|"Contract:<br/>numbered spans"| C3
    C2 -->|"Contract"| C4
    C3["🟩 C3 Evidence retrieval<br/>bge-small, exemplar kNN<br/>over train evidence"] -->|"top-k spans per rule<br/>(UI hints, insertion anchors)"| C6
    C4["🟥 C4 NLI + evidence<br/>gpt-oss-120b, 1 call/contract<br/>prompt nli_v4"] -->|"17 × label + evidence span ids"| C5
    C5["🟦 C5 Playbook compliance<br/>stance → status, risk score,<br/>recommendation"] -->|"ComplianceReport"| C6
    C5 -->|"ComplianceReport"| C7
    C6["🟥 C6 Redline drafter<br/>gpt-oss-120b, 1 call/contract<br/>+ deterministic apply"] -->|"RedlineSet → revised text"| OUT
    C7["🟥 C7 Negotiation memo<br/>gpt-oss-120b, 1 call/contract"] -->|"Memo with span citations"| OUT
    end
    PB[("🟨 playbooks/*.yaml<br/>rules, stances, severities,<br/>preferred clauses, thresholds")] --> C5
    PB --> C6
    PB --> C7
    OUT[/"Streamlit UI<br/>findings · highlights · redlines ·<br/>memo · traces"/]
```

## Evaluation flow (what each eval compares against)

```mermaid
flowchart LR
    G[("ContractNLI gold<br/>text · spans · labels · evidence")]
    G -->|gold text| E1["eval_ingest<br/>word F1, line F1,<br/>evidence recoverability"]
    G -->|gold spans| E2["eval_segment<br/>span/boundary F1,<br/>evidence-span recall"]
    G -->|gold evidence| E3["eval_retrieve<br/>Recall@k, MRR"]
    G -->|gold labels + evidence| E4["eval_nli<br/>macro-F1, Contradiction-F1,<br/>evidence P/R/F1"]
    G -->|"gold labels × playbook<br/>= gold rule status"| E5["eval_playbook<br/>issue P/R/F1, risk ρ"]
    J["🟥 Judge: qwen3.8-27b<br/>(other model family)"] --> E6["eval_redline<br/>fix rate, collateral,<br/>edit ratio, quality"]
    J --> E7["eval_memo<br/>faithfulness"]
    V["validate_judge<br/>known-good / known-bad,<br/>κ vs gold, Claude Code labels"] -.validates.-> J
```

LLM calls per contract: 3 system calls (C4, C6, C7). The evals add judge calls (C6: 2 NLI + 1 quality call;
C7: 1 faithfulness call).
