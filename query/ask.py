"""
ask.py
------
Natural-language query layer for the One Piece knowledge graph.

Pipeline:
  question → Cypher (Claude) → Neo4j → natural-language answer (Claude)

Usage:
  python ask.py "who are the Straw Hat Pirates?"   # single question
  python ask.py                                      # interactive REPL
"""

import os
import sys
import json
import re

from dotenv import load_dotenv
import anthropic
from neo4j import GraphDatabase

load_dotenv()

# ── config ────────────────────────────────────────────────────────────────────

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Mussa1234"

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024
NEO4J_TIMEOUT = 5  # seconds

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "graph_schema.md")
FAILURE_LOG = os.path.join(os.path.dirname(__file__), "..", "logs", "failure_cases.md")

# ── Claude client ─────────────────────────────────────────────────────────────


def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit(
            "Error: ANTHROPIC_API_KEY environment variable is not set.\n"
            "Add it to a .env file in this directory:\n"
            "  ANTHROPIC_API_KEY=sk-ant-..."
        )
    return anthropic.Anthropic(api_key=api_key)


def call_claude(
    client: anthropic.Anthropic, system_prompt: str, user_prompt: str
) -> str:
    """Single non-streaming Claude call. Returns the text content of the first message."""
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text.strip()


# ── schema loading ────────────────────────────────────────────────────────────


def load_schema() -> str:
    with open(SCHEMA_FILE) as f:
        return f.read()


# ── Stage 3: question → Cypher ────────────────────────────────────────────────

CYPHER_SYSTEM_PROMPT = """\
You are a Cypher query generator for a One Piece knowledge graph stored in Neo4j.

Your job: given a fan's natural-language question, produce a single valid read-only Cypher query \
that retrieves the data needed to answer it.

## Graph schema

{schema}

## Rules

1. Return ONLY the raw Cypher query. No explanations, no markdown code fences, no commentary, \
no "Here is the query:", nothing but the Cypher itself.
2. Read-only queries only. Never use CREATE, MERGE, DELETE, SET, REMOVE, DROP, LOAD CSV, or CALL \
(except CALL db.schema which is safe).
3. Always use toLower() + CONTAINS for name matching — fans type "luffy", not "Monkey D. Luffy". \
Example: WHERE toLower(c.name) CONTAINS toLower("luffy")
4. Return enough context to answer the question. If asking about characters, include their \
affiliations and devil fruit where relevant.
5. If the question requires data the graph doesn't have (e.g. Haki, abilities, bounties, \
full chapter content), write a query that returns whatever IS available and note via a RETURN \
alias like "no_haki_data: 'Haki data not in graph'" — do not hallucinate properties.
6. Use OPTIONAL MATCH for relationships that may not exist (e.g. not every character has a \
devil fruit).
7. Prefer DISTINCT in collect() to avoid duplicates.
8. Devil Fruit name lookup: fans type Japanese romanized names (e.g. "Ope Ope no Mi", \
"Mera Mera no Mi") but the graph stores English names in f.name (e.g. "Op-Op Fruit", \
"Flame-Flame Fruit"). ALWAYS search both fields: \
WHERE toLower(f.name) CONTAINS toLower($term) OR toLower(f.fruit_id) CONTAINS toLower($term_underscored). \
For example, searching "ope ope": toLower(f.name) CONTAINS "ope" OR toLower(f.fruit_id) CONTAINS "ope".
9. Former-affiliation queries: when asked about "former" members of an org, filter \
r.status IN ["former","defected","disbanded","revoked"] AND exclude characters who \
still have a current affiliation with the same org using NOT EXISTS. \
Example: who are former Marines? See few-shot below.

## Few-shot examples

Q: Who are the Straw Hat Pirates?
A:
MATCH (c:Character)-[r:AFFILIATED_WITH]->(o:Organization)
WHERE toLower(o.name) CONTAINS toLower("straw hat pirates")
RETURN c.name, c.status, c.epithet, r.status AS affiliation_status,
       c.debutChapter AS debut_chapter
ORDER BY c.debutChapter

Q: What Devil Fruits are Logia type?
A:
MATCH (c:Character)-[r:ATE_FRUIT]->(f:DevilFruit)
WHERE f.type = "Logia"
RETURN f.name AS fruit, f.meaning, c.name AS user, r.status AS ownership
ORDER BY f.name

Q: Who debuted in the Wano arc?
A:
MATCH (c:Character)-[:DEBUTED_IN]->(ch:Chapter)-[:IN_ARC]->(a:Arc)
WHERE toLower(a.name) CONTAINS toLower("wano")
RETURN c.name, c.status, ch.number AS debut_chapter
ORDER BY ch.number, c.name

Q: Does Luffy have a Devil Fruit?
A:
MATCH (c:Character)
WHERE toLower(c.name) CONTAINS toLower("luffy")
   OR toLower(c.opwikiID) CONTAINS toLower("luffy")
OPTIONAL MATCH (c)-[r:ATE_FRUIT]->(f:DevilFruit)
RETURN c.name, f.name AS fruit, f.type AS fruit_type, r.status AS ownership

Q: What is the Ope Ope no Mi?
A:
MATCH (c:Character)-[r:ATE_FRUIT]->(f:DevilFruit)
WHERE toLower(f.name) CONTAINS toLower("ope")
   OR toLower(f.fruit_id) CONTAINS toLower("ope")
RETURN f.name AS fruit, f.fruit_id, f.type, f.meaning, f.debut_chapter,
       c.name AS user, r.status AS ownership

Q: Who are the former members of the Marines?
A:
MATCH (c:Character)-[r:AFFILIATED_WITH]->(o:Organization)
WHERE toLower(o.name) CONTAINS toLower("marine")
  AND r.status IN ["former", "defected", "disbanded", "revoked"]
  AND NOT EXISTS {{
    MATCH (c)-[r2:AFFILIATED_WITH]->(o2:Organization)
    WHERE toLower(o2.name) CONTAINS toLower("marine")
      AND r2.status = "current"
  }}
RETURN c.name, r.status AS former_status, o.name AS org
ORDER BY c.name
"""

ANSWER_SYSTEM_PROMPT = """\
You are answering a One Piece fan's question using results from a knowledge graph query.

Rules:
1. Only use information present in the results below. Do not add facts from your training data.
2. If results are empty, say so honestly: "The graph doesn't have data to answer this."
3. If the question asks about something the graph doesn't track (e.g. Haki, abilities, bounties), \
say so explicitly: "The graph doesn't yet contain [X] data."
4. When mentioning characters, include their debut chapter as a citation if available in the \
results — format: (debut: Chapter N).
5. Keep the answer conversational and factual. No fluff, no "based on the knowledge graph...", \
no preamble. Just answer.
6. For long lists (>10 items), summarize intelligently — don't dump every row.
"""


def question_to_cypher(client: anthropic.Anthropic, question: str, schema: str) -> str:
    system = CYPHER_SYSTEM_PROMPT.format(schema=schema)
    return call_claude(client, system, question)


def results_to_answer(
    client: anthropic.Anthropic,
    question: str,
    cypher: str,
    results: list[dict],
) -> str:
    user_prompt = f"""Question: {question}

Cypher query that ran:
{cypher}

Results ({len(results)} rows):
{json.dumps(results, indent=2, default=str)}
"""
    return call_claude(client, ANSWER_SYSTEM_PROMPT, user_prompt)


# ── Stage 4: Cypher validation + execution ────────────────────────────────────

DESTRUCTIVE = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|LOAD)\b",
    re.IGNORECASE,
)
SAFE_CALL = re.compile(r"\bCALL\s+db\.", re.IGNORECASE)
UNSAFE_CALL = re.compile(r"\bCALL\b", re.IGNORECASE)


def validate_cypher(cypher: str) -> tuple[bool, str]:
    """Returns (is_valid, reason). Rejects destructive or unsafe queries."""
    if DESTRUCTIVE.search(cypher):
        match = DESTRUCTIVE.search(cypher)
        return False, f"Rejected: contains destructive keyword '{match.group()}'"
    # Allow CALL db.* but reject any other CALL
    for m in UNSAFE_CALL.finditer(cypher):
        start = m.start()
        surrounding = cypher[start : start + 20]
        if not SAFE_CALL.match(surrounding):
            return False, "Rejected: contains CALL (only CALL db.* is allowed)"
    return True, "ok"


def run_cypher(cypher: str) -> list[dict]:
    """Execute Cypher against Neo4j. Returns list of result dicts."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            result = session.run(cypher, timeout=NEO4J_TIMEOUT)
            return [dict(r) for r in result]
    finally:
        driver.close()


def log_failure(question: str, cypher: str, error: str) -> None:
    with open(FAILURE_LOG, "a") as f:
        f.write(f"\n---\n")
        f.write(f"**Question:** {question}\n\n")
        f.write(f"**Generated Cypher:**\n```cypher\n{cypher}\n```\n\n")
        f.write(f"**Error:** {error}\n")


# ── Stage 6: end-to-end pipeline ─────────────────────────────────────────────


def ask(
    question: str, client: anthropic.Anthropic, schema: str, debug: bool = True
) -> None:
    print(f"\nQuestion: {question}")
    print("─" * 60)

    # Step 1: generate Cypher
    cypher = question_to_cypher(client, question, schema)

    if debug:
        print(f"Cypher:\n{cypher}\n")

    # Step 2: validate
    valid, reason = validate_cypher(cypher)
    if not valid:
        print(f"[validation error] {reason}")
        log_failure(question, cypher, reason)
        return

    # Step 3: execute
    try:
        results = run_cypher(cypher)
    except Exception as e:
        msg = str(e)
        print(f"[query error] {msg}")
        log_failure(question, cypher, msg)
        return

    if debug:
        print(f"Results: {len(results)} row(s)\n")

    # Step 4: generate answer
    answer = results_to_answer(client, question, cypher, results)
    print(answer)


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> None:
    client = get_client()
    schema = load_schema()

    if len(sys.argv) > 1:
        # Single question from CLI arg
        question = " ".join(sys.argv[1:])
        ask(question, client, schema)
    else:
        # Interactive REPL
        print("One Piece Knowledge Graph — ask anything. Type 'exit' to quit.\n")
        while True:
            try:
                question = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not question:
                continue
            if question.lower() in {"exit", "quit", "q"}:
                break
            ask(question, client, schema)


if __name__ == "__main__":
    main()
