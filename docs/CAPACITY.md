\# Capacity plan: FlyRight



Full corpus target: + all relevant CARs, revisions and 4 airlines' terms (1,200+ pages)



<!-- generated:start -->
## Measured on my start corpus (2026-11-24 15:30 UTC)

| What | Value |
|---|---|
| Files | 6 |
| Size on disk | 32.3 MB |
| Pages (PDF pages + 1 per 3,000 characters of text/HTML) | 34 |
| Characters of text | 50,940 |
| Estimated tokens (characters / 4) | 12,735 |
| Tokens per page | 372 |
| PDFs with almost no text (scanned? OCR is Day 7) | 2 |
| Files not measured (zip, xlsx, unreadable) | 1 |

## Estimate for the full corpus (target: 1,200 pages)

| What | How | Value |
|---|---|---|
| Scale factor | target / measured | x 35.0 |
| Tokens | measured tokens x scale | 0.45 M |
| Raw files | measured MB x scale | 1,133 MB |
| Chunks | tokens / 400 x 1.15 overlap | 1,283 |
| Embedding cost, one time | tokens x 1.15 x $0.15 per 1M | $0.08 = Rs 7 |
| Vector storage | chunks x 768 numbers x 4 bytes | 4 MB |
| Text in Postgres | characters x scale x 1.2 | 2 MB |

Assumptions: 4 characters per token, 400-token chunks, 768-dimension embeddings at $0.15 per 1M tokens, Rs 95 per US dollar.
<!-- generated:end -->



\## What I conclude



1\. Is embedding cost a problem for this product? (1 line, with the number)

2\. Do the vectors and text fit in my free Postgres? (1 line: compare with the storage limit on my database dashboard)

3\. Which number above am I least sure about, and how will I measure it better? (1 line)

4\. What changes if the corpus grows 10 times? (2 lines)
