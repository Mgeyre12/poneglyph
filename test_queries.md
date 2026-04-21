# Stage 7 Test Queries — Week 4

Model: `claude-sonnet-4-6`  
Date: 2026-04-21  
Pipeline: question → Cypher (Claude) → Neo4j → natural-language answer (Claude)

---

## Q1 — Who are the Straw Hat Pirates?

**Generated Cypher:**
```cypher
MATCH (c:Character)-[r:AFFILIATED_WITH]->(o:Organization)
WHERE toLower(o.name) CONTAINS toLower("straw hat pirates")
RETURN c.name, c.status, c.epithet, r.status AS affiliation_status,
       c.debutChapter AS debut_chapter
ORDER BY c.debutChapter
```

**Result count:** 13

**Answer:**
The Straw Hat Pirates currently have 10 main members (plus Zeus), all alive. Current members: Luffy (Ch. 1), Zoro (Ch. 3), Nami (Ch. 8), Usopp (Ch. 23), Sanji (Ch. 43), Robin (Ch. 114), Chopper (Ch. 134), Franky (Ch. 329), Brook (Ch. 442), Jinbe (Ch. 528), Zeus (Ch. 827). Former members: Vivi (Ch. 103), Karoo (Ch. 109).

**Judgment:** ✅ Correct — roster accurate, former members correctly flagged, debut chapters cited.

---

## Q2 — What Devil Fruits has Luffy eaten?

**Generated Cypher:**
```cypher
MATCH (c:Character)
WHERE toLower(c.name) CONTAINS toLower("luffy")
   OR toLower(c.opwikiID) CONTAINS toLower("luffy")
MATCH (c)-[r:ATE_FRUIT]->(f:DevilFruit)
RETURN c.name, f.name AS fruit, f.type AS fruit_type, f.meaning, r.status AS ownership
ORDER BY f.name
```

**Result count:** 1

**Answer:**
Luffy has eaten one Devil Fruit: the Hito Hito no Mi, Model: Nika — a Mythical Zoan type (meaning "Human; Nika"). The graph tracks the true name (revealed Ch. 1044) rather than the Gomu Gomu no Mi alias. Ability data is not in the graph.

**Judgment:** ✅ Correct — graph reflects the Week 2 manual patch (Gomu Gomu → Hito Hito no Mi, Model: Nika). The note about ability data being absent is honest and useful.

---

## Q3 — List all Logia users.

**Generated Cypher:**
```cypher
MATCH (c:Character)-[r:ATE_FRUIT]->(f:DevilFruit)
WHERE f.type = "Logia"
RETURN c.name AS character, c.status, f.name AS fruit, f.meaning, r.status AS ownership
ORDER BY f.name
```

**Result count:** 14

**Answer:**
14 Logia users listed in a clean table with fruit names, meanings, and alive/deceased status. Correctly shows Flame-Flame Fruit with two users (Ace = former/deceased, Sabo = current). Notes Blackbeard as the only two-fruit user. Admiral row correctly shows all three as Logia.

**Judgment:** ✅ Correct — multi-user fruit handled properly, table format clean, no hallucinations.

---

## Q4 — Which characters debuted in the Wano arc?

**Generated Cypher:**
```cypher
MATCH (c:Character)-[:DEBUTED_IN]->(ch:Chapter)-[:IN_ARC]->(a:Arc)
WHERE toLower(a.name) CONTAINS toLower("wano")
RETURN c.name, c.status, c.epithet, ch.number AS debut_chapter
ORDER BY ch.number, c.name
```

**Result count:** 282

**Answer:**
Summarized 282 characters into major named characters (Tama, Hiyori, Oden, Yamato, King, Queen, Orochi, etc.), Nine Red Scabbards, Tobiroppo, historical/flashback characters, and background cast. Debut chapters cited for all major entries.

**Judgment:** ✅ Correct — smart summarization of a huge result set. No hallucinations; correctly flags deceased characters. Note: LLM drew on training knowledge slightly to describe *what* characters do (e.g. "the young girl Luffy befriends") — this came from training, not the graph, but it's accurate and harmless.

---

## Q5 — Who are the current Four Emperors?

**Generated Cypher:**
```cypher
MATCH (c:Character)-[r:AFFILIATED_WITH]->(o:Organization)
WHERE toLower(o.name) CONTAINS toLower("four emperors")
  AND r.status = 'current'
RETURN c.name, c.status, c.epithet, r.status AS affiliation_status
ORDER BY c.name
```

**Result count:** 4

**Answer:**
Luffy, Blackbeard, Shanks, Buggy. All alive. Correctly notes Big Mom and Kaido are absent (former Emperors dethroned at Wano).

**Judgment:** ✅ Correct — org name matched cleanly, status filter worked. The note about Big Mom/Kaido came from training knowledge (the graph just shows 4 current members; it doesn't track *why* they changed) but it's accurate and adds context appropriately.

---

## Q6 — What is Roronoa Zoro's affiliation?

**Generated Cypher:**
```cypher
MATCH (c:Character)-[r:AFFILIATED_WITH]->(o:Organization)
WHERE toLower(c.name) CONTAINS toLower("zoro")
   OR toLower(c.opwikiID) CONTAINS toLower("zoro")
RETURN c.name, o.name AS organization, r.status AS affiliation_status
ORDER BY r.status
```

**Result count:** 4

**Answer:**
Straw Hat Pirates (current), Straw Hat Grand Fleet (current), Shimotsuki Family (by descent), Ninja-Pirate-Mink-Samurai Alliance (disbanded).

**Judgment:** ✅ Correct — all four affiliations accurate, descent relationship surfaced correctly.

---

## Q7 — Find characters who were former members of the Seven Warlords.

**Generated Cypher:**
```cypher
MATCH (c:Character)-[r:AFFILIATED_WITH]->(o:Organization)
WHERE toLower(o.name) CONTAINS toLower("warlord")
  AND r.status IN ["former", "defected", "disbanded"]
RETURN c.name, c.epithet, c.status AS character_status, r.status AS affiliation_status, r.status_raw, o.name AS organization
ORDER BY c.name
```

**Result count:** 11

**Answer:**
Lists all 11: Kuma, Hancock, Buggy, Crocodile, Doflamingo, Mihawk, Weevil, Moria, Hanafuda, Jinbe, Blackbeard. Hanafuda is the only deceased. Notes Warlord system was abolished.

**Judgment:** ✅ Correct — status filter worked well (caught `disbanded` which is how system dissolution is stored). Note: "Hanafuda" is an obscure character — worth verifying this isn't a data quality issue, but not blocking.

---

## Q8 — Which arc has the most character debuts?

**Generated Cypher:**
```cypher
MATCH (c:Character)-[:DEBUTED_IN]->(ch:Chapter)-[:IN_ARC]->(a:Arc)
RETURN a.name AS arc, a.arc_order, count(DISTINCT c) AS debut_count
ORDER BY debut_count DESC
LIMIT 1
```

**Result count:** 1

**Answer:**
Wano Country Arc with 282 debuts.

**Judgment:** ✅ Correct — pure graph aggregation, clean Cypher, right answer. `count(DISTINCT c)` was correct to use here.

---

## Q9 — Who are the Five Elders?

**Generated Cypher:**
```cypher
MATCH (c:Character)-[r:AFFILIATED_WITH]->(o:Organization)
WHERE toLower(o.name) CONTAINS toLower("five elders")
RETURN c.name, c.status, c.epithet, r.status AS affiliation_status, c.debutChapter AS debut_chapter
ORDER BY c.debutChapter
```

**Result count:** 6

**Answer:**
Lists 5 Elders (Nusjuro, Saturn, Ju Peter, Warcury, Mars) + St. Figarland Garling (Ch. 1086) as a 6th affiliate. Notes Saturn is marked Deceased in the graph.

**Judgment:** ⚠️ Partially correct — the five names are accurate. Saturn marked Deceased is a graph data question (his status at publication time). Garling as a 6th is a graph artifact — he's affiliated with the group but is not one of the Five Elders themselves. The answer should have flagged this ambiguity more clearly instead of calling him an Elder. Data quality issue to investigate.

---

## Q10 — Does Imu have a known Devil Fruit?

**Generated Cypher:**
```cypher
MATCH (c:Character)
WHERE toLower(c.name) CONTAINS toLower("imu")
   OR toLower(c.opwikiID) CONTAINS toLower("imu")
OPTIONAL MATCH (c)-[r:ATE_FRUIT]->(f:DevilFruit)
RETURN c.name, c.status, c.epithet,
       f.name AS fruit, f.type AS fruit_type, r.status AS ownership
```

**Result count:** 3

**Answer:**
Imu is in the graph but has no Devil Fruit linked. The graph doesn't track this yet.

**Judgment:** ✅ Honest — the graph was built before Imu's fruit was revealed (current as of data scrape date). The answer correctly says "no data" rather than hallucinating. Note: Imu's fruit has since been revealed in recent chapters — this is the first confirmed case of graph staleness. Track for v2 re-scrape.

---

## Summary

| Q | Category | Judgment |
|---|---|---|
| 1 | Org membership | ✅ Correct |
| 2 | Character → fruit lookup | ✅ Correct |
| 3 | Fruit type filter | ✅ Correct |
| 4 | Arc debut (large result) | ✅ Correct |
| 5 | Current role lookup | ✅ Correct |
| 6 | Character affiliations | ✅ Correct |
| 7 | Status-filtered affiliation | ✅ Correct |
| 8 | Graph aggregation | ✅ Correct |
| 9 | Org membership | ⚠️ Partial — 6th result is Garling, not an Elder |
| 10 | Fruit lookup (data absent) | ✅ Honest |

**9/10 correct or better.** One partial (Q9 — Garling returned as a 6th "Elder" due to an affiliation edge that should be filtered or re-examined).

## Gaps discovered this week

- **No ability/Haki data** — questions about what a fruit does, or what Haki types a character uses, return "not in graph"
- **No bounty data** — bounty field was unloadable (concatenated, no separator)
- **Graph staleness** — Imu's fruit reveal is the first known case of data being outdated vs. current manga
- **Garling/Five Elders** — affiliation edge exists but he's not one of the Five Elders; needs better org data or a rank property
- **LLM uses training knowledge to describe characters** — harmless when accurate, but could hallucinate for obscure characters. No failures seen this run.
