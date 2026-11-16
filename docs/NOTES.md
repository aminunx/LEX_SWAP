# Running notes

Appended as work happens, newest last. Errors and dead ends are kept — the
methodology in [`METHODOLOGY.md`](METHODOLOGY.md) is distilled from this file,
and a lesson with its history removed is just an assertion.

---

## 2026-11-16 · The owner's correction, and why it was a diagnosis

> «مشكلتك هي انك تريد تغيير كل شي دفعة واحدة قسمها على خطوات ثم ابدء بتغييرت
> ببعض الكلمات التي ستنتج بعض الجمل وجرب وكرر وكبر»

This was not project management. It was a diagnosis, and it was proved correct
within one run.

The full-vocabulary runs moved five things at once — coverage, collisions, word
sense, word order, morphology. On that basis a confident causal story was
built: *word order is the wall*. Its first controlled test killed it
(Indonesian 0% vs Dutch 12% on exactly that group).

With five variables moving, I believed I knew which one was responsible, and I
did not.

**The measured vindication:**

| lexicon | method | accuracy |
|---|---|---|
| 14,860 | machine-translated | 21% |
| 10,820 | + round-trip verified | 32% |
| **63** | **hand-made** | **67%** |
| 2,244 | seed + verified growth | **83%** |

63 hand-picked pairs beat 10,820 machine-translated ones by two to three times.

## 2026-11-16 · Rung 0 failed its own gate, and that was the point

100% coverage, 67% accuracy, and **0 of 12 id matches**. The accuracy looked
like success.

Cause: byte-level BPE encodes `"The book"` as `["The", " book"]`, so position 0
carries no leading space. Mapping every Dutch word to its space-prefixed English
id got positions 1..n right and position 0 wrong on every prompt.

**Without the identity gate this would have been written up as a fact about
Dutch** — the identical mistake as the word-order story, one layer down.

Fix: two tables, by position. Result 11/12.

## 2026-11-16 · The twelfth prompt, and fixing the class instead of the case

`Brood en` stayed at 0.50 coverage. `" bread"` is one token; `"Bread"` is not.
So the sentence-initial form did not exist and the word fell back.

The tempting fix is to special-case multi-token capitals. The better fix is to
**delete the category**: prepend one space to every prompt in every arm, and
every word — including the first — is space-prefixed. One table, no position-0
case, nothing to except.

A fix that removes a class of bugs beats a fix that handles an instance.

## 2026-11-16 · Two predictions failed in one run

**Predicted:** growing the lexicon injects translation noise, so accuracy falls.
**Measured:** 67% → 83%.

**Predicted:** Indonesian beats Dutch on word order, being SVO with no
conjugation. **Measured:** Indonesian 0%, Dutch 12%.

The first failed because of an axis I had named but never measured: **input
coverage is not output coverage**. All prompt words were in the seed, but the
model *generates* words outside it, which then render in the source language —
`cheese`, `total`, `naar con` inside otherwise correct Dutch. Growth was buying
output coverage, and that mattered more than the sense noise it added.

So output purity is now measured, not assumed. Naming an axis is not measuring
it, and I had been treating the two as the same thing for three runs.

## 2026-11-16 · Where the 83% must not be oversold

83% equals the source ceiling exactly — full preservation. But those 12 prompts
are **constructed to be word-for-word parallel with English**. They are English
in Dutch clothing, and they avoid the word-order problem by design.

Naturally written Dutch, same pipeline: **32%**.

The gap between 83% and 32% is the whole limitation of the method. Both numbers
are true; quoting either alone is a lie.

## 2026-11-16 · Still open

- 9,368 of 30,000 ids lost to collisions even after round-trip verification.
  MT on bare context-free words is a weak dictionary; a real bilingual lexicon
  is the next lever.
- Output purity now measured for the first time — no reading yet.
- The word-order gap is untouched, and no dictionary closes it. The question
  with commercial weight is how little *training* closes it, given that the swap
  is free.
