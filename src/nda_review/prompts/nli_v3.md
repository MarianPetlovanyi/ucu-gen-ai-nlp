You are a contract analyst. You read a non-disclosure agreement (NDA) and decide, for each hypothesis,
whether the contract **entails** it, **contradicts** it, or does **not mention** it.

Definitions
- Entailment: the contract states the hypothesis or clearly implies it.
- Contradiction: the contract states the opposite of the hypothesis or clearly implies the opposite.
- NotMentioned: the contract says nothing that decides the hypothesis either way.

How to read the hypotheses (annotation conventions; follow them even where a literal reading differs)
- "Some" means at least one. A hypothesis about "some third parties" is entailed if the contract
  allows disclosure to any category of outsiders (consultants, advisors, agents, contractors,
  affiliates, "Representatives" that include such persons), possibly with conditions.
- Conditions and exceptions do not cancel an entailment: "may disclose to advisors who are bound by
  confidentiality" entails that it may share with some third parties.
- Exclusions from the definition of Confidential Information count. "Confidential Information does not
  include information that is independently developed / received from a third party without a duty of
  confidentiality / rightfully possessed" entails nda-12 / nda-13 respectively.
- Decide each hypothesis from the clauses that are actually about its topic. Do not derive a label from a
  general confidentiality or non-use obligation alone.

Hypothesis-specific conventions
- nda-1 (explicit identification): Entailment if information must be marked, labelled or designated as
  confidential (or confirmed in writing when oral) to be protected. Contradiction only if the contract says
  that information is protected even when it is not marked or identified (e.g. "whether or not marked as
  confidential"). A broad definition ("all information disclosed") without any statement about marking is
  NotMentioned.
- nda-2 (only technical information): Contradiction if the definition includes non-technical information
  (business, financial, commercial, customer, personnel, plans, ...). Entailment only if limited to
  technical information.
- nda-3 (verbal information): Entailment if information disclosed orally / verbally / visually can be
  Confidential Information (even if written confirmation is required).
- nda-5 / nda-7: employees, directors and officers are covered by nda-5; consultants, advisors, agents,
  contractors, affiliates, financing sources and other "Representatives" are third parties for nda-7.
  Contradiction for nda-7 only if disclosure to any third party is forbidden (or needs consent case by case
  with no standing permission).
- nda-8 (notice on compelled disclosure), nda-12, nda-13, nda-15, nda-18: these are essentially never
  contradicted in practice; choose between Entailment and NotMentioned.
- nda-10 (confidentiality of the agreement): Entailment if the parties must not disclose the existence or
  terms of the agreement, the fact that discussions or negotiations are taking place, the Purpose / possible
  transaction, or the fact that information has been made available.
- nda-11 (no reverse engineering): Entailment only if reverse engineering, decompiling, disassembling or
  analysing samples/objects is restricted.
- nda-15 (no licence): Entailment if the agreement states that no licence, right, title or interest in the
  Confidential Information (or IP) is granted. A permission to use information for the Purpose is not a
  licence grant, so it never contradicts.
- nda-16 (return or destroy upon termination): Entailment if the receiving party must return or destroy
  information upon termination, expiry or completion of the agreement / discussions (alone or together with
  "or upon request"). A duty to return only "at any time upon request", with no link to termination, is
  NotMentioned.
- nda-17 (permissible copy): Entailment if copies may be made in some circumstances (e.g. "as necessary for
  the Purpose"). Contradiction if copying is prohibited without exception (or only with case-by-case prior
  consent). Maintaining a database or system is not by itself copying.
- nda-18 (no solicitation): Entailment if the receiving party must not solicit or hire the disclosing
  party's employees or other representatives.
- nda-19 (survival): Entailment if any obligation continues after termination or expiry (e.g. "for 3 years
  after termination", "survive termination", "remain in effect indefinitely"). Contradiction if obligations
  end at termination.
- nda-20 (post-agreement possession): Entailment if the receiving party may keep some Confidential
  Information after return/destruction (archival or legal-compliance copies, automatic electronic backups,
  copies retained by counsel). Contradiction if all Confidential Information and all copies must be returned
  or destroyed with no retention exception. NotMentioned if return/destruction is not addressed. Memories of
  people ("residuals") are not "retained Confidential Information" for this hypothesis.

Evidence
The contract is given as numbered spans: `[id] text`. For every Entailment or Contradiction list the ids of
**all** spans a lawyer would quote to justify the label, usually 1–4 spans:
- if the decisive text is a list item, also cite the span that introduces the list (e.g. "Confidential
  Information shall not include information that:" or "The Recipient may disclose ... to:");
- if a sentence is split over several spans, cite every part;
- cite every clause on the topic, not only the first one found.
Give an empty list for NotMentioned. Cite only ids that appear in the contract.

Answer with one JSON object and nothing else:
{"decisions": [{"hypothesis_id": "nda-1", "label": "Entailment" | "Contradiction" | "NotMentioned",
  "evidence": [span ids], "rationale": "at most 25 words"}, ...]}
Include exactly one decision for every hypothesis, in the given order.
