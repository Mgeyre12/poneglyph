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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from utils.neo4j_env import get_neo4j_config

NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, _ = get_neo4j_config()

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
        timeout=60.0,
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

## Conversation context

If a "Recent conversation" block is present in the user message, the current question may use \
pronouns ("them", "they", "him", "her", "it") or definite references ("the crew", "that fight", \
"those characters") that depend on the prior turns. Resolve those references against the recent \
turns before generating Cypher — treat the question as if the user had asked it explicitly with \
the resolved entity in place.

If a reference is genuinely ambiguous after consulting history, generate Cypher for the most \
likely interpretation. Never write Cypher that literally matches the pronoun string \
(e.g. `CONTAINS "them"`).

If no history is provided and the question is unresolvable on its own (e.g. just "name them"), \
still emit a single read-only Cypher query that returns zero rows — for example \
`MATCH (c:Character) WHERE false RETURN c.name`. Do NOT emit prose, hedging, or explanations. \
The answer step will report the empty result honestly. Rule 1 (raw Cypher only) always wins.

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
10. Location queries: use :BORN_IN for birthplace/origin, :RESIDES_IN for where they live. \
BORN_IN coverage is ~38% of characters; use OPTIONAL MATCH when origin may be absent. \
A character can have multiple BORN_IN edges (sea + specific location). \
:LOCATED_IN connects specific locations to their sea (67 edges, one hop only).
11. Occupation queries: use :HAS_OCCUPATION. Coverage is 84%. Status is current|former|temporary. \
Occupation names may be imperfect (some camelCase fusions remain) — use CONTAINS matching.
12. Five Elders: the "Five Elders" org has exactly 5 members (Saturn, Mars, Nusjuro, Ju Peter, Warcury). \
Garling Figarland is NOT one of the Five — he is Supreme Commander of the Holy Knights (org: "Knights of God"). \
If asked "who are the Five Elders", return only the 5 canonical members.
13. Kaku disambiguation: two characters share the name "Kaku" (debut Ch 323 and Ch 927). \
If a Kaku query returns 2 rows, describe both and note the ambiguity explicitly.
14. Aggregation ORDER BY: when RETURN contains an aggregation (count, collect, sum, avg), \
ORDER BY may only reference aliases defined in that RETURN clause. \
Wrong: RETURN a.name, count(c) ORDER BY a.arc_order \
Right: RETURN a.name, a.arc_order, count(c) AS n ORDER BY n DESC

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

Q: Where is Luffy from?
A:
MATCH (c:Character)-[:BORN_IN]->(l:Location)
WHERE toLower(c.name) CONTAINS toLower("luffy")
   OR toLower(c.opwikiID) CONTAINS toLower("luffy")
RETURN c.name, collect(l.name) AS born_in

Q: Where does Zoro live?
A:
MATCH (c:Character)-[r:RESIDES_IN]->(l:Location)
WHERE toLower(c.name) CONTAINS toLower("zoro")
   OR toLower(c.opwikiID) CONTAINS toLower("zoro")
RETURN c.name, l.name AS location, r.status
ORDER BY r.status

Q: Who are all the characters from East Blue?
A:
MATCH (c:Character)-[:BORN_IN]->(l:Location)
WHERE toLower(l.name) CONTAINS toLower("east blue")
RETURN c.name, c.status, l.name AS birthplace
ORDER BY c.name

Q: What does Nami do?
A:
MATCH (c:Character)-[r:HAS_OCCUPATION]->(o:Occupation)
WHERE toLower(c.name) CONTAINS toLower("nami")
   OR toLower(c.opwikiID) CONTAINS toLower("nami")
RETURN c.name, o.name AS occupation, r.status
ORDER BY r.status, o.name

Q: How many current Pirate Captains are in the graph?
A:
MATCH (c:Character)-[r:HAS_OCCUPATION]->(o:Occupation)
WHERE toLower(o.name) CONTAINS toLower("pirate captain")
  AND r.status = "current"
RETURN count(c) AS pirate_captain_count

## Few-shot examples — with conversation history

Recent conversation:
  user: how many in the straw hat crew?
  assistant: My crew, the Straw Hat Pirates, has 10 members.
Q: name them
A:
MATCH (c:Character)-[r:AFFILIATED_WITH]->(o:Organization)
WHERE toLower(o.name) CONTAINS toLower("straw hat pirates")
  AND r.status = "current"
RETURN c.name, c.epithet, c.debutChapter AS debut_chapter
ORDER BY c.debutChapter

Recent conversation:
  user: who are the four emperors?
  assistant: The current Yonko are Luffy, Shanks, Buggy, and Blackbeard.
Q: which of them have devil fruits
A:
MATCH (c:Character)
WHERE toLower(c.name) CONTAINS toLower("luffy")
   OR toLower(c.name) CONTAINS toLower("shanks")
   OR toLower(c.name) CONTAINS toLower("buggy")
   OR toLower(c.name) CONTAINS toLower("blackbeard")
   OR toLower(c.name) CONTAINS toLower("teach")
OPTIONAL MATCH (c)-[r:ATE_FRUIT]->(f:DevilFruit)
RETURN c.name, f.name AS fruit, f.type AS fruit_type, r.status AS ownership
"""

ANSWER_SYSTEM_PROMPT = """\
You are Nico Robin, archaeologist of the Straw Hat Pirates. You are answering a fan's \
question, drawing only on the records the graph has surfaced below.

Voice:
- Speak in the FIRST PERSON about yourself. "I ate the Hana-Hana Fruit." "I was born \
on Ohara." "I joined my crew in [[Ch.114|...]]." Never "Nico Robin is...", never "she".
- Use POSSESSIVE for the Straw Hats: "my crew", "my captain" (Luffy), "my navigator" \
(Nami), "my swordsman" (Zoro), "my sniper" (Usopp), "my cook" (Sanji), "my doctor" \
(Chopper), "my shipwright" (Franky), "my musician" (Brook), "my helmsman" (Jinbe). \
"The Straw Hats" or "my crew" for the group.
- Everyone else stays in the third person. No "my" for enemies, rivals, or outsiders.
- Tone: calm, scholarly, quietly amused. A touch of dark humor when it fits. Never bubbly, \
never breathless.

Rules:
1. Only use information present in the results below. Do not add facts from training data, \
even about yourself or my crew.
2. If results are empty, say so honestly in character: "The records are silent on that."
3. If the question asks about something the graph doesn't track (Haki, abilities, bounties), \
say so explicitly: "These records don't yet contain [X] data."
4. Cite chapters with inline tokens `[[Ch.NNN|Arc Name]]`, placed after the claim they \
support. Use the "Chapter → Arc" lookup at the end of the user message. Skip any chapter \
not in the lookup — do not invent an arc or write "(debut: Chapter N)". \
Example: "Nami joined my crew in [[Ch.69|Arlong Park Arc]]."
5. No preamble. No "based on the knowledge graph...". Just answer.
6. For long lists (>10 items), summarize intelligently — don't dump every row.
7. Always name the entity you are talking about, even in short answers. A reader picking \
up your reply mid-conversation should know who or what it concerns. \
Wrong: "There are 11." \
Right: "My crew, the Straw Hat Pirates, has 11 members."
8. If a "Recent conversation" block is present, you are continuing that conversation. The \
reader remembers what was just said — don't restart from scratch or repeat their question \
back. Reference prior turns naturally when relevant. If the current question uses a pronoun \
or definite reference resolved from history, surface the resolved entity in your answer so \
the next follow-up has an anchor.

## Few-shot example — conversational continuity

Recent conversation:
  user: how many in the straw hat crew?
  assistant: My crew, the Straw Hat Pirates, has 10 members.
Question: name them
[results: 10 rows of crew members]
Answer:
The Straw Hats, in order of joining: my captain Luffy, then Zoro, Nami, Usopp, Sanji, \
Chopper, myself, Franky, Brook, and most recently Jinbe. Luffy founded the crew in \
[[Ch.1|Romance Dawn Arc]].
"""


def _format_history_block(history: list[dict] | None) -> str:
    """Render the recent-conversation block injected into both prompts.

    Returns "" when history is empty so prompts pass through unchanged for the
    stateless path. Each turn is rendered on its own indented line.
    """
    if not history:
        return ""
    lines = ["Recent conversation:"]
    for turn in history:
        role = turn.get("role", "")
        content = (turn.get("content") or "").strip()
        if not content or role not in ("user", "assistant"):
            continue
        lines.append(f"  {role}: {content}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def question_to_cypher(
    client: anthropic.Anthropic,
    question: str,
    schema: str,
    history: list[dict] | None = None,
) -> str:
    system = CYPHER_SYSTEM_PROMPT.format(schema=schema)
    history_block = _format_history_block(history)
    user = f"{history_block}\n\nQ: {question}" if history_block else question
    return call_claude(client, system, user)


CHAPTER_KEY_RE = re.compile(r"chapter|number", re.IGNORECASE)


def build_arc_map(results: list[dict], run_cypher_fn=None) -> dict[int, str]:
    """Resolve chapter numbers present in ``results`` to their arc names.

    Returns ``{chapter_number: arc_name}``. Chapters without an :IN_ARC edge
    (currently only Chapter 0 in the graph) are SKIPPED — we don't fall back to
    "Unknown Arc" because a dangling citation pill is worse than no pill.
    Callers must be prepared for a chapter to be absent from the map.

    ``run_cypher_fn`` lets the API layer inject its Aura-configured runner; the
    CLI and stress test default to this module's ``run_cypher``.
    """
    if run_cypher_fn is None:
        run_cypher_fn = run_cypher

    numbers: set[int] = set()
    for row in results:
        for k, v in row.items():
            if isinstance(v, int) and CHAPTER_KEY_RE.search(k):
                numbers.add(v)

    if not numbers:
        return {}

    sorted_nums = sorted(numbers)
    cypher = (
        f"MATCH (ch:Chapter)-[:IN_ARC]->(a:Arc) "
        f"WHERE ch.number IN {sorted_nums} "
        f"RETURN ch.number AS number, a.name AS arc"
    )
    try:
        rows = run_cypher_fn(cypher)
    except Exception:
        return {}
    return {row["number"]: row["arc"] for row in rows if row.get("arc")}


def results_to_answer(
    client: anthropic.Anthropic,
    question: str,
    cypher: str,
    results: list[dict],
    arc_map: dict[int, str] | None = None,
    history: list[dict] | None = None,
) -> str:
    user_prompt = _build_answer_user_prompt(question, cypher, results, arc_map, history)
    return call_claude(client, ANSWER_SYSTEM_PROMPT, user_prompt)


def _build_answer_user_prompt(
    question: str,
    cypher: str,
    results: list[dict],
    arc_map: dict[int, str] | None,
    history: list[dict] | None = None,
) -> str:
    arc_section = _format_arc_lookup(arc_map)
    history_block = _format_history_block(history)
    history_section = f"{history_block}\n\n" if history_block else ""
    return (
        f"{history_section}"
        f"Question: {question}\n\n"
        f"Cypher query that ran:\n{cypher}\n\n"
        f"Results ({len(results)} rows):\n"
        f"{json.dumps(results, indent=2, default=str)}\n\n"
        f"{arc_section}"
    )


def _format_arc_lookup(arc_map: dict[int, str] | None) -> str:
    header = "Chapter → Arc lookup (for `[[Ch.NNN|Arc Name]]` citations):"
    if not arc_map:
        return header + "\n(empty — omit all citations)"
    by_arc: dict[str, list[int]] = {}
    for num, arc in arc_map.items():
        by_arc.setdefault(arc, []).append(num)
    lines = [
        f"  {arc}: {', '.join(str(n) for n in sorted(nums))}"
        for arc, nums in sorted(by_arc.items())
    ]
    return header + "\n" + "\n".join(lines)


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

    # Step 4: resolve chapter→arc for inline citation tokens
    arc_map = build_arc_map(results)
    if debug and arc_map:
        print(f"Arc map: {arc_map}\n")

    # Step 5: generate answer
    answer = results_to_answer(client, question, cypher, results, arc_map=arc_map)
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
