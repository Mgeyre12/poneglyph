# Missing Characters Investigation
# Week 6 · Stage 1 (pre-work)
# Investigated: 2026-04-21

## Method

Compared `source_name` slugs in Kareem's raw output (`characters_raw.json`, 1,517 records)
against `opwikiID` values in the live Neo4j graph (all `:Character` nodes).

## Result

**No missing characters.** Both sets contain exactly 1,517 slugs with 100% overlap.

- Raw scraped: 1,517
- In graph: 1,517
- In raw but not graph: **0**
- In graph but not raw: **0**

## Implication for Stage 6 detection script

The "previously missed" bucket in `detect_new_content.py` can be dropped — any character
that exists on the wiki but not in the graph is genuinely new, not a prior scrape miss.
The Week 1 analysis that flagged ~56 missing was incorrect.
