\# Day 3 – PostgreSQL Migration Notes



\## 1. Database Migration



Migration history verified using:



```powershell

uv run alembic history

```



Output:



```text

014aa435b676 -> 51ec6327ece4 (head), add gin index on metadata

<base> -> 014aa435b676, create documents and pages

```



\## 2. Migration Rollback Test



Commands executed:



```powershell

uv run alembic downgrade -1

uv run alembic current

uv run alembic upgrade head

```



The downgrade successfully reverted to migration `014aa435b676`.



The upgrade successfully restored migration `51ec6327ece4`.



\## 3. Database Loader



The loader uses SHA-256 fingerprints to detect inserted, updated, and unchanged records.



Latest verified output:



```text

records=20 inserted=0 updated=1 unchanged=19

```



\## 4. GIN Index Verification



Command:



```powershell

uv run python scripts/explain.py rule "3.2.1 - Volunteers for denied boarding"

```



\### Normal query plan



```text

Seq Scan on documents

Rows Removed by Filter: 19

Execution Time: 2.171 ms

```



PostgreSQL selected a sequential scan because the table contains only 20 records.



\### Query plan with sequential scans disabled



```text

Bitmap Heap Scan on documents

&#x20; -> Bitmap Index Scan on ix\_documents\_metadata\_gin

```



Execution time: 0.922 ms.



This confirms that the GIN index is available and can accelerate JSONB containment queries.



\## 5. Test Results



```text

9 passed, 3 skipped

```



The three integration tests are skipped when `TEST\_DATABASE\_URL` is not configured.



\## 6. Code Quality



Command:



```powershell

uv run ruff check .

```



Result:



```text

All checks passed!

```
