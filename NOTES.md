# Engineering Notes: FlyRight

## D03 · PostgreSQL

### 1. Database Migrations

Migration history was verified using:

```powershell
uv run alembic history
```

Output:

```text
014aa435b676 -> 51ec6327ece4 (head), add gin index on metadata
<base> -> 014aa435b676, create documents and pages
```

### 2. Migration Rollback Test

Commands executed:

```powershell
uv run alembic downgrade -1
uv run alembic current
uv run alembic upgrade head
```

The downgrade successfully reverted to migration `014aa435b676`.

The upgrade successfully restored migration `51ec6327ece4`.

### 3. Database Loader Idempotency

The loader uses SHA-256 fingerprints to detect inserted, updated, and unchanged records.

First run:

```text
records=20 inserted=0 updated=0 unchanged=20
```

Second run:

```text
records=20 inserted=0 updated=0 unchanged=20
```

Temporary modification test:

```text
records=20 inserted=0 updated=1 unchanged=19
```

Restoration run:

```text
records=20 inserted=0 updated=1 unchanged=19
```

The loader correctly detected unchanged and updated records. The original sample JSON file was not modified. The temporary test file was removed.

### 4. GIN Index Verification

Command:

```powershell
uv run python scripts/explain.py rule "3.2.1 - Volunteers for denied boarding"
```

**Normal query plan**

```text
Seq Scan on documents  (cost=0.00..3.25 rows=1 width=36) (actual time=2.140..2.140 rows=1.00 loops=1)
 Filter: (metadata @> '{"rule": "3.2.1 - Volunteers for denied boarding"}'::jsonb)
 Rows Removed by Filter: 19
 Buffers: shared read=3 dirtied=3
Planning:
 Buffers: shared hit=117 read=8 dirtied=1
Planning Time: 6.343 ms
Execution Time: 2.171 ms
```

**Query plan with sequential scans disabled**

```text
Bitmap Heap Scan on documents (cost=8.54..12.55 rows=1 width=36) (actual time=0.872..0.873 rows=1.00 loops=1)
 Recheck Cond: (metadata @> '{"rule": "3.2.1 - Volunteers for denied boarding"}'::jsonb)
 Heap Blocks: exact=1
 Buffers: shared hit=2 read=1
 -> Bitmap Index Scan on ix_documents_metadata_gin (cost=0.00..8.54 rows=1 width=0) (actual time=0.833..0.833 rows=1.00 loops=1)
      Index Cond: (metadata @> '{"rule": "3.2.1 - Volunteers for denied boarding"}'::jsonb)
      Index Searches: 1
      Buffers: shared hit=1 read=1
Planning:
 Buffers: shared hit=1
 Planning Time: 0.087 ms
Execution Time: 0.922 ms
```

**Why did PostgreSQL choose Seq Scan?**

The documents table contains only 20 records. Scanning all rows is inexpensive for such a small table.

**When would PostgreSQL switch to the GIN index?**

PostgreSQL may choose the GIN index when the table grows and using the index becomes cheaper than scanning every row.

### 5. Test Results

Command:

```powershell
uv run pytest -v
```

Previously recorded result:

```text
16 passed, 3 skipped in 0.33s
```

The three integration tests are skipped when `TEST_DATABASE_URL` is not configured.

### 6. PostgreSQL Integration Tests

Command:

```powershell
uv run pytest tests/test_db_integration.py -v
```

Result:

```text
3 passed in 10.76s
```

### 7. Complete Test Suite

Command:

```powershell
uv run pytest -v
```

Previously recorded result:

```text
19 passed in 11.50s
```

### 8. Code Quality

Command:

```powershell
uv run ruff check .
```

Result:

```text
All checks passed!
```

### 9. Final Day 3 Verification

The database loader successfully demonstrated idempotency across repeated runs. The GIN index was verified using PostgreSQL query plans, and database migrations were tested through downgrade and upgrade operations.

---

## D04 · Docker and Testing

### 1. Docker Setup

- Created a multi-stage Dockerfile using Python 3.12 and uv.
- Configured a non-root application user.
- Added Docker Compose services for API, PostgreSQL, Redis, and migrations.
- Verified all services started successfully.

### 2. API Verification

- Swagger UI: http://localhost:8000/docs
- Health endpoint: `GET /health`
- Readiness endpoint: `GET /ready`
- Documents endpoint: `GET /v1/documents`

### 3. Health and Recovery Test

Stopped PostgreSQL and verified:

- `/health` returned status `ok`.
- `/ready` returned status `not_ready`.
- After restarting PostgreSQL, `/ready` returned status `ready`.

### 4. Migration and Loader Idempotency

After restarting the Docker Compose stack:

```text
records=20 inserted=0 updated=0 unchanged=20
```

The loader detected that all 20 records were unchanged.

---

## D05 · CI/CD and Going Live

### 1. Live Deployment

**Live URL:** https://flyright-api.onrender.com

The application was deployed to Render using a public GitHub Container Registry image.

Production environment:

- `APP_ENV=production`
- `DATABASE_URL` configured in Render.
- Health Check Path: `/health`

### 2. Health Check Verification

Live `/health` endpoint:

https://flyright-api.onrender.com/health

Previously recorded production response:

```json
{
  "status": "ok",
  "app": "flyright",
  "env": "production",
  "version": "9c921e1"
}
```

Live `/ready` endpoint:

https://flyright-api.onrender.com/ready

Verified response:

```json
{
  "status": "ready",
  "checks": {
    "database": true
  }
}
```

Both endpoints returned successful responses during the recorded verification.

### 3. Continuous Integration

GitHub Actions CI workflow:

`.github/workflows/ci.yml`

The workflow includes:

- Code quality checks.
- Unit tests.
- PostgreSQL integration tests.
- Test coverage.
- Docker image build.
- GitHub Container Registry image publishing on main.

The PostgreSQL integration tests were configured to run using a PostgreSQL service in GitHub Actions.

The CI checks passed on the pull request and after merging.

**CI run for the pull request:**

https://github.com/elamadhiram2006-code/prince28-cit02-flyright/actions/runs/45137072334

CI workflow duration: 1 minute 23 seconds.

### 4. Continuous Deployment

GitHub Actions CD workflow:

`.github/workflows/cd.yml`

The deployment workflow performs:

1. Waits for successful CI on main.
2. Runs database migrations on Neon.
3. Triggers Render deployment using the exact SHA-tagged Docker image.
4. Waits for the new application version.
5. Runs the deployment smoke test.

The Render deployment hook and database URL are stored as GitHub Actions secrets.

**Automatic CD deployment run:**

https://github.com/elamadhiram2006-code/prince28-cit02-flyright/actions/runs/45139183085

### 5. Smoke Test

The deployment smoke test checks:

- `/health` returns the expected commit SHA.
- `/ready` confirms database readiness.
- `/v1/documents?limit=1` successfully reads database-backed data.

The CD workflow completed successfully during deployment verification.

### 6. Rollback Drill

PR #8 was used as the older pre-CD image for the rollback drill.

**Rollback commit:** `9a443d0`

The manual CD workflow completed successfully.

Verified `/health` response during the rollback drill:

```json
{
  "status": "ok",
  "app": "flyright",
  "env": "production",
  "version": "9a443d0"
}
```

The live application reported the expected older commit.

### 7. Roll Forward

After the rollback drill, the application was rolled forward to commit `afb4d93`.

**Roll-forward commit:** `afb4d93`

Verified `/health` response during the roll-forward drill:

```json
{
  "status": "ok",
  "app": "flyright",
  "env": "production",
  "version": "afb4d93"
}
```

The application successfully returned to the version used for the roll-forward verification.

### 8. Why Was Rollback Safe?

The rollback workflow skips database migrations, so the database remains on the newer schema.

The older application version passed the smoke test against the existing database schema during the rollback drill. This demonstrated compatibility for the tested endpoints.

### 9. Where My Secrets Live

- Neon database URL: GitHub Actions secret `DATABASE_URL` and Render environment variables.
- Render deploy hook: GitHub Actions secret `RENDER_DEPLOY_HOOK` only.
- Live URL: GitHub Actions repository variable `LIVE_URL`.

Secrets are not stored in Git or inside the Docker image.

### 10. Monitoring

UptimeRobot monitor:

- URL: https://flyright-api.onrender.com/health
- Monitoring interval: Every 5 minutes.
- Email alerts: Enabled.
- Previously verified uptime: 100% over 30 days.

The uptime monitor checks the live health endpoint regularly.

### 11. Deployment Timing Evidence

The exact merge, smoke-test, rollback, and roll-forward timestamps and durations were not recorded in the available evidence.

CI workflow duration: 1 minute 23 seconds.

### 12. Performance Improvement

One improvement to make the first request faster would be to keep the Render service warm or use an always-on paid instance, avoiding the cold-start delay associated with the free instance.

---

## Final Project Status

- PostgreSQL database and migrations verified.
- Database loader idempotency verified.
- GIN index verified.
- Docker setup and API health checks verified.
- CI pipeline with PostgreSQL integration tests configured.
- Docker image publishing to GHCR configured.
- Render production deployment verified.
- Automatic CD deployment verified.
- Rollback and roll-forward drills verified.
- UptimeRobot monitoring configured.
- GitHub main branch protection enabled.

---

## D06 · Downloader and Resume Verification

### 1. Downloader Implementation

- Added a polite, resumable downloader using HTTPX and Protego.
- Added robots.txt checks before requesting documents.
- Implemented retry handling, timeouts and per-host delays.
- Added SHA-256 file hashing and atomic `.part` file handling.
- Added JSONL manifest tracking.
- Added CLI at `scripts/fetch.py`.
- Added permission checks before downloading sources.
- Supports HTTP Range requests for resuming partial downloads.

The resumable downloader changes were merged through PR #34.

### 2. Automated Downloader Tests

Command:

```powershell
uv run pytest tests/unit/test_fetch.py -q
```

Latest recorded result:

```text
25 passed in 0.44s
```

The tests verify downloader behaviour, including:

- Successful file downloads.
- SHA-256 hashing.
- Oversized-file rejection.
- Manifest recording.
- Skipping already downloaded files.
- Partial-download resume behaviour.
- Range response handling.

### 3. Full Test Suite and Code Quality

Previously verified full test suite:

```text
42 passed in 0.75s
```

Code quality verification:

- Ruff checks passed.
- Ruff formatting passed.
- Pre-commit hooks passed.
- Git whitespace checks passed.

These are previously recorded results; they were not rerun during the final documentation update.

### 4. Partial File Check

Command:

```powershell
Get-ChildItem data -Recurse -Filter *.part
```

Previously recorded result: No `.part` files found during that check.

### 5. Real Download Interruption and Resume — Pending

The automated tests verify the downloader's resume behaviour.

However, a separate real-world Ctrl+C interruption-and-resume drill has not been verified.

The required live exercise is:

1. Start an approved document download.
2. Interrupt it using Ctrl+C after approximately 10 seconds.
3. Run the downloader again.
4. Confirm that it resumes the partial download.
5. Run it again to verify that completed files are skipped.
6. Record the three run measurements.

No real run counts are claimed because this exercise has not been completed.

A permitted source and its publisher's download conditions must be verified before performing the live exercise.

---

## D06 · Collecting the Corpus

### 1. Starting Target

- Starting target: Passenger CARs and two airlines' conditions of carriage (IndiGo and Air India).
- Full target: Relevant CARs, revisions and four airlines' terms, with 1,200+ pages.
- Source register: `data/sources.csv`.
- Sources reviewed: 12 URLs, including government and aviation information sources and two airline sources.

### 2. Current Corpus Measurements

Latest measured dataset report:

| Metric | Result |
|---|---:|
| Valid unique PDF documents | 4 |
| Total PDF pages | 134 |
| Total characters | 192,381 |
| Estimated tokens | 28,084 |
| Total size | 30.42 MiB |
| Unavailable or excluded sources | 8 |
| Full corpus target | 1,200+ pages |
| Remaining pages to target | At least 1,066 |

The four valid PDFs in the measured D06 dataset were:

1. Passenger Denied Boarding Cancellation and Delay CAR — 8 pages.
2. Refund of Airline Tickets CAR — 3 pages.
3. Persons with Disability and Reduced Mobility CAR — 13 pages.
4. Accessibility Standards and Guidelines for Civil Aviation 2022 — 110 pages.

The complete file list and SHA-256 fingerprints are recorded in `data/manifest.jsonl`.

### 3. Access and Permission Review

- Source register: `data/sources.csv`.
- Source licence descriptions have been recorded.
- Publisher-specific permission to download, store and display all source documents has not been fully confirmed.
- The downloader uses `download_approved` checks and defaults to blocking unapproved sources.
- No unverified permission has been treated as approval.

### 4. Robots.txt and Access Restrictions

| Source | Result |
|---|---|
| IndiGo Conditions of Carriage | Blocked by robots.txt |
| Air India Conditions of Carriage | Blocked by robots.txt |
| Carriage by Air Act 1972 | HTTP 403 |
| Compensation Guidelines | HTTP 403 |
| Passenger Charter February 2019 | HTTP 403 |
| Ministry of Civil Aviation Passenger Grievance | HTTP 403 |
| Passenger Baggage Rules and Information | Homepage/fallback HTML; excluded |
| DGCA Passenger Information FAQs | Homepage/fallback HTML; excluded |

No blocked requests were bypassed.

HTTP 403 and robots.txt restrictions were treated as access limitations, not as reasons to bypass publisher controls.

### 5. Kill and Resume

- Run 1: Real interruption drill not performed.
- Run 2: Real resume run not performed.
- Run 3: Completed-download skip verification was covered by automated tests, but a separate live run is not recorded.

The automated tests cover resume and manifest behaviour. The real three-run exercise remains pending.

### 6. Capacity Measurements

The measured D06 corpus contains 134 pages, 192,381 characters and approximately 28,084 tokens.

The updated `docs/CAPACITY.md` estimates the 1,200-page target using the current measurements.

Planning estimates:

| Metric | Estimate for 1,200 pages |
|---|---:|
| Scale factor | 8.96x |
| Tokens | Approximately 251,600 |
| Raw files | Approximately 272.5 MiB |
| Chunks | Approximately 723 |
| One-time embedding cost | Approximately $0.044 (Rs 4.20) |
| Vector storage | Approximately 2.12 MiB |
| Text storage | Approximately 1.98 MiB |

These are estimates based on stated assumptions, not actual production measurements.

The free PostgreSQL storage limit must be checked against the database dashboard before confirming that the complete corpus will fit.

### 7. What Went Wrong and How It Was Handled

Some airline sources were blocked by robots.txt. Several government sources returned HTTP 403 or homepage fallback HTML instead of the expected documents.

Publisher-specific download and storage permissions were not fully confirmed.

Collection was limited to the documents available in the measured corpus. Blocked sources were not bypassed, and invalid fallback HTML files were excluded from the valid PDF corpus.

### 8. Documentation and Git Verification

Updated files:

- `DATASET.md`
- `docs/CAPACITY.md`

The dataset documentation records the four valid PDFs, 134 pages, source gaps and access restrictions.

The capacity documentation records the measured corpus, full-corpus estimates and four required conclusions.

Documentation commit:

`c1891c1` — `docs: update dataset and capacity measurements`

Pull Request #35 was merged into `main`.

Final merge commit:

`996f111` — Merge pull request #35.

The local `main` branch was verified as synchronized with `origin/main`, with a clean working tree.

### 9. Remaining D06 Work

- Complete the real Ctrl+C interruption-and-resume drill using an approved source.
- Verify publisher-specific download and storage permissions.
- Collect additional permitted documents toward the 1,200+ page target.
- Compare estimated database storage with the actual free PostgreSQL storage limit.
- Record the actual live interruption and resume measurements when the drill is performed.

**D06 conclusion:** Downloader implementation, automated tests, dataset reporting, capacity reporting and documentation merge are completed. The live resume drill, complete source permissions and 1,200+ page corpus target remain outstanding.

---

## D07 · PDF Parsing Quality Notes

### 1. Parsing Implementation

- Implemented PDF and HTML parsing.
- Stored extracted pages in PostgreSQL.
- Added heading and table extraction support.
- Added `parse_failures` tracking.
- Added OCR fallback for scanned PDFs.
- Used PyMuPDF as the primary PDF parser.

### 2. Parsing Results

The manifest contains 13 downloaded entries representing 12 unique files.

Two HTML files were found to have identical SHA-256 hashes:

- `digigov-portal-4fd04e37.html`
- `digigov-portal-e95b6f2d.html`

The parser deduplicates files with identical content, explaining why 13 manifest entries correspond to 12 unique parsed documents.

Final database inventory:

| Document type | Count |
|---|---:|
| PDF | 11 |
| HTML | 1 |
| Total parsed documents | 12 |

Total stored pages: **1,289**.

Outstanding parse failures: **0**.

### 3. OCR Recovery

Two scanned DGCA PDFs initially failed with `no_text_layer`.

Tesseract 5.5.3.20260724 was installed with English language support.

Command:

```powershell
uv run python scripts/parse_corpus.py --retry-failed --ocr eng --limit 20
```

Both scanned documents were recovered.

| Document | Pages | Extracted characters |
|---|---:|---:|
| Refund of Airline Tickets CAR | 3 | 5,721 |
| Persons with Disability and Reduced Mobility CAR | 13 | 33,770 |

Manual inspection confirmed readable OCR text across all three pages of the Refund of Airline Tickets CAR.

### 4. Parser Idempotency

The parser was executed again after successful parsing.

The repeated runs reported all 13 manifest entries as already parsed, with zero additional pages created.

This confirmed that repeated parsing did not create duplicate document pages.

### 5. Parser Comparison

Compared PyMuPDF and pypdf on ten representative files.

Findings:

- PyMuPDF extracted more characters and was faster on seven annual reports.
- For `upload-5246a2aa.pdf`, PyMuPDF detected 56 tables, while pypdf detected zero.
- Neither parser extracted text from the two scanned PDFs without OCR.

**Conclusion:** PyMuPDF is the preferred primary parser for the tested documents. Tesseract OCR is used as a fallback for scanned PDFs.

### 6. Manual Extraction Inspection

**Civil Aviation Requirements**

- Extracted text was available.
- Headings were detected on subsequent pages.
- Some initial pages had empty heading arrays.
- Section headings such as `SECTION 3 – AIR TRANSPORT` and `3.3 Cancellation of Flight` were identified.

**Accessibility Standards and Guidelines — Project Team**

- Text extraction was verified.
- Headings including `Project Team`, `Disclaimer`, `Preface`, and `Acknowledgement` were identified.
- Repeated headings and some front-matter extraction artifacts were observed.
- PyMuPDF detected 56 tables.

**Refund of Airline Tickets CAR**

- OCR text was recovered across all three pages.
- Heading extraction returned empty heading arrays.
- The extracted text was manually checked and found readable.

### 7. Known Limitations

- Scanned PDFs require OCR.
- OCR heading extraction may return empty heading arrays.
- Repeated headers and headings can occur.
- Front-matter page ordering and extraction quality may require improvement.
- Higher character counts do not guarantee accurate extraction of financial figures or numerical tables.
- Legacy Tamil fonts may require additional Unicode conversion or OCR handling.

### 8. Final Verification

| Verification | Result |
|---|---|
| Downloaded manifest entries | 13 |
| Unique downloaded files | 12 |
| Parsed documents | 12 |
| Stored pages | 1,289 |
| Outstanding parse failures | 0 |
| OCR recovery | 2 documents |
| Parser comparison | 10 files |
| Parser idempotency | Verified |
| Production health | Healthy |
| Production readiness | Ready |

Production version verified:

`c31d669393e8119582b04687a3b64f946720d1ae`

### 9. D07 Completion Checklist

- [x] PDF and HTML parsing implemented.
- [x] Parsed content stored in PostgreSQL.
- [x] Heading and table extraction tested.
- [x] Parse failure tracking verified.
- [x] All 12 unique downloaded files parsed.
- [x] Both scanned PDFs recovered using English OCR.
- [x] Parser idempotency verified.
- [x] PyMuPDF and pypdf compared on ten files.
- [x] Three documents manually inspected.
- [x] Corpus coverage reconciled using SHA-256 hashes.
- [x] Production deployment verified.

**D07 conclusion:** PDF parsing, OCR recovery, parser comparison, database verification, and corpus reconciliation completed.

---

## D09 · Streaming Chat API and LLM Gateway Experiments

### 1. Chat API Implementation

- Added versioned system prompt: `prompts/chat_system_v1.md`.
- Added `POST /v1/chat` with streaming Server-Sent Events (SSE).
- Added non-streaming JSON responses.
- Added `GET /v1/usage` for daily usage and cost summaries.
- Integrated the API with the LLM gateway and usage recorder.
- Added dependency overrides and fake LLM fixtures for unit tests.
- Added `scripts/ask.py` to test the API and measure response timing.

### 2. Automated Tests and Code Quality

Chat API tests:

```text
7 passed
```

Complete unit test suite:

```text
89 passed, 1 warning
```

Code quality:

```text
uv run poe lint

Ruff checks: All checks passed!
Ruff format: 64 files already formatted
```

The warning relates to the optional PySocks dependency.

### 3. Real API Verification

Verified the following endpoints:

- `POST /v1/chat` with streaming enabled.
- `POST /v1/chat` with JSON responses.
- `GET /v1/usage`.

Both streaming and JSON requests successfully returned answers through the Groq fallback provider.

Recorded streaming cancellation test:

```text
Provider: groq
Model: openai/gpt-oss-20b
First words: 61.59 seconds
Total time: 62.49 seconds
Input tokens: 237
Output tokens: 559
Cost: Rs 0.017620
Fallback: YES
```

Recorded JSON denied-boarding test:

```text
Provider: groq
Model: openai/gpt-oss-20b
Total time: 62.40 seconds
Input tokens: 232
Output tokens: 225
Cost: Rs 0.008065
Fallback: YES
```

### 4. Token Comparison

Compared three requests using the same system prompt and Groq fallback.

| Message | Input tokens | Output tokens |
|---|---:|---:|
| Hi | 228 | 109 |
| English refund question | 241 | 282 |
| Tamil refund question | 252 | 249 |

Input token differences relative to "Hi":

- English refund question: +13 tokens.
- Tamil refund question: +24 tokens.

These differences include the effect of the system prompt and provider tokenization. They are not standalone message-token counts.

### 5. Off-topic and Flight Status Tests

Off-topic question:

```text
Who won the 2011 cricket world cup?
```

The assistant responded:

```text
This question is outside FlyRight's subject.
```

Flight status question:

```text
Is my flight on time today?
```

The assistant explained that it could not access real-time flight status and directed the passenger to check the airline or a flight-tracking service.

Both tests behaved appropriately for the current application scope.

### 6. Passenger Rights Answer Checks

Tested cancellation, delay assistance and denied boarding questions.

The assistant generated responses for all three scenarios using Groq fallback.

However:

- Document retrieval is not connected to the chat endpoint yet.
- Legal claims were not independently verified against the source documents.
- The denied-boarding response included specific compensation percentage claims that require verification.
- The chat prompt instructs the model not to invent legal references and to direct users to official sources for current fees, deadlines and eligibility.

These experiments demonstrate response generation, not verified legal accuracy.

### 7. Invalid Primary Model and Fallback Test

Temporarily changed the primary model configuration to:

```text
LLM_PRIMARY_MODEL=gemini-no-such-model
```

The `.env` file was backed up before the experiment and restored afterwards.

Groq successfully answered the test requests when the primary provider failed.

The circuit breaker configuration was inspected:

```text
Failure threshold: 3
Cooldown: 30 seconds
```

A request was also made after the cooldown period. The response metadata confirmed Groq fallback, but did not independently prove the internal half-open state.

The original primary model setting was restored:

```text
LLM_PRIMARY_MODEL=gemini-3.8-flash
```

### 8. Gemini Quota Investigation

The Neon `llm_calls` table was inspected to identify the primary provider failure.

Observed Gemini errors included:

- HTTP 429: Current quota exceeded.
- HTTP 503: Model temporarily experiencing high demand.
- ReadTimeout: Request timed out.

Google AI Studio Rate Limits dashboard showed:

| Model | RPM | TPM | RPD |
|---|---:|---:|---:|
| Gemini 3.8 Flash | 2 / 5 | 8.1K / 250K | 23 / 20 |
| Gemini 3.6 Flash | 1 / 5 | 75.15K / 250K | 2 / 20 |

Gemini 3.8 Flash exceeded its displayed daily request limit.

The primary model's successful operation after quota reset remains pending verification.

The fallback provider continued serving chat requests successfully.

### 9. Usage Tracking

A usage endpoint snapshot during testing reported:

```text
Date: 2026-11-26
Calls: 23
Errors: 11
Fallbacks: 12
Input tokens: 2,832
Output tokens: 2,708
Cost: Rs 0.0974
```

These figures represent the usage snapshot at the time of the experiment, not the final lifetime totals.

The `llm_calls` database table stores provider, model, status, error, token counts, latency, cost and fallback information.

### 10. Day 9 Outstanding Verification

- Confirm Gemini primary responses after the daily quota resets.
- Verify circuit-breaker half-open behaviour independently.
- Verify individual provider usage records against the final usage endpoint totals.
- Continue checking legal responses against authoritative DGCA documents when retrieval is implemented.
- Record a successful Gemini-primary response when quota becomes available.

### 11. Day 9 Conclusion

The streaming chat API, JSON response mode, usage endpoint, versioned prompt, automated tests and Groq fallback were implemented and tested.

The Gemini primary provider encountered quota exhaustion and temporary availability errors. The fallback mechanism allowed the API to continue answering requests.

**Day 9 implementation and fallback experiments are verified. Successful Gemini-primary operation after quota reset remains pending.**
