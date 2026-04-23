# Contributing

Thanks for your interest. Poneglyph is a solo project but contributions are welcome.

## Before opening a pull request

**Open an issue first** for anything non-trivial. A quick alignment on scope saves
everyone time — especially for new features or schema changes.

Bug fixes and documentation improvements can go straight to a PR.

## Local setup

```bash
git clone https://github.com/Mgeyre12/poneglyph
cd poneglyph

pip install -r requirements.txt
pip install -r api/requirements.txt

cp .env.example .env
# Fill in NEO4J_PASSWORD and ANTHROPIC_API_KEY in .env
```

You need Neo4j Desktop running locally (bolt://localhost:7687) with the graph loaded.
See the Quick Start in README.md for the full ingest sequence.

## Running tests

```bash
# 75-question stress test (requires Neo4j + Anthropic API key)
python tests/run_stress_test.py

# Spot-check a single question
python query/ask.py "who are the straw hats?"
```

The stress test makes ~150 Claude API calls and costs roughly $0.10–0.20 per run.

## Code style

- Python 3.11+
- No formatter enforced — match the style of the file you're editing
- No comments that explain what the code does; only comments for non-obvious *why*
- Every ingest/mutation script must default to dry-run; require `--apply` to write

## PR guidelines

- One logical change per PR
- Include a brief description of what changed and why
- If touching the LLM prompts, run the stress test and include the pass rate in the PR description
- Don't bump dependencies unless there's a specific reason

## Code of conduct

Be direct and constructive. No harassment.
