# Locations & Occupations — Data Audit (Week 8, Stage 1)

**Date:** 2026-04-22  
**Source:** `data/full-character-data-processed-2.json` (1,517 characters)  
**Neo4j state:** `:Location` = 0, `:Occupation` = 0, all new rel types = 0 (clean slate)

---

## 1. Field Coverage

| Field | Populated | % of 1,517 |
|---|---|---|
| `Origin` | 576 | 38.0% |
| `Residence` | 701 | 46.2% |
| `Occupations` | 1,276 | 84.1% |

Occupations is by far the most complete. Origin and Residence have 54–62% gaps — many minor characters lack this data on the wiki.

---

## 2. Origin Field

### Format
Two variants:
- **Sea only:** `"East Blue"` (262 chars)
- **Sea + specific:** `"East Blue(Foosha Village)"` (314 chars)

### Sea values
| Sea | Count |
|---|---|
| Grand Line | 286 |
| East Blue | 108 |
| North Blue | 53 |
| West Blue | 38 |
| South Blue | 36 |
| Calm Belt | 20 |
| Sky Islands | 15 |
| Red Line | 6 |
| Other (Wano, Jaya, etc.) | 14 |

Grand Line dominates (49.7% of chars with Origin).

### Specific location diversity
- 67 unique specific location values
- Top locations: Ryugu Kingdom (48), Fish-Man Island (40), Wano Country (36), Amazon Lily (20), Elbaph (14), Skypiea (11), Egghead (10)

### Edge cases
- **Multi-specific inside parens (39 chars):** `"Grand Line(Ryugu Kingdom;Fish-Man Island)"` — semicolon inside the parenthetical means two specific locations. All 39 are this exact case. A parser must split on `;` inside the paren, not just extract the whole string.
- **No nested parens:** Zero cases — safe to assume at most one level of parenthetical.
- **Unusual sea values:** `"Punk Hazard"`, `"Wano Country"`, `"Jaya"` used as the top-level "sea" slot (not standard seas). Treat them as locations, not seas — or just store the whole string verbatim.

---

## 3. Residence Field

### Volume
- 701 chars have Residence; 822 total entries
- Avg: 1.2 entries per char; max: 5; distribution: 1 (603), 2 (82), 3+ (16)
- Delimiter: semicolon (same as Affiliations)

### Status annotations
Parenthetical suffixes, same pattern as Affiliations:

| Status | Count |
|---|---|
| former / formerly | 237 |
| temporary | 11 |
| non-canon (≠ or explicit) | 2 |

No "defected" or "disbanded" variants — residence uses only former/temporary.

### Sub-location parentheticals
Many entries have *two* parenthetical groups:
```
"Wano Country (Flower Capital)"          ← sub-location in first paren
"Shells Town(153rd Branch) (former)"     ← sub-location + status
"Mermaid Cove(Coral Hill)Fish-Man District(former)"  ← fused + sub-location
```
The sub-location paren contains a place name, not a status keyword. A parser must distinguish "former/temporary" parens from sub-location parens.

### Fusion defects (31 chars)
Missing semicolons between consecutive locations, e.g.:
```
"Fish-Man District(former)Arlong Park(former)"
"Wano Country (Flower Capital)Wano Country (Kibi)"
"ElbaphEnies Lobby(former)Water 7(former)"
```
These are scraper bugs. Affects 31 chars (~4.4% of chars with Residence). Fixable by splitting on `)(` or before an uppercase letter that follows `)`, but needs careful handling.

### Unique location names
~231 unique location strings after stripping status parens. Top entries:
Wano Country (102), Elbaph (37), Mary Geoise (31), Hachinosu (30), Water 7 (28), Amazon Lily (21), Dressrosa (19), Egghead (18), Fish-Man District (17).

---

## 4. Occupations Field

### Volume
- 1,276 chars; 2,053 total entries
- Avg: 1.6 entries per char; max: 8
- Delimiter: semicolon

### Status annotations
| Status | Count |
|---|---|
| former / formerly | 360 |
| temporary / temporarily | 7 |
| non-canon (≠) | 2 |

Also: `undercover`, `acting`, `cover`, `illegitimate`, `promoted`, `demoted` appear inside parens for some entries — these are role-context qualifiers, not just status.

### Fusion defects — significant problem
**260 chars (20.4% of chars with Occupations)** have fused tokens where the scraper dropped spaces between words, e.g.:
```
"PirateOfficer"          (should be "Pirate Officer")
"MarineRear Admiral"     (should be "Marine Rear Admiral")
"SeniorOfficer"          (should be "Senior Officer")
"QueenofTotto Land"      (should be "Queen of Totto Land")
"CrewCombatant"          (should be "Crew Combatant")
"GodofSkypiea"           (should be "God of Skypiea")
```
This is the most serious data quality issue. Affects ~1 in 5 characters with Occupations. Sources of fusion:
- **Rank + role concatenation:** "PirateOfficer", "MarineOfficer", "CipherPolAgent"
- **Title + name concatenation:** "QueenofTotto Land", "KingofDressrosa"
- **Multiple entries without delimiter:** "Revolutionary Army memberFish-Man KarateInstructorFish-Man JujutsuMartial Artist"

These would create garbage `:Occupation` nodes if stored verbatim.

### Non-canon markers
2 entries with `≠` suffix (same pattern as Affiliations). Very rare — can be filtered with the same logic.

---

## 5. Key Decisions Needed Before Stage 2

### Decision A: Location granularity for Origin
Three options:
1. **Leaf only** — store just the specific location (`"Foosha Village"`), infer sea from it. Loses data for sea-only chars.
2. **Sea + optional specific** — two separate `BORN_IN` rels: one to sea node, one to specific. More nodes but fuller coverage.
3. **Store Origin verbatim as a string on `:Character`** — no `:Location` nodes for Origin; only use Residence for `:RESIDES_IN`. Simpler but queries can't traverse born_in.

### Decision B: Fused occupation tokens
Three options:
1. **Skip fused chars entirely** — ingest clean occupations (80% of chars), skip the 20% with fusion. Simple, avoids bad data.
2. **Regex-split on camelCase boundary** — `re.sub(r"([a-z])([A-Z])", r"\1 \2", s)`. Fixes most cases but "PirateOfficer" → "Pirate Officer" isn't wrong, but "QueenofTotto Land" → "Queenof Totto Land" still needs the preposition fixed.
3. **Best-effort normalize + flag** — apply camelCase split, strip `≠`, store normalized, add `data_quality: "normalized"` property on the rel. Gives most coverage; downstream query layer can handle fuzz.

### Decision C: Residence sub-location parens
For entries like `"Shells Town(153rd Branch) (former)"`:
- Option 1: Strip sub-location, store just `"Shells Town"` — loses granularity
- Option 2: Use sub-location as the canonical name `"153rd Branch"` — more specific but inconsistent
- Option 3: Store as two nodes: `(:Location {name:"Shells Town"})-[:CONTAINS]->(:Location {name:"153rd Branch"})` — rich but complex

---

## 6. Summary Recommendation (for Stage 2 discussion)

| Scope | Recommended | Rationale |
|---|---|---|
| `:Occupation` nodes | Yes | 84% coverage, mostly clean after skipping fused tokens |
| `:BORN_IN` from Origin | Yes, leaf-only | 38% coverage is worth it; sea-level can be a property |
| `:RESIDES_IN` from Residence | Yes, skip fused entries | 4.4% fusion rate is manageable by skipping |
| Sub-location parens (Residence) | Strip to parent name | Simpler; sub-locations are not consistently present |
| Fused occupation tokens | Skip, flag in log | Avoids creating 260 garbage nodes; log slugs for future fix |
| `LOCATED_IN` (location hierarchy) | Defer | No source data for relationships between locations |

**Estimated usable data after conservative approach:**
- Occupations: ~1,016 chars cleanly importable (1,276 − 260 fused)
- BORN_IN: ~576 chars
- RESIDES_IN: ~670 chars (701 − 31 fused entries)
