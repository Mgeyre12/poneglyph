# One Piece Knowledge Graph — Schema Reference

This schema is used as context for LLM-generated Cypher queries. All property names are case-sensitive. String matching should use `toLower()` + `CONTAINS` for fan-typed names.

## Graph statistics

| Label / Relationship | Count |
|---|---|
| `Character` | 1,526 |
| `Organization` | 362 |
| `DevilFruit` | 134 |
| `Chapter` | 534 |
| `Arc` | 33 |
| `Location` | 247 |
| `Occupation` | 661 |
| `AFFILIATED_WITH` | 1,932 |
| `ATE_FRUIT` | 143 |
| `DEBUTED_IN` | 1,480 |
| `IN_ARC` | 533 |
| `BORN_IN` | 940 |
| `RESIDES_IN` | 849 |
| `LOCATED_IN` | 67 |
| `HAS_OCCUPATION` | 2,050 |

## Node labels

### `Arc`

Properties: `arc_order`: integer, `end_chapter`: integer, `name`: string, `saga`: string, `start_chapter`: integer

- `arc_order` — stable integer key (1 = Romance Dawn, 33 = Elbaf)
- `name` — arc display name
- `saga` — parent saga (e.g. `East Blue Saga`, `Final Saga`)
- `start_chapter`, `end_chapter` — chapter range (end is 9999 for ongoing Elbaf Arc)

### `Chapter`

Properties: `number`: integer

- `number` — chapter number (integer), unique key
- NOTE: only chapters that are a character debut chapter exist as nodes (515 nodes).
  Not every manga chapter has a node.

### `Character`

Properties: `age`: integer, `birthday`: string, `bloodType`: string, `debutChapter`: integer, `debutEpisode`: integer, `epithet`: string, `height_cm`: float, `name`: string, `nameJapanese`: string, `nameRomanized`: string, `opwikiID`: string, `opwikiURL`: string, `status`: string

- `opwikiID` — stable unique key (wiki URL slug, e.g. `Monkey_D._Luffy`)
- `name` — canonical English display name
- `status` — `Alive` | `Deceased` | `Unknown`
- `age` — post-timeskip age (integer)
- `height_cm` — height in cm (float; some values are incorrect due to upstream scraping)
- `epithet` — e.g. `Straw Hat Luffy`
- `debutChapter` — chapter number of first appearance (integer)
- `bloodType`, `birthday` — strings
- `nameJapanese`, `nameRomanized` — Japanese and romanized name aliases (alternate property names)

### `DevilFruit`

Properties: `debut_chapter`: integer, `fruit_id`: string, `japanese_name`: string, `meaning`: string, `name`: string, `type`: string

- `fruit_id` — stable unique key (wiki slug, e.g. `Gomu_Gomu_no_Mi`, `Ope_Ope_no_Mi`). Underscores replace spaces. This is the closest field to the Japanese romanized name.
- `name` — **English canonical name** as imported (e.g. `Op-Op Fruit`, `Flame-Flame Fruit (VIZ, Funimation dub)`, `Tremor-Tremor Fruit or Quake-Quake Fruit`). Fans often know the Japanese name; the graph stores the English name. **Always search both `f.name` and `f.fruit_id` when looking up a fruit.**
- `type` — `Paramecia` | `Zoan` | `Logia`
- `japanese_name` — katakana (e.g. `オペオペの実`)
- `meaning`, `debut_chapter` — source data fields

### `Location`

Properties: `slug`: string, `name`: string

- `slug` — stable unique key (lowercase, underscored, e.g. `east_blue`, `foosha_village`)
- `name` — display name as it appears in the wiki data

Coverage: 247 nodes. Origins come from the `Origin` field (38% of characters); residences from `Residence` (46%). Coverage is sparse for minor characters.

### `Occupation`

Properties: `slug`: string, `name`: string

- `slug` — stable unique key (lowercase, underscored, e.g. `pirate_captain`, `marine_officer`)
- `name` — display name after camelCase normalization (e.g. `Pirate Officer`, not `PirateOfficer`)

Coverage: 661 unique occupations, 84% of characters have at least one. ~20% of entries were camelCase-fused in the source (e.g. `PirateOfficer`) and were split automatically; edge cases are logged in `logs/occupation_splits.log` for hand-patching.

### `Organization`

Properties: `name`: string, `org_id`: string

- `org_id` — stable unique key (normalized: lowercase, spaces→underscores)
- `name` — display name (e.g. `Straw Hat Pirates`, `Marines`)

## Relationships

- `(:Character)-[:AFFILIATED_WITH { org_id: string, status: string, status_raw: string }]->(:Organization)`
- `(:Character)-[:ATE_FRUIT { fruit_id: string, status: string }]->(:DevilFruit)`
- `(:Character)-[:DEBUTED_IN]->(:Chapter)`
- `(:Chapter)-[:IN_ARC]->(:Arc)`
- `(:Character)-[:BORN_IN]->(:Location)`
- `(:Character)-[:RESIDES_IN { status: string }]->(:Location)`
- `(:Location)-[:LOCATED_IN]->(:Location)`
- `(:Character)-[:HAS_OCCUPATION { status: string }]->(:Occupation)`

### Relationship notes

- `:AFFILIATED_WITH` — `status`: `current` | `former` | `defected` | `disbanded` | `temporary` | `semi-retired` | `descended` | *(other raw annotation)*. `status_raw` stores the original unprocessed annotation string.
- `:ATE_FRUIT` — `status`: `current` | `former`. Multi-user fruits (e.g. Gura Gura no Mi) have two relationships: Whitebeard (`former`) and Blackbeard (`current`).
- `:DEBUTED_IN` — no properties. Links character to their debut chapter node.
- `:IN_ARC` — no properties. Links a chapter node to its arc.
- `:BORN_IN` — no properties. A character may have multiple BORN_IN edges: one to the sea (e.g. East Blue) and one to the specific location (e.g. Foosha Village). Fish-Man Island characters have three: Grand Line + Ryugu Kingdom + Fish-Man Island.
- `:RESIDES_IN` — `status`: `current` | `former` | `temporary`. A character can have multiple RESIDES_IN edges with different statuses.
- `:LOCATED_IN` — no properties. Hierarchy sourced only from explicit parenthetical in the wiki Origin field (e.g. `East Blue(Foosha Village)`). 67 edges total. Not inferred — only stated.
- `:HAS_OCCUPATION` — `status`: `current` | `former` | `temporary`. Multiple occupations per character are common.


## Example Cypher patterns

### Find all members of an organization (case-insensitive partial match)
```cypher
MATCH (c:Character)-[r:AFFILIATED_WITH]->(o:Organization)
WHERE toLower(o.name) CONTAINS toLower("straw hat")
RETURN c.name, c.status, r.status AS affiliation_status, o.name AS org
ORDER BY c.name
```

### Find all characters who ate a devil fruit, with fruit details
```cypher
MATCH (c:Character)-[r:ATE_FRUIT]->(f:DevilFruit)
RETURN c.name, f.name AS fruit, f.type AS fruit_type, r.status AS ownership
ORDER BY f.type, c.name
```

### Find characters who debuted in a specific arc
```cypher
MATCH (c:Character)-[:DEBUTED_IN]->(ch:Chapter)-[:IN_ARC]->(a:Arc)
WHERE toLower(a.name) CONTAINS toLower("wano")
RETURN c.name, ch.number AS debut_chapter, a.name AS arc
ORDER BY ch.number, c.name
```

### Find characters affiliated with two organizations simultaneously
```cypher
MATCH (c:Character)-[:AFFILIATED_WITH]->(o1:Organization)
MATCH (c)-[:AFFILIATED_WITH]->(o2:Organization)
WHERE toLower(o1.name) CONTAINS toLower("marines")
  AND toLower(o2.name) CONTAINS toLower("warlord")
RETURN c.name, o1.name, o2.name
```

### Count character debuts per arc (sorted by debut count)
```cypher
MATCH (c:Character)-[:DEBUTED_IN]->(ch:Chapter)-[:IN_ARC]->(a:Arc)
RETURN a.name AS arc, a.arc_order, count(c) AS debut_count
ORDER BY debut_count DESC
```

### Look up a specific character with all relationships
```cypher
MATCH (c:Character)
WHERE toLower(c.name) CONTAINS toLower("luffy")
   OR toLower(c.opwikiID) CONTAINS toLower("luffy")
OPTIONAL MATCH (c)-[af:AFFILIATED_WITH]->(o:Organization)
OPTIONAL MATCH (c)-[df:ATE_FRUIT]->(f:DevilFruit)
OPTIONAL MATCH (c)-[:DEBUTED_IN]->(ch:Chapter)-[:IN_ARC]->(a:Arc)
RETURN c.name, c.status, c.age, c.epithet,
       collect(DISTINCT {org: o.name, status: af.status}) AS affiliations,
       collect(DISTINCT {fruit: f.name, type: f.type, ownership: df.status}) AS devil_fruits,
       ch.number AS debut_chapter, a.name AS debut_arc
```

### Find where a character is from (origin)
```cypher
MATCH (c:Character)-[:BORN_IN]->(l:Location)
WHERE toLower(c.name) CONTAINS toLower("luffy")
   OR toLower(c.opwikiID) CONTAINS toLower("luffy")
RETURN c.name, collect(l.name) AS born_in
```

### Find all characters from a specific location (including sea-level)
```cypher
MATCH (c:Character)-[:BORN_IN]->(l:Location)
WHERE toLower(l.name) CONTAINS toLower("east blue")
RETURN c.name, c.status, l.name AS location
ORDER BY c.name
```

### Find characters born somewhere inside a sea (via LOCATED_IN)
```cypher
MATCH (specific:Location)-[:LOCATED_IN]->(sea:Location)
WHERE toLower(sea.name) CONTAINS toLower("east blue")
MATCH (c:Character)-[:BORN_IN]->(specific)
RETURN c.name, specific.name AS birthplace, sea.name AS sea
ORDER BY c.name
```

### Find where a character lives / has lived
```cypher
MATCH (c:Character)-[r:RESIDES_IN]->(l:Location)
WHERE toLower(c.name) CONTAINS toLower("zoro")
   OR toLower(c.opwikiID) CONTAINS toLower("zoro")
RETURN c.name, l.name AS location, r.status
ORDER BY r.status
```

### Find current residents of a location
```cypher
MATCH (c:Character)-[r:RESIDES_IN]->(l:Location)
WHERE toLower(l.name) CONTAINS toLower("wano")
  AND r.status = "current"
RETURN c.name, c.status, l.name
ORDER BY c.name
```

### Find all occupations of a character
```cypher
MATCH (c:Character)-[r:HAS_OCCUPATION]->(o:Occupation)
WHERE toLower(c.name) CONTAINS toLower("robin")
   OR toLower(c.opwikiID) CONTAINS toLower("robin")
RETURN c.name, o.name AS occupation, r.status
ORDER BY r.status, o.name
```

### Find all characters with a given occupation
```cypher
MATCH (c:Character)-[r:HAS_OCCUPATION]->(o:Occupation)
WHERE toLower(o.name) CONTAINS toLower("pirate captain")
  AND r.status = "current"
RETURN c.name, c.status, o.name AS occupation
ORDER BY c.name
```

## Important query notes

1. **Always use `toLower()` + `CONTAINS` for name matching** — fans type `luffy`, not `Monkey D. Luffy`.
2. **Character → Arc path**: `(Character)-[:DEBUTED_IN]->(Chapter)-[:IN_ARC]->(Arc)` — there is no direct Character→Arc relationship.
3. **Only debut chapters exist** as `:Chapter` nodes. You cannot query "what happened in chapter X" unless it is a character's debut chapter.
4. **Devil fruit type** is on the `:DevilFruit` node, not on the relationship.
5. **Organization lookup**: prefer matching on `o.name` with `CONTAINS` rather than exact match.
6. **Arc lookup**: use `a.name` with `CONTAINS` or `a.arc_order` for precise arc targeting.
7. **BORN_IN is sparse** (38% of characters). Combine with `OPTIONAL MATCH` when origin data may not exist.
8. **HAS_OCCUPATION coverage**: 84% of characters. Use `OPTIONAL MATCH` when occupation may be absent.
9. **Occupation name matching**: fans may say "Marine" or "Pirate" loosely — use `CONTAINS` on `o.name`.
10. **LOCATED_IN hierarchy is shallow** — only 67 edges, all sea→specific. Don't expect multi-hop paths beyond one level.
