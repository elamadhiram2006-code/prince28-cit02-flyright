
# Capacity Plan: FlyRight

Full corpus target: All relevant CARs, revisions and four airlines' terms (1,200+ pages).

## Measured on the current corpus

Measurement date: 2026-11-24

| Metric | Measured value |
|---|---:|
| Valid unique documents | 4 |
| Total pages | 134 |
| Total characters | 192,381 |
| Estimated tokens | 28,084 |
| Size on disk | 30.42 MiB |
| Unavailable or excluded sources | 8 |

## Estimate for the full corpus

Target: 1,200 pages.

Assumptions:
- 4 characters per token (approximation).
- 400-token chunks.
- 15% chunk overlap.
- 768-dimensional embeddings.
- 4 bytes per vector dimension.
- Embedding price assumption: $0.15 per million tokens.
- Exchange-rate assumption: Rs 95 per US dollar.

| Metric | Calculation | Estimate |
|---|---|---:|
| Scale factor | 1,200 / 134 | 8.96x |
| Estimated tokens | 28,084 x 8.96 | 251,600 |
| Raw files | 30.42 MiB x 8.96 | 272.5 MiB |
| Chunks | 251,600 / 400 x 1.15 | 723 |
| One-time embedding cost | 251,600 x 1.15 x $0.15 / 1M | $0.044 (about Rs 4.20) |
| Vector storage | 723 x 768 x 4 bytes | 2.12 MiB |
| Text storage | 192,381 x 8.96 x 1.2 bytes | 1.98 MiB |

These are planning estimates, not measured production storage or billing figures. Actual database overhead, indexes and embedding dimensions may change the result.

## What I conclude

1. **Is embedding cost a problem?** No. At the 1,200-page target, the estimated one-time embedding cost is approximately $0.044 (Rs 4.20), using the stated pricing assumption.

2. **Do vectors and text fit in free Postgres?** The estimated vector and text payload is approximately 4.1 MiB. This should be compared with the actual storage limit and current usage shown in the database dashboard before confirming.

3. **Which number am I least sure about?** Estimated tokens are uncertain because PDF text extraction, scanned pages and OCR can change token counts. I will improve this by measuring extracted text and actual tokenizer output for every document.

4. **What changes if the corpus grows 10 times?** Token volume, chunk count, embedding cost and storage requirements will grow approximately 10 times, assuming similar documents. I will need to monitor PostgreSQL storage, indexing performance and embedding costs as the corpus expands.

## Current progress

| Target | Goal | Current | Progress |
|---|---:|---:|---:|
| Pages | 1,200 | 134 | 11.2% |
| Files | 2,500 | 4 | 0.16% |

The corpus targets have not yet been reached. Continue collecting only permitted and relevant documents.

<!-- BEGIN GENERATED CONTENT -->

**Last updated:** 2026-11-24

## Corpus measurements

| Metric | Current value |
|---|---:|
| Unique documents | 6 |
| Total pages | 588 |
| Total characters | 192,381 |
| Estimated tokens | 28,084 |
| Total size | 142.87 MiB |
| Unavailable or excluded sources | 8 |

## Capacity targets

| Target | Goal | Current | Progress |
|---|---:|---:|---:|
| Full pages | 1,200 | 588 | 49.0% |
| Full files | 2,500 | 6 | 0.2% |

## Status

Corpus targets have not yet been reached. Continue collecting permitted, relevant documents.

<!-- END GENERATED CONTENT -->
