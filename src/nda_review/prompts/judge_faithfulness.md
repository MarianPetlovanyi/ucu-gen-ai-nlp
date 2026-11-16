You check a negotiation memo about an NDA for faithfulness. For each memo item you get the claim the
memo makes about the contract and the contract spans it cites. You do NOT judge the advice or the ask,
only whether the factual statements about what the contract says (or does not say) are supported.

- supported: every factual statement about the contract is backed by the cited spans (for an item that
  says the contract is silent on a topic, the cited spans, if any, must not regulate that topic).
- unsupported: at least one statement about the contract is not backed by, or contradicts, the cited
  spans.

Answer with one JSON object and nothing else:
{"verdicts": [{"rule_id": "R02", "supported": true | false, "reason": "at most 25 words"}, ...]}
Decide first, then write the JSON. Never reason inside the JSON.
