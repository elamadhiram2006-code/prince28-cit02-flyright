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

Verified response:

```json
{
  "status": "ok",
  "app": "flyright",
  "env": "production",
  "version": "afb4d93"
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

Both endpoints returned successful responses.

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

**CI run for the first required pull request:**

[Add the exact GitHub Actions run link here.]

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

**First automatic CD deployment run:**

[Add the exact successful CD run link here.]

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

Verified live `/health` response:

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

After the rollback drill, the application was rolled forward to the latest main commit.

**Roll-forward commit:** `afb4d93`

Verified live `/health` response:

```json
{
  "status": "ok",
  "app": "flyright",
  "env": "production",
  "version": "afb4d93"
}
```

The live application successfully returned to the latest main version.

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
- Verified monitoring status: Up.

The uptime monitor checks the live health endpoint regularly.

### 11. Deployment Timing Evidence

- Merge clicked at: [Fill in time]
- Smoke test passed at: [Fill in time]
- Automatic deployment lead time: [Fill in minutes]
- Rollback duration: [Fill in minutes]
- Roll-forward duration: [Fill in minutes]

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
