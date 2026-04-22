"""
generate_schema.py
------------------
Introspects the live Neo4j graph and writes graph_schema.md.
Run once (or any time the schema changes) — output is committed to the repo
and used as context for LLM Cypher generation.
"""

import os
from collections import defaultdict
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

OUT_FILE = os.path.join(os.path.dirname(__file__), "..", "graph_schema.md")


def infer_type(value) -> str:
    if value is None:
        return "?"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    return "string"


def collect_label_schema(session) -> dict[str, dict[str, str]]:
    """Return {label: {prop: type}} by sampling up to 50 nodes per label."""
    labels_result = session.run(
        "CALL db.labels() YIELD label RETURN label ORDER BY label"
    )
    labels = [r["label"] for r in labels_result]

    schema = {}
    for label in labels:
        result = session.run(f"MATCH (n:`{label}`) RETURN n LIMIT 50")
        prop_types: dict[str, str] = {}
        for record in result:
            node = record["n"]
            for k, v in dict(node).items():
                if k not in prop_types or prop_types[k] == "?":
                    prop_types[k] = infer_type(v)
        schema[label] = prop_types
    return schema


def collect_rel_schema(session) -> list[dict]:
    """Return list of {type, from_labels, to_labels, props}.
    Enumerates all rel types first, then samples each to avoid LIMIT skew."""
    types_result = session.run(
        "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType"
    )
    rel_types = [r["relationshipType"] for r in types_result]

    rels = []
    for rel_type in rel_types:
        result = session.run(
            f"MATCH (a)-[r:{rel_type}]->(b) RETURN labels(a) AS from_labels, labels(b) AS to_labels, r LIMIT 50"
        )
        seen: dict[tuple, dict[str, str]] = {}
        for record in result:
            from_label = record["from_labels"][0] if record["from_labels"] else "?"
            to_label = record["to_labels"][0] if record["to_labels"] else "?"
            key = (from_label, to_label)
            if key not in seen:
                seen[key] = {}
            for k, v in dict(record["r"]).items():
                if k not in seen[key] or seen[key][k] == "?":
                    seen[key][k] = infer_type(v)
        for (from_label, to_label), props in sorted(seen.items()):
            rels.append(
                {"type": rel_type, "from": from_label, "to": to_label, "props": props}
            )

    return rels


def collect_counts(session) -> dict[str, int]:
    counts = {}
    for label in ["Character", "Organization", "DevilFruit", "Chapter", "Arc"]:
        r = session.run(f"MATCH (n:{label}) RETURN count(n) AS c")
        counts[label] = r.single()["c"]
    for rel in ["AFFILIATED_WITH", "ATE_FRUIT", "DEBUTED_IN", "IN_ARC"]:
        r = session.run(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c")
        counts[rel] = r.single()["c"]
    return counts


# ── markdown generation ───────────────────────────────────────────────────────

EXAMPLE_QUERIES = """
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
"""


def build_markdown(label_schema: dict, rels: list[dict], counts: dict) -> str:
    lines = ["# One Piece Knowledge Graph — Schema Reference\n"]
    lines.append(
        "This schema is used as context for LLM-generated Cypher queries. "
        "All property names are case-sensitive. String matching should use "
        "`toLower()` + `CONTAINS` for fan-typed names.\n"
    )

    # ── counts ────────────────────────────────────────────────────────────────
    lines.append("## Graph statistics\n")
    lines.append("| Label / Relationship | Count |")
    lines.append("|---|---|")
    for k, v in counts.items():
        lines.append(f"| `{k}` | {v:,} |")
    lines.append("")

    # ── node labels ───────────────────────────────────────────────────────────
    lines.append("## Node labels\n")
    for label, props in sorted(label_schema.items()):
        prop_str = ", ".join(f"`{k}`: {t}" for k, t in sorted(props.items()))
        lines.append(f"### `{label}`\n")
        lines.append(f"Properties: {prop_str}\n")

        # Annotate key properties inline for the most important labels
        if label == "Character":
            lines.append(
                "- `opwikiID` — stable unique key (wiki URL slug, e.g. `Monkey_D._Luffy`)\n"
                "- `name` — canonical English display name\n"
                "- `status` — `Alive` | `Deceased` | `Unknown`\n"
                "- `age` — post-timeskip age (integer)\n"
                "- `height_cm` — height in cm (float; some values are incorrect due to upstream scraping)\n"
                "- `epithet` — e.g. `Straw Hat Luffy`\n"
                "- `debutChapter` — chapter number of first appearance (integer)\n"
                "- `bloodType`, `birthday` — strings\n"
                "- `name_ja`, `name_romanized` — Japanese and romanized name aliases\n"
            )
        elif label == "Organization":
            lines.append(
                "- `org_id` — stable unique key (normalized: lowercase, spaces→underscores)\n"
                "- `name` — display name (e.g. `Straw Hat Pirates`, `Marines`)\n"
            )
        elif label == "DevilFruit":
            lines.append(
                "- `fruit_id` — stable unique key (wiki slug, e.g. `Gomu_Gomu_no_Mi`)\n"
                "- `name` — canonical name (e.g. `Hito Hito no Mi, Model: Nika`)\n"
                "- `type` — `Paramecia` | `Zoan` | `Logia`\n"
                "- `japanese_name`, `meaning` — source data fields\n"
                "- `debut_chapter` — chapter number (integer)\n"
            )
        elif label == "Chapter":
            lines.append(
                "- `number` — chapter number (integer), unique key\n"
                "- NOTE: only chapters that are a character debut chapter exist as nodes (515 nodes).\n"
                "  Not every manga chapter has a node.\n"
            )
        elif label == "Arc":
            lines.append(
                "- `arc_order` — stable integer key (1 = Romance Dawn, 33 = Elbaf)\n"
                "- `name` — arc display name\n"
                "- `saga` — parent saga (e.g. `East Blue Saga`, `Final Saga`)\n"
                "- `start_chapter`, `end_chapter` — chapter range (end is 9999 for ongoing Elbaf Arc)\n"
            )

    # ── relationships ─────────────────────────────────────────────────────────
    lines.append("## Relationships\n")
    for rel in rels:
        prop_str = (
            " { "
            + ", ".join(f"`{k}`: {t}" for k, t in sorted(rel["props"].items()))
            + " }"
            if rel["props"]
            else ""
        )
        lines.append(f"- `(:{rel['from']})-[:{rel['type']}{prop_str}]->(:{rel['to']})`")

    lines.append("")
    lines.append("### Relationship notes\n")
    lines.append(
        "- `:AFFILIATED_WITH` — `status`: `current` | `former` | `defected` | `disbanded` | "
        "`temporary` | `semi-retired` | `descended` | *(other raw annotation)*. "
        "`status_raw` stores the original unprocessed annotation string.\n"
        "- `:ATE_FRUIT` — `status`: `current` | `former`. Multi-user fruits (e.g. Gura Gura no Mi) "
        "have two relationships: Whitebeard (`former`) and Blackbeard (`current`).\n"
        "- `:DEBUTED_IN` — no properties. Links character to their debut chapter node.\n"
        "- `:IN_ARC` — no properties. Links a chapter node to its arc.\n"
    )

    lines.append(EXAMPLE_QUERIES)

    lines.append("## Important query notes\n")
    lines.append(
        "1. **Always use `toLower()` + `CONTAINS` for name matching** — fans type `luffy`, not `Monkey D. Luffy`.\n"
        "2. **Character → Arc path**: `(Character)-[:DEBUTED_IN]->(Chapter)-[:IN_ARC]->(Arc)` — "
        "there is no direct Character→Arc relationship.\n"
        '3. **Only debut chapters exist** as `:Chapter` nodes. You cannot query "what happened in chapter X" '
        "unless it is a character's debut chapter.\n"
        "4. **Devil fruit type** is on the `:DevilFruit` node, not on the relationship.\n"
        "5. **Organization lookup**: prefer matching on `o.name` with `CONTAINS` rather than exact match.\n"
        "6. **Arc lookup**: use `a.name` with `CONTAINS` or `a.arc_order` for precise arc targeting.\n"
    )

    return "\n".join(lines)


# ── main ──────────────────────────────────────────────────────────────────────


def main():
    print(f"Connecting to Neo4j at {NEO4J_URI}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print("Connected.\n")

    with driver.session() as session:
        print("Collecting node label schema...")
        label_schema = collect_label_schema(session)

        print("Collecting relationship schema...")
        rels = collect_rel_schema(session)

        print("Collecting counts...")
        counts = collect_counts(session)

    driver.close()

    print("\nBuilding markdown...")
    md = build_markdown(label_schema, rels, counts)

    with open(OUT_FILE, "w") as f:
        f.write(md)

    print(f"Written to {OUT_FILE}")
    print(f"\nLabels found: {sorted(label_schema.keys())}")
    print(f"Relationships found: {sorted(set(r['type'] for r in rels))}")


if __name__ == "__main__":
    main()
