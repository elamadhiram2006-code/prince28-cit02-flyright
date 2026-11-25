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

#### Normal query plan

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

#### Query plan with sequential scans disabled

```text
Bitmap Heap Scan on documents  (cost=8.54..12.55 rows=1 width=36) (actual time=0.872..0.873 rows=1.00 loops=1)
  Recheck Cond: (metadata @> '{"rule": "3.2.1 - Volunteers for denied boarding"}'::jsonb)
  Heap Blocks: exact=1
  Buffers: shared hit=2 read=1
  -> Bitmap Index Scan on ix_documents_metadata_gin  (cost=0.00..8.54 rows=1 width=0) (actual time=0.833..0.833 rows=1.00 loops=1)
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

Result:

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

Result:

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

Latest previously verified production response:

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

Latest result:

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

The current valid documents are:

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

The following access issues were recorded:

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

The current corpus contains 134 pages, 192,381 characters and approximately 28,084 tokens.

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

**Current D06 conclusion:** Downloader implementation, automated tests, dataset reporting, capacity reporting and documentation merge are completed. The live resume drill, complete source permissions and 1,200+ page corpus target remain outstanding.

---

## D07 · PDF Parsing Quality Notes

### 1. Initial Parsing Results

- 13 downloaded files were eligible for parsing.
- The initial run successfully parsed 10 files.
- One file was already parsed and skipped.
- Two DGCA PDF files initially failed with `no_text_layer`.
- The initial run extracted and stored 1,273 pages in PostgreSQL.
- PDF text extraction using PyMuPDF was working.
- Some extracted headings were noisy and contained dates or names instead of meaningful section titles.
- Some extracted text contained character recognition errors.
- Repeated report headers appeared in page text.
- The document title "World-Class Civil Aviation Infrastructure" looked reasonable.
- Scanned PDFs required OCR.

### 2. Full Parsing and Failure Review

- Ran the full parser twice successfully after OCR recovery.
- Both final runs reported 13 files and 13 already parsed.
- The second run created 0 additional pages, confirming idempotency.
- Queried `parse_failures`: 0 outstanding failures.
- Both scanned PDFs were successfully recovered using English OCR.

### 3. OCR Recovery

The two scanned DGCA PDFs initially failed because they did not contain an extractable text layer.

Tesseract English OCR was used to recover them:

```powershell
uv run python scripts/parse_corpus.py --retry-failed --ocr eng --limit 20
```

The retry successfully parsed both previously failed files.

| Failure reason | Initial failures | Final status |
|---|---:|---|
| `no_text_layer` | 2 | Both recovered using English OCR |

### 4. Parsing My Corpus

| Metric | Result |
|---|---:|
| Files eligible for parsing | 13 |
| Files successfully parsed or already parsed | 13 |
| Outstanding parse failures | 0 |
| Parsing coverage | 100% |
| Pages stored in PostgreSQL | **VERIFY WITH SQL** |

To verify the exact page count:

```sql
SELECT COUNT(*) AS total_pages
FROM pages;
```

### 5. Parser Comparison

The comparison script evaluated ten files using PyMuPDF and pypdf.

| File | Parser A | A chars | A tables | A sec | Parser B | B chars | B tables | B sec | Better parser and why |
|---|---|---:|---:|---:|---|---:|---:|---:|---|
| `data\raw\moca\annual-report-2023-24.pdf` | PyMuPDF | 496259 | 0 | 8.61 | pypdf | 474632 | 0 | 26.61 | PyMuPDF — more characters and faster |
| `data\raw\moca\annual-report-2024-25.pdf` | PyMuPDF | 411622 | 0 | 5.6 | pypdf | 393736 | 0 | 17.3 | PyMuPDF — more characters and faster |
| `data\raw\moca\annual-report-2019-20.pdf` | PyMuPDF | 241644 | 0 | 3.56 | pypdf | 232601 | 0 | 10.9 | PyMuPDF — more characters and faster |
| `data\raw\moca\annual-report-2022-23.pdf` | PyMuPDF | 373203 | 0 | 3.45 | pypdf | 352436 | 0 | 15.99 | PyMuPDF — more characters and faster |
| `data\raw\moca\annual-report-2018-19.pdf` | PyMuPDF | 329314 | 0 | 3.2 | pypdf | 315241 | 0 | 13.41 | PyMuPDF — more characters and faster |
| `data\raw\moca\annual-report-2020-21.pdf` | PyMuPDF | 337711 | 0 | 3.21 | pypdf | 327971 | 0 | 12.62 | PyMuPDF — more characters and faster |
| `data\raw\moca\annual-report-2021-22.pdf` | PyMuPDF | 333601 | 0 | 3.69 | pypdf | 308015 | 0 | 16.73 | PyMuPDF — more characters and faster |
| `data\raw\dgca\upload-5246a2aa.pdf` | PyMuPDF | 191275 | 56 | 13.16 | pypdf | 162365 | 0 | 6.76 | PyMuPDF — extracted 56 tables and more characters |
| `data\raw\dgca\upload-2b704f8c.pdf` | PyMuPDF | 0 | 0 | 0.05 | pypdf | 0 | 0 | 0.01 | Neither — zero text; OCR required |
| `data\raw\dgca\upload-f576f41e.pdf` | PyMuPDF | 0 | 0 | 0.1 | pypdf | 0 | 0 | 0.0 | Neither — zero text; OCR required |

**Comparison conclusion:**

PyMuPDF is the preferred parser for the tested annual reports because it extracted more characters and completed faster than pypdf.

PyMuPDF is also preferred for `upload-5246a2aa.pdf` because it extracted 56 tables, whereas pypdf extracted none.

Neither parser can effectively extract text from the two scanned PDFs without OCR.

### 6. Manual Inspection of Parsed Documents

At least three parsed documents must be manually inspected in PostgreSQL.

For each document, verify:

- Document title and page number.
- Extracted text and heading path.
- Whether the heading path is meaningful and correctly ordered.
- Whether any text is missing, duplicated or incorrectly extracted.
- Whether tables are preserved as structured data or readable text.

Example query:

```sql
SELECT
    d.title,
    p.page_no,
    p.headings,
    LEFT(p.text, 600) AS start_of_page
FROM pages p
JOIN documents d ON d.id = p.document_id
ORDER BY d.title, p.page_no
LIMIT 15;
```

**Manual inspection findings — complete after checking three documents:**

- Document 1: PENDING INSPECTION.
- Document 2: PENDING INSPECTION.
- Document 3: PENDING INSPECTION.
- Heading path correctness: PENDING INSPECTION.
- One extraction issue observed: PENDING INSPECTION.
- One table example: PENDING INSPECTION.

### 7. Parser Choice for Documents Containing Numbers

PyMuPDF is preferred for the tested annual reports because it extracted more characters and was faster in the comparison.

For documents containing financial figures, tables, dates and numerical data, the extracted values and table structure should also be checked manually. A higher character count alone does not guarantee numerical accuracy.

### 8. Document Types That Need Special Handling

Scanned image-only PDFs are not handled effectively by either PyMuPDF or pypdf without OCR.

Tesseract OCR successfully recovered the two scanned DGCA PDFs.

Tamil text stored in legacy non-Unicode fonts may also require a Unicode source or a suitable OCR workflow.

### 9. What Went Wrong and How It Was Fixed

Two DGCA PDFs initially failed because they had no extractable text layer.

The parser recorded the failures using the `no_text_layer` reason. The files were retried using Tesseract English OCR, and both were successfully recovered.

Some annual-report headings and extracted text also contained noise, including repeated headers and recognition errors. Manual quality inspection is required to identify and document these extraction issues.

### 10. D07 Completion Checklist

- [x] Implemented PDF and HTML parsing.
- [x] Stored parsed pages in PostgreSQL.
- [x] Added heading and table extraction support.
- [x] Added `parse_failures` tracking.
- [x] Parsed the available 13 eligible files.
- [x] Recovered both initial scanned-PDF failures using English OCR.
- [x] Verified that rerunning the parser does not create duplicate pages.
- [x] Compared PyMuPDF and pypdf on ten files.
- [ ] Verified exact final page count in
