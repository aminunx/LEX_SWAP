# Methodology: translating a language model by swapping its vocabulary

A working playbook, written from the errors that produced it. Every rule below
exists because something went wrong and was caught — the measured numbers are
included so the rules are evidence, not opinion.

**Scope.** Replacing a causal LM's tokenizer ID ↔ string table so it accepts and
emits another language, with **no fine-tuning, no embedding edits, no training
of any kind**.

---

## 0. What the method can and cannot do

State this before anything else, because every overclaim in this project came
from skipping it.

The model never sees text. It sees integer ids. So substitution happens entirely
**outside** the network, at both ends, and the arithmetic inside is
byte-identical. The system is:

```
target language → [dictionary] → English ids → MODEL → ids → [dictionary] → target
```

| | |
|---|---|
| **It measures** | how much meaning a word-for-word lexical substitution preserves between two languages |
| **It does not measure** | whether internal representations are language-independent — they are never shown the target language |
| **Its ceiling** | word-for-word translation quality, not the model's quality |

**Measured bound.** On prompts constructed to be word-for-word parallel with
English, the swap reached **83% against the English baseline's 83%** — full
preservation. On *naturally written* Dutch with its own word order, the same
pipeline reached **32%**. The gap between those two numbers is the entire
limitation of the method, and it is word order.

So the honest claim is:

> ✅ A vocabulary swap preserves model capability **where the target language's
> word order matches the source's**, and degrades in proportion to how much it
> does not.

> ❌ "A Dutch model with no training." The system is an English model between two
> dictionary layers.

### Prior art

Vocabulary-and-embedding replacement for cross-lingual transfer is an
established line of work — `WECHSEL`, `FOCUS`, `Trans-Tokenization`,
`Zero-Shot Tokenizer Transfer` are the names to check. **Every method in that
line follows the swap with training**, which is itself the strongest evidence
that the swap alone is insufficient. The no-training variant reduces to
dictionary-based machine translation, which is 1950s technology that failed for
exactly the reason measured here.

What is contributable is **the measurement**: a controlled anatomy of what
survives and what breaks. Not the method.

---

## 1. Correctness gates — run these before any experiment

This is the single most valuable thing in this document. Four of the five
mistakes below were invisible in aggregate accuracy and would have been
attributed to *language* rather than to *code*.

### Gate 1 — the identity test

Build a small hand-made lexicon and a set of prompts that are **word-for-word
parallel** between source and target through that lexicon.

> The swapped prompt must encode to **the same token ids** as its source twin,
> and therefore produce a **byte-identical** continuation.

If it does not, the codec is broken. **Stop.** No higher measurement means
anything.

**Evidence.** The first clean run scored 67% accuracy with 100% coverage and
looked like a success. The identity gate reported **0 of 12 id matches**. The
bug was real (§2.1), and without the gate it would have been written up as a
fact about Dutch.

### Gate 2 — a reference anchor that must read a known value

Include one condition whose answer is fixed **by construction**, and assert it.

**Evidence** (from the sister project, same lesson): an intervention added to a
network's final residual stream passes through nothing but the final layer-norm,
so its amplification ratio must be exactly `1.00`. It read `0.30`. The anchor
caught a double-applied layer-norm in the primary metric. After the fix it read
`1.0000`.

### Gate 3 — the all-pass guard

> If **every** condition passes, the control is too weak and the run is void.

**Evidence.** Six of six "passed" with z-scores up to 475. The pre-registered
guard voided the run and the diagnosis found an invalid decomposition. The guard
had been written for a different reason entirely and caught an error nobody
anticipated — which is the practical argument for pre-registration, stronger
than the theoretical one.

### Gate 4 — weights verified, not assumed

Clone a slice of `state_dict()` before the run, compare after, print the result.
"No training" is a claim; make it an assertion.

---

## 2. The error log

### 2.1 The sentence-initial token is a different token

**Severity: total.** Broke every prompt, invisibly.

Byte-level BPE encodes `"The book"` as `["The", " book"]`. The first word of a
sentence carries **no leading space** and is capitalised; every later word
carries one. Mapping every target word to its space-prefixed source id gets
positions `1..n` right and position `0` wrong, every time.

- **Symptom:** 100% coverage, 0/12 id matches, 67% accuracy that looked fine.
- **Fix:** two tables — mid-sentence and sentence-initial — selected by position.
- **After:** 11/12 id matches.

### 2.2 Capitalised forms are not always single tokens

`" bread"` is one token; `"Bread"` may be two. When the sentence-initial form is
multi-token, that word silently falls back and coverage drops.

- **Symptom:** one prompt stuck at 0.50 coverage, mean coverage pinned at 95.8%.
- **Fix:** verify **both** forms at lexicon build time and report which words
  lack a usable initial form. Never assume a capitalised variant exists.

### 2.3 Collisions destroy a third of the vocabulary

`big`, `large`, `great`, `huge` all translate to one target word. With
first-occurrence-wins, the rest become unreachable.

- **Measured:** **10,198 of 30,000 ids lost.**
- **Fix:** round-trip verification — translate the candidate back and keep the
  mapping only if it returns the word it started from.
- **After:** overall accuracy rose **21% → 32%**; 4,040 pairs rejected;
  9,368 ids still lost. A real improvement, not a cure.

### 2.4 Translating bare context-free words picks the wrong sense

A translation model given a single word with no context returns the most
frequent sense. `bank` → financial or riverbank? Round-trip verification filters
much of this. A real bilingual lexicon would be better than an MT model.

### 2.5 Input coverage is not output coverage

Two independent axes, conflated for two runs.

- **Input coverage** — are the prompt's words in the lexicon?
- **Output coverage** — are the words the model *generates* in the lexicon?

A prompt can be at 100% input coverage and still produce output peppered with
source-language words. Observed: `cheese`, `total`, `naar con` inside otherwise
correct Dutch.

- **Fix:** report both. They grow differently and fail differently.

### 2.6 The unknown-word fallback mixes two regimes

Falling back to the original tokenizer means that word hits the model's **own
native embeddings** for the target language, sitting in the same sequence as
relabelled source embeddings. Two different regimes in one vector space.

- **Fix:** report the proportion per prompt. Never read a score without it.

### 2.7 Changing five things at once makes every result unattributable

The first full run moved coverage, collisions, word sense, word order and
morphology simultaneously. The resulting number could not be attributed to any
of them — and a confident causal story was built on it anyway, and was wrong
(§3.2).

- **Fix:** §4, the ladder.

---

## 3. Predictions that failed, and what they cost

Recording these is the point. Each was plausible, argued, and wrong.

### 3.1 "Afrikaans is best for word-order compatibility"

Wrong. Afrikaans has radically simplified **morphology** but retains Germanic
**word order** — verb-second, verb-final in subordinate clauses. It would have
hit the identical wall as Dutch. *Lesson: genetic closeness and structural
closeness are different axes; name which one you need.*

### 3.2 "Indonesian will beat Dutch on word order"

Argued from Indonesian being SVO in every clause with zero verb conjugation.
Measured: **Indonesian 0%, Dutch 12%** on the word-order group. The word-order
account did not survive its first controlled test. *Lesson: a causal story built
on a five-variable run is a guess wearing a mechanism's clothes.*

### 3.3 "Growing the lexicon will inject noise and reduce accuracy"

Measured the opposite: **67% → 83%** as the lexicon grew from 113 to 2,244 ids.
Growth improved **output** coverage, which mattered more than the sense noise it
added. *Lesson: §2.5 — the axis I had not separated was the one that dominated.*

---

## 4. The procedure

### Rung 0 — the smallest thing that can work

- 50–70 hand-picked pairs. **Not** machine-translated.
- Prompts that the seed covers at **100%**, word-for-word parallel with the source.
- This removes coverage, collisions, sense error and morphology **by
  construction**, leaving word order and the model.
- **Run Gate 1.** Do not proceed until ids match on every prompt.

**Evidence that this ordering is right:** 63 hand-made pairs scored **67%**
where 10,820 machine-translated pairs scored 32% and 14,860 scored 21%. The
small clean lexicon beat the large noisy one by a factor of two to three.

### Rungs 1..n — grow geometrically, measure every rung

`N = 100, 300, 1000, 3000, 10000`. Fixed prompt set. The seed always wins a
conflict so the clean core is never overwritten. Report at every rung:

| | why |
|---|---|
| lexicon size | the independent variable |
| input coverage | §2.5 |
| **ids == source** | if this drops, a growth entry overwrote a seed word — a **bug**, not a finding |
| accuracy | the dependent variable |
| source-language accuracy | the ceiling, on the same prompts |

**Read it as:** accuracy flat at the ceiling → lossless so far. Falling → noise
now costs more than coverage adds, and that rung is the budget.

### Required arms, every rung

| arm | bounds |
|---|---|
| `source` | the ceiling |
| `swap` | the claim |
| **`native target`** | **attribution** — without it a low score cannot be told from the model simply being weak in that language |
| `shuffled` | the floor — a random dictionary must score ≈ 0, or the metric is not measuring meaning |

**`native target` is the arm most likely to be left out and the most important
one.** It is also where the publishable result lives: if `swap` *beats* native,
the source language's learned structure plus a dictionary outperforms the
model's own knowledge of the target — which matters directly for low-resource
languages.

### Prompt groups, not one score

| group | job |
|---|---|
| parallel-order | should work if the lexicon is sound |
| **arithmetic** | **internal control** — numbers bypass the swap, so these must match the source arm **exactly**. Arithmetic surviving while facts fail puts the failure in the lexicon, not the pipeline. Measured: 75% = 75% across every run. |
| divergent-order | the expected failure, pre-registered as such |
| one named mismatch | price each structural difference separately |

---

## 5. Choosing the target language

The criterion is **not** genetic closeness. With source syntax preserved, what
matters is:

1. **Same order in subordinate clauses** — the hard wall. No dictionary fixes
   verb-final.
2. **Light inflection** — every verb form needs its own lexicon entry.
3. **Modifier order** — a mismatch here is mild and systematic; price it separately.
4. **Script and segmentation** — space-separated Latin script keeps the codec
   unchanged.
5. **Lexicon availability** — verify the resource exists before committing.

| | order in subordinates | inflection | verdict |
|---|---|---|---|
| Germanic (Dutch, Afrikaans, Norwegian) | **verb-final** ❌ | varies | the wall |
| Romance (Spanish, French) | SVO ✅ | heavy ⚠️ | workable, morphology cost |
| Indonesian / Malay | SVO ✅ | **almost none** ✅ | best structural fit |
| Mandarin | SVO ✅ | **none** ✅ | relative clauses precede; needs segmentation |

Measured caution: Indonesian's structural advantages did **not** produce a
better score than Dutch (§3.2). Choose on these criteria, then **measure** — do
not assume the criteria are sufficient.

---

## 6. The rules, condensed

1. **Gate before you measure.** A correctness test that must return a known
   value catches bugs that accuracy cannot see.
2. **One variable per run.** Five variables produce a number plus a story, and
   the story will be wrong.
3. **Never subtract a counterfactual model.** A quantity is subtractable only if
   it is a real component of the measurement, not an alternative scenario.
4. **Controls match in capacity, not form.** A fitted direction must be compared
   against fitted directions, not random ones.
5. **If everything passes, the control is too weak.**
6. **Report the denominator.** Coverage, collisions, fallback proportion — a
   score without them is unreadable.
7. **Write the prediction down first.** Both failed predictions here were
   plausible; only the written record makes the failure informative.
8. **Verify the premise mechanically.** "Weights unchanged" is an assertion in
   code, not a sentence in a README.
9. **Name the result at the right altitude.** This measures lexical substitution
   between two languages. It does not measure anything about representations.

---

## 7. Status

| | |
|---|---|
| Correctness gate | ✅ 11/12 ids identical; one word blocked by §2.2 |
| Preservation on parallel-order prompts | ✅ **83% swap vs 83% source** |
| Preservation on natural target-language text | ⚠️ **32%** — word order is the gap |
| Weights unchanged | ✅ verified in code |
| Remaining known losses | 9,368 ids to collisions; output coverage; §2.2 |

**Next, in order:** fix §2.2 so coverage reaches 100%; replace MT with a real
bilingual lexicon to cut the collision loss; then measure how little training
closes the word-order gap — which is the question with commercial weight, since
the swap is free and the answer sets how much training is actually needed.
