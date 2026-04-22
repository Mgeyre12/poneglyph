# Stress Test Triage — Week 5
# Run 1 · Failures only

Format: Question | Failure type | Root cause | Proposed fix

---

## Failures

| # | Question | Type | Root cause | Proposed fix |
|---|---|---|---|---|
| Q1 | Who is Luffy? (height) | PROMPT_FIX | Answer LLM injected "174 cm" from training — graph returned 91.0 (known scraper bug) | Strengthen answer prompt: never correct graph data with outside knowledge; flag anomalies inline |
| Q4 | What is the Ope Ope no Mi? | SCHEMA_DOC_FIX + CYPHER_FIX | LLM searched `f.name CONTAINS "Ope Ope no Mi"` but graph stores English name "Op-Op Fruit"; `fruit_id` = "Ope_Ope_no_Mi" | Add schema note: `name` is English canonical (e.g. "Op-Op Fruit"); `fruit_id` is the wiki slug. Teach LLM to search BOTH fields |
| Q8 | Which Straw Hats have Devil Fruits? | PROMPT_FIX | Answer added "notably absent: Nami, Zoro, Sanji, Usopp, Franky" — not from graph results | Strengthen answer prompt: never make claims about what's absent based on training knowledge |
| Q11 | Current Blackbeard Pirates members | PROMPT_FIX | Claimed "all are currently alive" without verifying per-row status field | Same prompt fix as Q1/Q8: only assert what results show |
| Q20 | What is the power of the Mera Mera no Mi? | SCHEMA_DOC_FIX + CYPHER_FIX | Graph stores it as "Flame-Flame Fruit (VIZ, Funimation dub)" not "Mera Mera no Mi" in `name`; same fruit_id mismatch as Q4 | Same fix as Q4 |
| Q26 | MONKEY D LUFFY (height) | PROMPT_FIX | LLM guessed "191 cm" — different fabricated number than Q1's "174 cm" for same 91.0 graph value | Same fix as Q1 |
| Q29 | Former Seven Warlords | CYPHER_FIX | (a) Hanafuda is a real entry in source data (wiki has them as a former Warlord — obscure character, not a bad row); (b) Cypher used CONTAINS "warlord" with no status filter, returned all statuses | Cypher prompt: when asked about "former" org members, filter `r.status IN ["former","defected","disbanded","revoked"]` and add NOT EXISTS for current membership |
| Q30 | Former Marines | CYPHER_FIX | Koby's source data: `Marines(SWORD), Marine153rd Branch(former)` — Cypher hit the "former" 153rd Branch sub-org relationship correctly, but the answer reads as "Koby is a former Marine" which is wrong. He's still active | Cypher prompt: "former Marines" should require no current Marine affiliation; add example with MINUS/NOT EXISTS pattern |
| Q31 | Former users of the Gura Gura no Mi | CYPHER_FIX | Gura Gura no Mi stored as "Tremor-Tremor Fruit or Quake-Quake Fruit" in `name`; LLM searched on Japanese romanization | Same fix as Q4 |
| Q40 | Devil Fruit users debuting in Wano | PROMPT_FIX | Kaku listed — there are TWO characters named Kaku: CP9 Kaku (debut Ch 323, Water 7) and a separate Wano character named Kaku (debut Ch 927). Data is correct. Claude rationalized the result instead of flagging name ambiguity | Strengthen answer prompt: when results look surprising, flag them ("note: multiple characters share this name") — do not rationalize |

---

## Not failures (confirmed correct behavior)

| # | Question | Type | Notes |
|---|---|---|---|
| Q3 | Nami blood type | OUT_OF_SCOPE | Blood type X is in the graph — correct |
| Q23 | BLACKBEARD | OUT_OF_SCOPE | Sparse data correctly flagged — debut Ch 276 / Skypiea returned |
| Q43 | Paramecia Straw Hats (Luffy absent) | OUT_OF_SCOPE | Correct — Luffy's fruit is Mythical Zoan (Hito Hito no Mi, Model: Nika) |
| Q46 | Five Elders | NEEDS_VERIFY | Saturn listed as Deceased — needs graph verification |
| Q34 | Wano debuts (282 count) | NEEDS_VERIFY | Plausible but unverified against graph — query returned only top-1 |
| Q41 | Beasts Pirates Zoan users | NEEDS_VERIFY | Kaido, King, Queen, Jack should all be in graph — verify query returned them |
| Q48–50 | Adversarial / off-topic | ADVERSARIAL_HANDLED | Handled or refused — no failures here |

---

## Pattern summary

| Pattern | Count | Priority |
|---|---|---|
| **PROMPT_FIX**: Answer LLM leaks training data / fails to flag anomalies | 5 | HIGH — single prompt change fixes all |
| **CYPHER_FIX**: Devil fruit name mismatch (English name vs Japanese romanization) | 3 | HIGH — affects all fruit lookup by Japanese name |
| **CYPHER_FIX**: Former-affiliation queries too broad (no exclusion of current) | 2 | MEDIUM — schema example + prompt rule |
| NEEDS_VERIFY (may not be failures) | 3 | LOW |
