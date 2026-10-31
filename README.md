# Regex Replace

Find and replace patterns in spreadsheets using plain English. Upload a CSV or Excel file,
describe what to find (for example, *"Find email addresses in the Email column and replace
them with 'REDACTED'"*), and an LLM (Claude) turns the description into a regular
expression. You preview exactly which cells will change, then apply the replacement.
You can also **extract** pieces of a column into new columns ("split Name into first and
last name") and **classify** a text column, such as customer comments, into categories
you name.

**Live demo:** https://32-237-30-22.sslip.io

<!-- Demo video: drag the .mp4 into this file while editing it on GitHub; GitHub uploads it and inserts a URL that renders as an inline player. -->

**Demo video:** _coming soon_

---

## Contents

- [Features](#features)
- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Run it locally](#run-it-locally)
- [Tests and LLM evaluation](#tests-and-llm-evaluation)
- [Deployment (AWS EC2)](#deployment-aws-ec2)
- [API reference](#api-reference)
- [Design decisions](#design-decisions)
- [Large files](#large-files)
- [Extract and Classify](#extract-and-classify)
- [Limitations and future work](#limitations-and-future-work)
- [Project structure](#project-structure)

---

## Features

**Required by the exercise**

- **Upload** CSV (`.csv`, up to 200 MB) or Excel (`.xlsx`, up to 50 MB) files, by
  drag-and-drop or file picker. A built-in sample file lets you try the app without one.
- **Describe the pattern in natural language.** Claude converts the description into a
  regex. The replacement value and the target columns can be written in the same sentence
  or set separately.
- **Replace matches in text columns** and **display the updated data** in a paginated
  table. Numeric columns (such as IDs) are left alone unless explicitly selected.

**Beyond the requirements**

- **Preview before applying.** See the generated regex, a one-sentence explanation, match
  statistics and before/after samples. Nothing changes until you click *Apply*.
- **Changed cells are highlighted** in the table after applying.
- **Non-destructive versions.** Every apply creates a new version; the uploaded data
  (version 1) is never modified.
- **Data retention.** Datasets and their files are deleted 24 hours after upload by an
  hourly job, so the public demo neither keeps people's data nor fills its disk.
- **Self-correcting LLM loop.** If the generated regex is invalid, too slow, matches empty
  text, matches nothing, or would not change anything, the problem is sent back to Claude
  for another attempt.
- **Extract (optional item: creative LLM transformation 1 of 2).** Describe what to pull
  out, such as *"Split Name into first and last name"* or *"Extract the year from Signup
  Date"*. Claude writes a regex with one named group per piece, and each group becomes a
  new column next to the source. Like find-and-replace, it is one LLM call and scales to
  large files. See [Extract and Classify](#extract-and-classify).
- **Classify (optional item: creative LLM transformation 2 of 2).** Pick a text column
  and name the categories, for example *"Classify as Complaint, Question, Refund
  request"*, or describe a grouping and let Claude propose them. Claude labels every
  distinct value, the preview shows the share of each category, and applying adds a new
  column. Regex cannot do this, because the categories depend on meaning, not wording.
- **Large files (optional item).** CSVs are parsed, transformed and stored in batches, so
  memory stays around 200 MB whether a file has one or two million rows. Previews scan
  the first 50,000 rows and are labeled as estimates; applying processes every row. See
  [Large files](#large-files).
- **Safe regex execution.** Per-cell and per-operation time limits (ReDoS protection)
  and rejection of patterns that match empty text.
- **Production deployment** on AWS EC2 with Docker, automatic HTTPS, PostgreSQL, rate
  limits and a health check.

## How it works

```mermaid
sequenceDiagram
    actor User
    participant UI as React
    participant API as Django REST API
    participant LLM as Claude
    participant Store as PostgreSQL + Parquet files

    User->>UI: Upload file
    UI->>API: POST /api/datasets/
    API->>Store: Parse to version 1 (Parquet)
    User->>UI: "Find email addresses and replace them with 'REDACTED'"
    UI->>API: POST /api/datasets/{id}/transformations/preview/
    API->>LLM: Description + column names + sample values
    LLM-->>API: pattern, replacement, columns, explanation
    API->>API: Validate and run the regex (retry with feedback if unusable)
    API-->>UI: Statistics + before/after samples
    User->>UI: Apply
    UI->>API: POST /api/transformations/{id}/apply/
    API->>Store: Save result as version 2
    UI->>API: GET /api/datasets/{id}/rows/ (changed cells highlighted)
```

With the exercise's example, Claude returns a structured answer such as:

| Field | Value |
|---|---|
| Pattern | `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b` |
| Replacement | `REDACTED` |
| Columns | `["Email"]` |
| Explanation | Matches email addresses in the Email column. |

The regex only describes *what to find*. The replacement is a separate value, applied
with Python's `regex.sub(pattern, replacement, cell)` to each cell of the target columns.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12, Django 5.2 LTS, Django REST Framework | Required by the exercise; LTS release |
| Data | pandas, openpyxl, PyArrow (Parquet) | Read CSV/Excel; store versions in a compact columnar format |
| Regex | [`regex`](https://pypi.org/project/regex/) package | `re`-compatible syntax with a per-call timeout |
| LLM | Claude via the official `anthropic` SDK: `claude-opus-5-5` writes regexes, `claude-haiku-5-5` classifies | Structured outputs validated by Pydantic models; a fast, cheap model for high-volume labeling |
| Frontend | React 19, TypeScript (strict), Vite, TanStack Query, Tailwind CSS | Typed API layer, caching and loading states |
| Database | SQLite locally, PostgreSQL 17 in production | Zero setup locally; robust in production |
| Serving | gunicorn, WhiteNoise, Caddy | Django serves the built React app; Caddy provides HTTPS |
| Tooling | uv, ruff, pytest, oxlint | Fast, locked, reproducible |

## Run it locally

**Prerequisites:** [uv](https://docs.astral.sh/uv/) (installs Python 3.12 for you),
Node.js 22+, and an [Anthropic API key](https://console.anthropic.com/).

```bash
git clone https://github.com/hsiao0207/Rhombus.git
cd Rhombus
cp .env.example .env        # then set ANTHROPIC_API_KEY in .env
```

**Backend** (terminal 1):

```bash
cd backend
uv sync                                  # install locked dependencies into .venv
uv run python manage.py migrate          # create the local SQLite database
uv run python manage.py runserver        # http://127.0.0.1:8000
```

**Frontend** (terminal 2):

```bash
cd frontend
npm ci
npm run dev                              # http://localhost:5173
```

Open http://localhost:5173. The Vite dev server forwards `/api` to Django, so the browser
talks to a single origin, as it does in production.

Without `ANTHROPIC_API_KEY`, everything except pattern generation works and the preview
returns a clear `LLM_NOT_CONFIGURED` error.

### Configuration

All settings come from environment variables (see [`.env.example`](.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for natural-language patterns |
| `LLM_MODEL` | `claude-opus-5-5` | Claude model that writes regexes |
| `LLM_EFFORT` | `medium` | Reasoning effort (`low` … `max`); trades latency and cost for quality |
| `LLM_CLASSIFY_MODEL` | `claude-haiku-5-5` | Claude model that labels values for *Classify* |
| `LLM_CLASSIFY_EFFORT` | `low` | Reasoning effort for classification |
| `MAX_CLASSIFY_VALUES` | `1000` | Most distinct values a column may have to be classified |
| `MAX_UPLOAD_SIZE_MB` | `200` | Upload limit |
| `MAX_EXCEL_UPLOAD_SIZE_MB` | `50` | Lower limit for Excel, which is parsed in one go |
| `PREVIEW_ROW_LIMIT` | `50000` | Rows a preview scans; larger datasets get estimated statistics |
| `REGEX_APPLY_TIMEOUT_SECONDS` | `120` | Time budget for applying a pattern to every row |
| `THROTTLE_PREVIEW` | `60/hour` | Previews per client IP (each one calls the LLM) |
| `THROTTLE_CLASSIFY` | `20/hour` | Classification previews per client IP (several LLM calls each) |
| `THROTTLE_UPLOAD` | `30/hour` | Uploads per client IP |
| `DATASET_RETENTION_HOURS` | `24` | Datasets and their files are deleted this long after upload |
| `DJANGO_DEBUG` | `false` | Must be `true` locally unless `DJANGO_SECRET_KEY` is set |
| `DATABASE_URL` | SQLite | e.g. `postgres://user:pass@host:5432/db` |

## Tests and LLM evaluation

```bash
cd backend
uv run pytest            # 126 tests; the LLM is replaced by fakes, no network or API key needed
uv run ruff check .      # lint

cd ../frontend
npm run lint             # oxlint
npm run build            # type-check (tsc) and production build
```

The tests cover file parsing, the regex engine (including catastrophic backtracking), the
preview/apply API, versioning and conflict detection, the self-correction loop, the Claude
client's error handling, and rate limiting.

Unit tests cannot tell whether Claude writes *good* regexes, so there is also an
evaluation command that runs the real pipeline against a deliberately messy dataset
(three phone formats, mixed date formats, emails inside free text, and more):

```bash
uv run python manage.py evaluate_llm                 # all 12 cases (real API calls, costs a few cents)
uv run python manage.py evaluate_llm --case 3        # a single case
uv run python manage.py evaluate_llm --try "Mask phone numbers in Notes with ***"
```

A case passes only if the **entire** resulting table matches the expected output: the
target cells changed and everything else untouched. All 12 cases pass.

## Deployment (AWS EC2)

The live demo runs on a single EC2 instance with Docker Compose:

```
Internet ──HTTPS──▶ Caddy ──▶ app (gunicorn + Django + built React) ──▶ PostgreSQL
                    :443            :8000                                 volume: pgdata
                                    Parquet versions ──▶ volume: media
                    cleanup (same image, hourly) ──▶ deletes expired datasets
```

- **Caddy** obtains and renews a Let's Encrypt certificate automatically. The domain uses
  [sslip.io](https://sslip.io), which resolves `32-237-30-22.sslip.io` to `32.237.30.22`,
  so no domain purchase is needed.
- The **Docker image** is multi-stage: Node builds the React app, and the final Python
  image contains only the backend and the built static files. It runs as a non-root user.
- On start, the container applies migrations and then starts gunicorn.
- A **cleanup** container from the same image runs `manage.py cleanup_datasets` every
  hour. It skips the entrypoint so only `app` runs migrations, and starts once `app` is
  healthy. No cron setup is needed on the host.

**Steps to reproduce:**

1. Launch an Ubuntu (24.04 or later) instance, e.g. `t3.small` with 20 GB of disk. Attach
   an Elastic IP. Security group: SSH (22) from your IP only; HTTP (80) and HTTPS (443)
   from anywhere.
2. SSH in and set up the server:
   ```bash
   git clone https://github.com/hsiao0207/Rhombus.git && cd Rhombus
   ./deploy/ec2-setup.sh       # Docker, Compose and 2 GB swap; log out and back in afterwards
   ./deploy/make-env.sh        # writes .env with random secrets; prompts for the API key
   ./deploy/deploy.sh          # build and start the stack
   ```
3. Open `https://<elastic-ip-with-dashes>.sslip.io`.

To ship a new version, push to `main`, then run `./deploy/deploy.sh` on the server (it
pulls, rebuilds, restarts and prunes old images).

## API reference

All endpoints are under `/api/`, accept and return JSON (uploads use `multipart/form-data`),
and need no authentication.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health/` | Liveness check (also checks the database) |
| `POST` | `/api/datasets/` | Upload a file (`file` field). Returns the dataset with version 1 |
| `GET` | `/api/datasets/{id}/` | Dataset metadata and its current version |
| `GET` | `/api/datasets/{id}/rows/?page=1&page_size=50` | Rows of the current version, with changed cells |
| `POST` | `/api/datasets/{id}/transformations/preview/` | Generate a pattern and preview its effect |
| `POST` | `/api/datasets/{id}/extractions/preview/` | Generate an extraction pattern and preview the new columns |
| `POST` | `/api/datasets/{id}/classifications/preview/` | Classify a column's values and preview the categories |
| `GET` | `/api/transformations/{id}/` | A previewed or applied transformation |
| `POST` | `/api/transformations/{id}/apply/` | Apply a preview, creating a new version |

### Preview

```http
POST /api/datasets/{id}/transformations/preview/
Content-Type: application/json

{
  "instruction": "Find email addresses in the Email column and replace them with 'REDACTED'",
  "replacement": null,
  "columns": null
}
```

`replacement` and `columns` are optional overrides. When set, they take precedence over
what Claude inferred from the instruction. If no replacement is given anywhere, matches
are deleted. If no columns are given anywhere, all text columns are searched.

Instead of `instruction`, the API also accepts an explicit `pattern` (with optional
`flags`: `IGNORECASE`, `MULTILINE`, `DOTALL`), which skips the LLM. The UI does not expose
it; the backend tests use it for deterministic preview/apply checks.

```jsonc
// 201 Created
{
  "transformation": {
    "id": "6f1c…",
    "kind": "replace",
    "status": "previewed",
    "instruction": "Find email addresses in the Email column and replace them with 'REDACTED'",
    "explanation": "Matches email addresses in the Email column.",
    "pattern": "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b",
    "flags": [],
    "replacement": "REDACTED",
    "columns": ["Email"],
    "stats": {
      "total_matches": 3,
      "total_cells_changed": 3,
      "rows_affected": 3,
      "rows_scanned": 3,
      "total_rows": 3,
      "columns": { "Email": { "matches": 3, "cells_changed": 3 } }
    },
    "source_version": 1,
    "result_version": null
  },
  "samples": [
    { "row": 0, "column": "Email", "before": "john.doe@example.com", "after": "REDACTED" }
  ]
}
```

`rows_scanned` is lower than `total_rows` when a large dataset was previewed on its first
rows only; the counts are then estimates.

### Extract

```http
POST /api/datasets/{id}/extractions/preview/
Content-Type: application/json

{ "instruction": "Split Name into first and last name", "column": null }
```

`column` is optional; without it, Claude picks the column from the instruction.

```jsonc
// 201 Created (abridged)
{
  "transformation": {
    "id": "c41d…",
    "kind": "extract",
    "status": "previewed",
    "pattern": "^\\s*(?P<first_name>\\S+)\\s+(?P<last_name>\\S+)\\s*$",
    "columns": ["Name"],
    "params": {
      "source_column": "Name",
      "new_columns": [
        { "group": "first_name", "column": "Name_first_name" },
        { "group": "last_name", "column": "Name_last_name" }
      ]
    },
    "stats": {
      "rows_matched": 3,
      "rows_scanned": 3,
      "total_rows": 3,
      "columns": { "Name_first_name": 3, "Name_last_name": 3 }
    }
  },
  "samples": [
    { "row": 0, "value": "John Doe", "parts": { "Name_first_name": "John", "Name_last_name": "Doe" } }
  ]
}
```

`new_columns` is a list rather than an object because PostgreSQL's `jsonb` does not keep
object key order, and the columns' order matters.

### Classify

```http
POST /api/datasets/{id}/classifications/preview/
Content-Type: application/json

{ "column": "Notes", "instruction": "Classify as Complaint, Question, Refund request" }
```

```jsonc
// 201 Created (abridged)
{
  "transformation": {
    "id": "9b2e…",
    "kind": "classify",
    "status": "previewed",
    "explanation": "Each note will be sorted into Complaint, Question, or Refund request.",
    "columns": ["Notes"],
    "params": {
      "source_column": "Notes",
      "new_column": "Notes_category",
      "categories": ["Complaint", "Question", "Refund request", "Other"]
    },
    "stats": {
      "categories": { "Complaint": 2, "Question": 2, "Refund request": 1, "Other": 1 },
      "distinct_values": 6,
      "rows_classified": 6,
      "total_rows": 6
    }
  },
  "samples": [
    { "row": 0, "column": "Notes", "before": "My order hasn't arrived after 2 weeks", "after": "Complaint" }
  ]
}
```

### Apply

Applying either kind returns the transformation (now `"status": "applied"`,
`"result_version": 2`) and the updated dataset. A preview can be applied only once, and
only while its source version is still the current one; otherwise the API returns `409`.

### Errors

Every error has the same shape, so the frontend can show a specific message per `code`:

```json
{ "error": { "code": "PATTERN_GENERATION_FAILED", "message": "…", "details": { } } }
```

| Status | Codes |
|---|---|
| 400 | `VALIDATION_ERROR`, `EMPTY_FILE`, `FILE_PARSE_ERROR`, `UNKNOWN_COLUMNS`, `NO_TARGET_COLUMNS`, `NOTHING_TO_CLASSIFY`, `TOO_MANY_CATEGORIES`, `INVALID_GROUPS`, and, for explicit patterns, `INVALID_REGEX`, `PATTERN_MATCHES_EMPTY`, `INVALID_REPLACEMENT` |
| 404 | `NOT_FOUND` |
| 409 | `ALREADY_APPLIED`, `STALE_VERSION` |
| 413 / 415 | `FILE_TOO_LARGE` / `UNSUPPORTED_FILE_TYPE` |
| 422 | `PATTERN_GENERATION_FAILED`, `LLM_REFUSED`, `REGEX_TIMEOUT`, `TOO_MANY_VALUES` |
| 429 | `THROTTLED` (with `retry_after_seconds`) |
| 500 | `INTERNAL_ERROR` (details are logged, never returned) |
| 502 / 503 | `LLM_BAD_OUTPUT` / `LLM_UNAVAILABLE`, `LLM_NOT_CONFIGURED` |

## Design decisions

**Layered backend.** Views only validate input and serialize output. The logic lives in
plain-Python services (`datasets/services/`), and the regex engine does not depend on
Django at all. Domain errors are plain exceptions carrying an HTTP status; a single DRF
exception handler turns them into the error format above.

**Preview, then apply.** An LLM-written regex can be subtly wrong. Showing the pattern,
the counts and before/after samples first means a bad pattern costs a glance, not your
data. Apply re-runs the exact stored pattern inside a database transaction with a row
lock, so double clicks or stale tabs cannot apply twice or on top of newer data.

**Immutable versions stored as Parquet.** Version 1 is the parsed upload, and each apply
writes a new version that links to its parent. This keeps the original safe, makes
highlighting a simple diff against the parent, and would make undo and history easy to
add. Parquet is compact and fast to read back for pagination: the 100 MB test CSV is
27 MB as Parquet. The uploaded file itself is not stored, since version 1 holds all of
its data and nothing reads the file again.

**Bounded storage.** Each version is a full copy, which keeps reading any page simple
but means storage grows with every apply. An hourly `cleanup_datasets` job deletes
datasets 24 hours after upload, rows first and then files, so a failure can leave
unreferenced files but never a row pointing at missing data. It also removes folders
left behind by failed uploads, but only once their files are as old as the retention
period, so an upload still being saved is never touched.

**Every value is read as text.** Files are parsed with `dtype=str`, so `007` stays `007`
and dates are not reformatted. A column counts as numeric only when every non-empty value
parses as a number. Numeric columns are excluded by default, following the exercise's
"replace in text columns".

**Grounding the LLM in the data.** Claude receives the column names, their kind, and five
distinct sample values per column. Real formats (`(02) 2345-6789` and `+886 912 345 678`
in the same column) produce regexes that match the data, not an idealized format.
Claude must answer in a fixed schema (`pattern`, `flags`, `replacement`, `columns`,
`explanation`), validated with Pydantic, so there is no free-text parsing.

**Self-correction instead of hoping.** Each suggestion is compiled and run before the
user sees it. If it is invalid, matches empty text, times out, matches nothing, or would
leave every cell unchanged, the specific problem goes back to Claude (two attempts in
total). The last two checks came from the evaluation suite: one instruction made Claude
read a phone number as a format template, which compiled fine but changed nothing.

**User input wins over inference.** Claude may infer the replacement and columns from
the sentence, but explicit form values override it, and column names Claude invents are
discarded. When no replacement is stated, Claude is told to return `null` rather than
invent one.

**Prompt-injection guard.** The user's text and the file's contents are wrapped in tags
and declared as data. The worst a malicious cell can achieve is a bad regex, which the
preview exposes.

**Regex safety and speed.** The `regex` package enforces two time limits: one second per
cell, so a catastrophically backtracking pattern fails fast, and a total budget scaled to
the work (5 seconds for a preview, 120 seconds for an apply). A single budget for both
would either let ReDoS run long or reject legitimate work on large files. Patterns are
also length-limited. Within each batch, a column is processed per *unique* value and
mapped back, so repeated values cost one regex call.

**One origin in production.** Django serves the built React app through WhiteNoise, so
there is no CORS configuration. Hashed assets are cached forever; `index.html` is
revalidated on every load, so a deploy takes effect immediately.

**Cost control.** One preview costs about $0.01 with the default model and effort
(about 1,500 input and 150 output tokens) and takes about 4 seconds. Previews are
rate-limited per IP because they spend real money.

## Large files

The first version loaded every file fully into memory and ran each operation within a
single 5-second regex budget. Measuring it with a one-million-row CSV showed three
problems: memory grew with the file size, every page of the table read the whole file,
and previewing even a simple email pattern failed with `REGEX_TIMEOUT`.

The fix keeps the architecture and changes how data flows through it, in batches of
50,000 rows:

1. **Upload:** the CSV is parsed with `pandas.read_csv(chunksize=...)`, each batch is
   written as its own Parquet row group, and column kinds are inferred across batches.
   An undecodable byte late in the file restarts parsing with the fallback encoding,
   and nothing is stored until the whole file has been written.
2. **Table pages:** only the row groups that contain the requested rows are read, and
   the row count comes from Parquet metadata.
3. **Preview:** the pattern runs on the first 50,000 rows only. The statistics are
   labeled as estimates in the UI, and *Apply* stays enabled even when no change was
   found in those rows.
4. **Apply:** batches are read, transformed and written one at a time, under the
   separate per-cell and per-operation time limits described above.

Measured locally (MacBook) with the worst case for the engine: every email and note is
unique, and the pattern is applied to two columns. Each stage ran in its own process.

| | 1M rows, 117 MB: before | 1M rows: after | 2M rows, 239 MB: after |
|---|---|---|---|
| Upload | 4.2 s, 441 MB peak | 2.8 s, 211 MB | 3.5 s, 198 MB |
| Open the last page | 0.26 s, 417 MB | 0.03 s, 157 MB | 0.05 s, 162 MB |
| Preview | fails (`REGEX_TIMEOUT`) | 0.4 s, 204 MB | 0.5 s, 194 MB |
| Apply (every row) | not reachable | 7.3 s, 249 MB | 15.4 s, 204 MB |

Peak memory is for the whole process, including Python, Django and pandas themselves. It
stays flat as the file doubles, and time grows linearly.

## Extract and Classify

The two optional LLM transformations use the LLM in two different ways, on purpose:

| | Find and replace | Extract | Classify |
|---|---|---|---|
| What the LLM does | Writes a regex once | Writes a regex with named groups once | Judges every distinct value |
| Result | Values changed in place | One new column per group | One new category column |
| LLM calls | 1 per preview, whatever the file size | 1 per preview, whatever the file size | 1 per 100 distinct values, plus 1 to settle the categories |
| Same result every time | Yes, code applies the rule | Yes, code applies the rule | No, so the result is stored (below) |
| Large files | Yes | Yes | Up to 1,000 distinct values |
| Suited to | Text with a recognizable form | Text with a recognizable form | Text whose category depends on meaning |

### Extract

"Extract the email domain", "Split Name into first and last name" or "Extract the year
from Signup Date": Claude writes a regex in which every piece to keep is a named group,
`(?P<first>\S+)\s+(?P<last>.+)`, and picks the source column (the user can also choose
it). Each group becomes a column named `<source>_<group>`, inserted after the source.
The first match in each cell is used; cells without one get empty values.

It reuses the find-and-replace machinery: the same column samples ground the model, a
preview scans the first 50,000 rows, and apply runs the stored pattern over every row in
batches. The self-correction loop also sends back a pattern without named groups, a
column name that does not exist, or a pattern that matches nothing.

Real formats are where the model earns its place. With dates written as `2020-04-17`,
`11/07/2024` and `2/13/2023` in one column, Claude wrote one alternative per format, all
capturing into the same `year` group, which the `regex` package allows (the standard
`re` module does not). On the 100 MB test file, the four instructions above each
succeeded on the first attempt, in about 3 seconds.

### Classify

"My order hasn't arrived" and "Package came damaged" are both complaints with no word in
common, and "Why is it so late?" is a complaint phrased as a question. No regex captures
that, so *Classify* asks the model about each value.

**How it works.** The column is scanned for its distinct, non-empty values. One call
settles the categories: the user's own, or 2 to 6 proposed from sample values, plus an
automatic *Other* for values that fit none. The values then go out in batches of 100,
five batches at a time, to `claude-haiku-5-5`. The response schema is generated from
the category list, so structured outputs cannot return a category outside it. Values the
model skips are retried once and otherwise marked *Unclassified*.

**Preview and apply see the same labels.** A model can label the same value differently
on two calls. The preview therefore classifies every distinct value and stores the value
to category mapping with the preview. *Apply* only looks values up in it: the new column
is exactly what the user approved, and the LLM is not called a second time.

**Why a cap of 1,000 distinct values.** The cost and time grow with the number of
distinct values, not rows. Repeated values are classified once, so a 100,000-row file of
statuses or short comments is cheap. A column of unique free text is not. The 100 MB
test file's *Notes* column has 523,485 distinct values, which estimates to:

| Model | LLM calls | Tokens (in / out) | Cost |
|---|---|---|---|
| Claude Haiku 5.5 | about 5,235 | about 13M / 6M | about $4 |
| Claude Opus 5.5 | about 5,235 | about 13M / 7M | about $190 |

That is affordable with Haiku, but takes around an hour, far beyond a web request. So
classification is capped at 1,000 distinct values (at most 11 calls, a few seconds with
Haiku), and the error message suggests a better-suited column. Going beyond that needs a
background job using the Message Batches API (half price, results within 24 hours) and a
progress indicator. For comparison, a real six-note classification measured about 700
input and 100 output tokens per call, and around 4 seconds end to end.

**Why Haiku.** Picking one label from a short list is the high-volume, simple work Haiku
is built for, at a fraction of Opus's price; regex writing stays on Opus, where a wrong
pattern corrupts data. The two models are configured separately. Haiku 5.5 does not
support server-side fallback, so classification requests do not ask for it.

## Limitations and future work

- **No accounts.** Datasets are identified by unguessable UUIDs, so anyone with a
  dataset's link can open it. A real product would add authentication and ownership.
- **Every version is a full copy.** Retention bounds storage over time, but one dataset
  with many applies still stores many copies. Keeping only the latest few versions, or
  moving files to S3 with lifecycle rules, would reduce it further.
- **Processing is synchronous.** Uploads and applies run within the request: about 15
  seconds for two million rows, with no progress bar. Going well beyond 200 MB would
  need background jobs (a job table and worker, or Celery) with progress reporting, and
  direct-to-S3 uploads so large files do not pass through Django.
- **Excel is not streamed.** pandas loads `.xlsx` files whole, hence their lower 50 MB
  limit. Excel itself caps a sheet at about one million rows, and saving as CSV lifts the
  limit.
- **Replacement is per cell.** A regex sees one cell at a time, so it cannot express
  "only the row where ID = 2". A natural next step is an LLM-generated row filter that
  restricts which rows the regex runs on.
- **No export or undo in the UI.** Versions are already stored, so a download endpoint
  (CSV/XLSX) and a version history with undo are mostly frontend work.
- **English instructions** are assumed (UI, prompts and evaluation are English).
- **Frontend has no automated tests.** The UI was tested manually; component tests
  (Vitest + Testing Library) and an end-to-end test (Playwright) would be the next step.
- **Extract keeps the first match per cell.** A cell with two emails yields only the
  first domain. Collecting every match (for example, comma-separated) would be an option,
  at the cost of values that are harder to analyze further.
- **Classification is limited to 1,000 distinct values** per column (see
  [Classify](#classify)); larger columns need a background job with the Message Batches
  API.

## Project structure

```
.
├── backend/
│   ├── config/                  # Django settings, URLs, WSGI
│   ├── datasets/
│   │   ├── models.py            # Dataset, DatasetVersion, Transformation
│   │   ├── views.py             # Thin HTTP layer
│   │   ├── serializers.py       # Request validation and response shapes
│   │   ├── exceptions.py        # Domain errors (no framework dependency)
│   │   ├── exception_handler.py # Domain/DRF errors → {"error": {...}}
│   │   ├── throttles.py         # Rate limits for uploads, previews and classifications
│   │   ├── services/
│   │   │   ├── file_io.py               # CSV/Excel parsing, Parquet storage, paging
│   │   │   ├── dataset_service.py       # Upload, versions, rows with changed cells
│   │   │   ├── regex_engine.py          # Safe, fast regex replacement over DataFrames
│   │   │   ├── transformation_service.py# Preview/apply and the LLM retry loop
│   │   │   ├── extraction_service.py    # Extract: named groups into new columns
│   │   │   ├── classification_service.py# Classify: distinct values, batches, stored mapping
│   │   │   └── llm/                     # Provider-neutral interface, prompts, Claude client
│   │   ├── management/commands/  # evaluate_llm, cleanup_datasets
│   │   └── tests/
│   ├── gunicorn.conf.py
│   └── docker-entrypoint.sh
├── frontend/src/
│   ├── api/                     # Typed fetch client and endpoint functions
│   ├── hooks/                   # TanStack Query hooks
│   └── components/              # Upload, transform panel, preview, data table
├── deploy/                      # EC2 setup, .env generation, deploy script
├── Dockerfile                   # Multi-stage: build React, then the Python runtime
├── docker-compose.yml           # Caddy + app + PostgreSQL + hourly cleanup
└── Caddyfile                    # HTTPS reverse proxy
```
