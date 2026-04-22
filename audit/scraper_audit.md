# Kareem's Scraper Audit
# Week 6 · Stage 1

Audited file: `one_piece/.../scraper/src/onepiece_scraper.py` (851 lines)
Audited: 2026-04-21

---

## 1. Structure

**Verdict: Clean.**

Single `OnePieceScraper` class with a clear responsibility boundary:
- `_fetch_*` — HTTP layer (requests or Selenium)
- `_extract_*` — HTML/wikitext parsing
- `scrape_multiple` / `scrape_devil_fruits_api` — orchestration loop
- `discover_*` — wiki list discovery
- `_load_progress` / `_save_batch` / `_consolidate_batches` — checkpoint/resume

No global state. Clean separation of concerns. The class is long but not tangled — each method does one thing. This is above-average quality for a solo scraper project.

---

## 2. Code Quality Checks

### Error handling
Good but uneven:
- `_fetch_with_requests`: 3 retries with exponential backoff (2s, 4s, 6s). Bot detection check: `content < 5000 bytes` or `"Client Challenge"` in response.
- `_fetch_with_selenium`: **No retry.** Single try/catch. If Selenium fails once, the character is skipped. Inconsistency.
- Network failures in the main loop → logs `"❌ Failed"` and moves on. Doesn't distinguish timeout vs. 404 vs. bot block.
- No explicit handling of HTTP 429 (rate limited) or 503 (wiki down). Both would get retried with the generic backoff, which is fine in practice.

### Rate limiting
Respected. `time.sleep(delay)` is called inside `scrape_multiple` after every fetch. Default delay = 3s for characters, 1s for devil fruits. No accidental double-dipping or skipping. The delay is skipped after the last item in the batch (intentional, correct).

### User-Agent
**Present.** Contradicts the Week 1 analysis that flagged this as missing. The header is:
```
Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ...
```
Set on `self.session` (requests) and also passed as a Selenium arg. Week 1 note was wrong.

### Selenium fallback
Optional — guarded by try/except import. Gracefully degrades to requests if selenium/webdriver-manager aren't installed. The anti-detection setup is solid (disable webdriver flag, no-sandbox, window size spoofing). Main gap: no retry in `_fetch_with_selenium`.

### Logging
Stdout only — emoji-heavy progress output (good for interactive runs). Failures saved to `output/scraping_failures.json`. No file-based logging, no per-record timestamps, no structured log format. If a run fails at 3am you have no persistent log to read.

### Idempotency / Resume
**Good.** `_load_progress()` reads all existing batch files + the consolidated file and builds a set of already-scraped `source_name` slugs. `to_scrape` is filtered against this set. Interrupted run = pick up where you left off.

---

## 3. Correctness Checks

### Bug 1 — Height parsing ("91" for Luffy)
**Present and understood.** Not a scraper bug — a parser bug in the import step.

The wiki infobox stores all height variants as one concatenated string:
```
"91 cm (3') (debut, child)[6]172 cm (5'8") (pre-timeskip)[15]174 cm (5'9") (post-timeskip)"
```

The scraper does `value.get_text(strip=True)` which captures all three values as a single raw string. My `import_characters.py` then tried to extract a number from this and grabbed the first one (91). The scraper faithfully returned the raw string — the parse bug is downstream.

**Fix location:** `import_characters.py` height parser — take the last height value, not the first. Already patched in the graph via `fix_data_bugs.py`.

### Bug 2 — Voice actor URI parsing
**Confirmed not present as described.** The scraper uses `get_text()` everywhere — it extracts the text content of links, not their href. So voice actor names come through correctly, but if you wanted their wiki URLs, they'd be lost. Since we don't use voice actor URLs, this is not a live bug for Poneglyph.

### Bug 3 — ~56 missing characters
**Likely still present.** `discover_canon_characters()` scrapes `List_of_Canon_Characters`, looks for a `sortable` table, and extracts wiki slugs from the second cell of each row. If the list page structure changed, or some characters appear in alternate sections (non-table format), they'd be silently skipped. No validation against expected counts. This is the probable source of the gap — not fixable without knowing which 56 are missing.

### Additional data quality observations
Spot-checked 3 records from `characters_raw.json`:

**Luffy** — `Height` field: raw string contains all three heights concatenated. All other fields look correct. `Affiliations` semicolon-delimited, `Debut` has citation tags fused in (`"Chapter 1;[1]Episode 1[2]"`).

**Ace** — Fields look correct. Debut chapter present.

**Zoro** — Fields present, citation tags fused into some values. Expected.

**Pattern across all records:** Citation tags like `[1]`, `[2]`, `[11]` are consistently fused into field values — the wiki renders them as superscripts but `get_text()` captures them inline. My `import_characters.py` already strips these. Not a new issue.

---

## 4. Diff-Friendliness Checks

This is the critical section for Week 6.

| Check | Status | Notes |
|---|---|---|
| Stable ID per record | ✅ | `source_name` = wiki URL slug (e.g. `Monkey_D._Luffy`). Stable across runs. |
| Output format | ❌ | One giant JSON file (`output/characters.json`) with all 1,517 records. Not per-character. Diffing requires loading both files fully into memory and comparing. |
| Per-record `scraped_at` timestamp | ❌ | Timestamp is on the envelope (`data.scraped_at`), not on each character record. Can't tell when a specific character was last fetched. |
| Content hash per record | ❌ | Not present. No way to detect changes without field-by-field comparison. |
| Deletion detection | ❌ | No mechanism. A character removed from the wiki list just won't appear in the new scrape. No tombstone, no flag. |
| Resume/idempotency | ✅ | Batch checkpointing works well. |
| One stable run target | ⚠️ | Output file path is relative (`output/characters.json`) — no date-stamped snapshot directory. Re-running overwrites the previous output. |

---

## 5. Verdict

**ENHANCE**

The scraper is production-quality for what it was built to do: a one-time batch scrape with resume support. It is not designed for recurring diffs. The code quality is good enough that a rewrite would be waste — but 4 specific gaps block the Week 6 pipeline and are straightforward to fix.

### Changes needed (ranked by effort and value)

| Priority | Change | Effort | Why |
|---|---|---|---|
| 1 | **Per-character file output with `_meta`** | Medium | Core requirement for field-level diffing. Wrap/post-process output into `data/snapshots/YYYY-MM-DD/{opwikiID}.json`. Add `_meta: {scraped_at, wiki_url, content_hash}` per record. |
| 2 | **Date-stamped snapshot directory** | Low | Prevent overwriting previous runs. `data/snapshots/YYYY-MM-DD/` as the output root. |
| 3 | **Per-record `scraped_at` timestamp** | Low | Needed so the diff engine knows the freshness of each record independently. |
| 4 | **Content hash per record** | Low | SHA-256 of the content fields (excluding `_meta`). Enables fast diff without field-by-field comparison. |

**Not changing this week:**
- Height field parsing — already fixed in the graph; the raw string is actually the right thing to store (it's complete data). Fix the import parser, not the scraper.
- Selenium retry gap — low priority since we run with requests.
- Missing-56 characters — need to identify which 56 before fixing the discovery step.

### Implementation plan (Stage 2)

Rather than modifying Kareem's scraper itself, build a thin wrapper `refresh_data.py` that:
1. Calls `scraper.scrape_multiple()` with a temp output dir
2. Post-processes the consolidated JSON into per-character files with `_meta`
3. Writes to `data/snapshots/YYYY-MM-DD/characters/{opwikiID}.json`

This keeps Kareem's code untouched and gives us a clean versioned snapshot format.
