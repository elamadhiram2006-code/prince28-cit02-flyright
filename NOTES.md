\# Engineering Notes: FlyRight



\## D03 · PostgreSQL



\### 1. Database Migrations



Migration history was verified using:



```powershell

uv run alembic history

```



Output:



```text

014aa435b676 -> 51ec6327ece4 (head), add gin index on metadata

<base> -> 014aa435b676, create documents and pages

```



\### 2. Migration Rollback Test



Commands executed:



```powershell

uv run alembic downgrade -1

uv run alembic current

uv run alembic upgrade head

```



The downgrade successfully reverted to migration `014aa435b676`.



The upgrade successfully restored migration `51ec6327ece4`.



\### 3. Database Loader Idempotency



The loader uses SHA-256 fingerprints to detect inserted, updated, and unchanged records.



Latest verified output after editing one record:



```text

records=20 inserted=0 updated=1 unchanged=19

```



The loader detected one updated record and left the other 19 unchanged.



\*\*Remaining evidence:\*\* Add the actual first-run and second-run outputs to complete the required three-run demonstration.



\### 4. GIN Index Verification



Command:



```powershell

uv run python scripts/explain.py rule "3.2.1 - Volunteers for denied boarding"

```



\#### Normal query plan



```text

Seq Scan on documents  (cost=0.00..3.25 rows=1 width=36) (actual time=2.140..2.140 rows=1.00 loops=1)

&#x20; Filter: (metadata @> '{"rule": "3.2.1 - Volunteers for denied boarding"}'::jsonb)

&#x20; Rows Removed by Filter: 19

&#x20; Buffers: shared read=3 dirtied=3

Planning:

&#x20; Buffers: shared hit=117 read=8 dirtied=1

Planning Time: 6.343 ms

Execution Time: 2.171 ms

```



\#### Query plan with sequential scans disabled



```text

Bitmap Heap Scan on documents  (cost=8.54..12.55 rows=1 width=36) (actual time=0.872..0.873 rows=1.00 loops=1)

&#x20; Recheck Cond: (metadata @> '{"rule": "3.2.1 - Volunteers for denied boarding"}'::jsonb)

&#x20; Heap Blocks: exact=1

&#x20; Buffers: shared hit=2 read=1

&#x20; -> Bitmap Index Scan on ix\_documents\_metadata\_gin  (cost=0.00..8.54 rows=1 width=0) (actual time=0.833..0.833 rows=1.00 loops=1)

&#x20;      Index Cond: (metadata @> '{"rule": "3.2.1 - Volunteers for denied boarding"}'::jsonb)

&#x20;      Index Searches: 1

&#x20;      Buffers: shared hit=1 read=1

Planning:

&#x20; Buffers: shared hit=1

Planning Time: 0.087 ms

Execution Time: 0.922 ms

```



\*\*Why did PostgreSQL choose Seq Scan?\*\*



The documents table contains only 20 records. Scanning all rows is inexpensive for such a small table.



\*\*When would PostgreSQL switch to the GIN index?\*\*



PostgreSQL may choose the GIN index when the table grows and using the index becomes cheaper than scanning every row.



\### 5. Test Results



Command:



```powershell

uv run pytest -v

```



Result:



```text

16 passed, 3 skipped in 0.33s

```



The three integration tests are skipped when `TEST\_DATABASE\_URL` is not configured.



\### 6. Code Quality



Command:



```powershell

uv run ruff check .

```



Result:



```text

All checks passed!

```
