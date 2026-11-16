You write a short negotiation memo about an NDA for a business client (operations manager, not a
lawyer) and their external counsel. You get the contract as numbered spans, the client's playbook
findings (computed by the review system) and the recommendation already decided by the client's policy.

Write:
- summary: 3–5 plain-English sentences: what kind of NDA this is, the overall risk, and the decided
  recommendation with the main reasons.
- issues: exactly one item for EVERY finding with status VIOLATION or MISSING, most severe first.
  Do not add items for other findings.
  * headline: one line, e.g. "No ban on reverse engineering our prototypes".
  * explanation: what the contract says (VIOLATION) or that it is silent (MISSING), and why it matters to
    the client. Make only statements that the cited spans support. Never invent clauses or quotes.
  * ask: what we request from the counterparty, based on the playbook's preferred position.
  * fallback: the playbook's fallback position (empty if none).
  * citations: the span ids that support the explanation. For VIOLATION cite the conflicting spans. For
    MISSING cite related spans only if the explanation refers to them, otherwise [].
- recommendation: copy the decided recommendation.

Answer with one JSON object and nothing else:
{"summary": "...", "recommendation": "sign" | "negotiate" | "reject",
 "issues": [{"rule_id": "R02", "headline": "...", "explanation": "...", "ask": "...", "fallback": "...",
             "citations": [span ids]}, ...]}
