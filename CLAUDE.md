# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A single-page exam-prep app (`Exam-Prep.html`, ~3000 lines: inline `<style>` + two inline `<script>` blocks) for Microsoft/data-management certifications (CDMP, AI-900, DP-300, AZ-104, DP-700). Question banks live in per-exam SQLite files loaded into the browser via `sql.js` (WASM). No build step, no package manager, no test suite — this is plain HTML/JS/Python.

Full architecture and schema documentation lives in `README.md` (in French) — read it before making non-trivial changes; this file only summarizes what's needed to orient quickly.

## Running and developing

```bash
# Regenerate the .js mirrors after editing any exams/*.json or data/**/*.sqlite
python3 bin/sqlite2js.py [--watch] [--clean]

# file:// mode — just open the HTML directly, no server needed (uses the .js mirrors)
xdg-open Exam-Prep.html

# HTTP mode — enables /api/translate, /api/transcript (YouTube), /api/ollama
python3 bin/serve.py [--port 8080] [--host 127.0.0.1] [--cors-origin ORIGIN]

# Docker mode (local container test, python:3.12-slim + yt-dlp, no nginx)
docker build -t exam-prep-local . && docker run --rm -p 8080:8080 exam-prep-local

# Kubernetes (Kind) — from the cnpg-playground deployment repo
ansible-playbook deploy-exam-prep.yml -e ingress_domain=votre-domaine.com
```

There is no lint/build/test command for this repo. Validate changes by opening the app in a browser and exercising the affected flow (picker → lang screen → config screen → exam → results).

Creating/inspecting a question DB by hand:
```bash
sqlite3 data/content/<id>.sqlite < sql/00_full_schema.sql   # full schema in one pass
# or sql/01_questions.sql, sql/02_history.sql, sql/03_translations.sql individually
```

## Architecture

**Two-tier data loading, no CORS dependency in file:// mode.** Every JSON/SQLite asset has a generated `.js` twin (via `bin/sqlite2js.py`) that assigns its content to a `window.__EXAM_*` global as base64; `<script src>` tags aren't subject to CORS the way `fetch()` is. The loading cascade always tries in this order: (1) already-loaded `window.__EXAM_*` global, (2) `loadScript()` the `.js` file, (3) `fetch()` the raw `.json`/`.sqlite` (HTTP mode only), (4) prompt the user for manual file `<input>` (`_promptManualImport`, ~line 1301). **Any time you add or rename a data file, you must rerun `bin/sqlite2js.py`** or the new file won't be visible in file:// mode.

**sql.js WASM is embedded directly in `Exam-Prep.html`** as `const _WASM_B64 = '...'` (~line 927). The app is fully offline-capable with no CDN or external network dependencies.

Key functions in `Exam-Prep.html` (second `<script>` block):
- `initSQLjs()` (~1098) — decodes `_WASM_B64` into a Blob URL and initialises sql.js WASM once.
- `loadQuiz(quiz)` (~1109) — per-exam entry point: checks IndexedDB cache (`idbGet`, key `<id>_db`) against `meta.version`; on miss, loads the content DB then the optional results DB via `_loadDataAsset` (~1277), merges history (`_mergeResultsInto`, ~1333), and calls `ensureResultsTables()` (~1033) to add history tables if missing.
- `_renderPicker()` (~2488) → `showLangScreen()` (~1706) → `showConfigScreen()` (~2070) → `startExam()` (~2517).

**Cache invalidation — two separate mechanisms:**
- Bump `version` in `exams/<id>.json` (and regenerate `.js`) to force one exam's content to reload from source.
- Bump `_QDB_VERSION` (~line 968 in `Exam-Prep.html`) to invalidate the IndexedDB cache for *all* exams globally — use only when the IDB schema itself changes.

**Exam registration is purely declarative**: add a row to `exams/index.json`, add `exams/<id>.json` (id/title/perExam/timeMin/passThreshold/contentFile/resultsFile — see README §5 for the full field list), drop the question bank at `data/content/<id>.sqlite`, then regenerate `.js` files. No code changes needed for a new exam.

**Custom exams** (created via the "+ Add exam" button in the picker) store metadata in `localStorage` under the key `_exam_custom_quizzes_v1` and their SQLite DB in IndexedDB. They follow the same `loadQuiz` path as bundled exams.

**Question schema** (`questions` table, see README §4.1): single-select exams (CDMP, AI-900) use the 4-option/no-multi schema; DP-300/AZ-104/DP-700 and custom imports use the extended schema with `opt_e`/`opt_f`, `is_multi`, `select_count`. `correct_idx` is TEXT to support both a single index (`"2"`) and multi-select lists (`"0,2"`). The answer is never kept as a raw index client-side — the app stores a SHA-1 hash of the correct option's text to prevent DOM inspection from revealing it.

**History/adaptive mode**: `sessions` / `domain_scores` / `session_answers` tables (added by `ensureResultsTables()`) track every exam taken. Adaptive mode looks at the last 3 sessions, pools questions answered correctly ≥2 times as "mastered" (15% of the draw) vs. "needs review" (85%). History can be exported/imported independently of questions via `data/results/<id>_history.sqlite`, deduplicated on `sessions.started_at` (collisions bumped by 1 second, up to 300 attempts).

**Translation**: `bin/serve.py` proxies `POST /api/translate` to `api.anthropic.com/v1/messages` to bypass CORS for in-browser question translation (Claude Haiku). The API key is entered on the language screen, saved to `sessionStorage._ak` (auto-cleared on tab/browser close), and forwarded by the browser via `X-Api-Key` — never stored server-side. Translation only works in HTTP mode (not `file://`).

**YouTube → QCM**: `POST /api/transcript` downloads subtitles via the yt-dlp Python API (not subprocess — avoids PATH issues in Alpine containers). Returns 422 for missing subtitles or invalid URL. The API key is validated with a 1-token test call before any download starts; if the call returns 401, the key field is shown again. In production, pass `--cors-origin https://your-domain.com` to restrict proxy access to your origin only.

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%). Format flags (-c, -l, -L, -o, -Z) run raw.
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->
