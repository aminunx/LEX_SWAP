# SPEC — "Vocabulary swap" experiment (NO retraining, NO weight changes)

Recorded verbatim from the project owner, 2026-11-16. This file is the contract.
Analysis of what it measures lives in `docs/what-this-measures.md` and does not
alter this text.

## Core idea

A causal LLM sees only integer token IDs. Its weights (embeddings, transformer
layers, lm_head) are never modified. Only the tokenizer ID <-> string table is
changed.

Example (original English vocab):

```
1    = "book"
2433 = "table"
567  = " the"
```

After the swap (Dutch), the SAME IDs map to the Dutch equivalents:

```
1    = "boek"
2433 = "tafel"
567  = " de"
```

Pipeline:

```
Dutch question -> (new vocab) -> IDs -> UNCHANGED model
-> output IDs -> (new vocab) -> Dutch text
```

The hypothesis: if internal representations are largely language-independent,
the model may answer sensibly in Dutch even though nothing was retrained.

## Steps

1. Load a small open causal LM (e.g. `Qwen/Qwen2.5-0.5B`) with Hugging Face
   transformers. Do not touch its weights.
2. Build `id2nl`: for every token ID in the first N entries (N=30000):
   - decode the token to its English string
   - if it is a whole alphabetic word, translate it to Dutch with
     `Helsinki-NLP/opus-mt-en-nl` (batched), keeping any leading space
   - if it is a digit, symbol, punctuation, code or special token, keep it
     unchanged
   - sub-word fragments (e.g. "ing", "ed") stay unchanged for now and are logged
3. Build `nl2id` as the inverse (first occurrence wins; log collisions where
   several IDs share one Dutch string).
4. Write a word-level `encode(text)` and `decode(ids)` using these tables. Do
   NOT edit the BPE merges file, because BPE merges are built for English and
   will not segment Dutch correctly. Unknown words fall back to the original
   tokenizer.
5. Run greedy generation (`do_sample=False`):
   - Baseline: English prompt with the original tokenizer.
   - Experiment: equivalent Dutch prompt with the swapped vocab.
6. Run at least 20 simple prompts (facts, completion, small arithmetic, short
   translation) and print a table:
   `English prompt | English answer | Dutch prompt | Dutch answer`
7. Report: number of tokens translated, number kept unchanged, number of
   collisions, and any observed failure patterns (English word order in the
   output, wrong word sense, etc.).

## Constraints

- No fine-tuning, no embedding edits, no extra training.
- Keep code short and runnable on CPU or a free Colab GPU.
- Be honest in the report: do not claim success unless the Dutch answers are
  actually correct and compared against the baseline.
- Ask me before assuming anything that is unclear.
