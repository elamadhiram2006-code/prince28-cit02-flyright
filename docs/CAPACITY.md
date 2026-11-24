\# Capacity plan: FlyRight



Full corpus target: + all relevant CARs, revisions and 4 airlines' terms (1,200+ pages)



<!-- generated:start -->

<!-- generated:end -->



\## What I conclude




1. **Embedding cost:** Not measurable yet because no documents have been downloaded; the estimate will use actual corpus tokens and the configured embedding price.
2. **Postgres storage:** Not measurable yet; compare the generated text and vector storage estimates with the actual free-tier database storage limit once measurements are available.
3. **Least certain number:** Estimated tokens, because characters divided by four is only a rough approximation; measure actual tokenizer output on a representative sample.
4. **10x corpus growth:** Text storage, vector storage, and embedding cost will increase approximately 10x if document size and processing settings remain similar. Recheck database capacity and embedding budget before expanding.
