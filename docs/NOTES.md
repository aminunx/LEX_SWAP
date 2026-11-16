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

## 2026-11-16 · v4: the fix worked, found two new problems, and moved the ruler

Step 1 (one prepended space, one table) **did** reach 100% input coverage, and
Step 2's new metric behaved exactly as the mechanism predicted: output purity
rose monotonically 62% → 68% → 72% → 77% → 79% → 82% as the lexicon grew. That
is the direct confirmation of METHODOLOGY 2.5 — growth buys OUTPUT coverage,
which is why v3 improved when I had predicted it would degrade.

But the identity gate still read **0/12**, and the baseline moved.

**New problem 1: case, not spacing.** `" The"` and `" the"` are different
tokens. Prepending a space fixed the spacing half of the mismatch and left the
capital, so `" Het"` mapped to `id(" the")` while the source arm used
`id(" The")`. Every prompt still differed at position 0.

**New problem 2, and the more important one: the ceiling fell from 83% to 75%.**
Prepending a space changed the SOURCE arm's tokenisation too, so the elegant fix
that deleted a bug class also shifted the measuring stick by eight points.

> **Rule added to the methodology:** after any fix, re-check the **baseline**,
> not only the quantity under test. A change to the encoding convention is a
> change to both arms, and an improvement measured against a moved ruler is not
> an improvement.

v5 therefore drops the prepended space (restoring the baseline) and carries
three surface forms per pair instead of one: no-space capitalised for position
0, space-lowercase and space-capitalised for mid-sentence.

And where no single-token initial form exists — `"Bread"` is two tokens while
`" bread"` is one — identity is simply **unachievable** at that position. Rather
than report a silent failure, the gate now requires identity everywhere it CAN
hold and prints every exception with its cause.

## 2026-11-16 · I had been measuring the wrong variable for four runs

> «من طلب منك رفع عدد المعجم؟ الهدف هو ترجمة المعجم بمعجم حقيقي لكل توكن
> بنفس الكلمة باللغة الهولندية»

Correct, and it invalidates the axis I had been optimising.

The ladder's independent variable was **N — how many tokens were attempted**:
300, 1000, 3000, 10000, 30000, 60000. But the *quality* of every mapping came
from `opus-mt` fed a bare context-free word, which returns the most frequent
sense and collapses many English words onto one Dutch word.

So I was scaling the count of a low-quality source and reporting the count as
progress. The data says exactly that:

| lexicon ids | output purity |
|---|---|
| 13,664 | 66% |
| 27,686 | 66% |
| 34,043 | **67%** |

**2.5x the lexicon bought one point.** I had promised two rounds earlier that
widening the scan would raise purity. It did not. That prediction failed too.

The target was never the count. It is **one real translation per token**.

v7 therefore replaces machine translation with MUSE bilingual dictionaries -
real word-pair lists - and walks the whole vocabulary in batches, reporting
matched / no-entry / multi-word per batch so the lexicon is built with its
failures visible instead of as one opaque number.

**Hard rule written into the run:** if the dictionary cannot be fetched, the run
**stops and says so**. It does not fall back to machine translation. A silent
fallback would reproduce the exact failure this run exists to remove while
appearing to have fixed it — and given that I have now mis-attributed three
results in this project, the guard matters more than the convenience.

## 2026-11-16 · The real dictionary worked; my code wasted a third of it

MUSE en-nl fetched: **82,167 English headwords**. Of the vocabulary's 41,495
whole-word tokens, **27,955 matched (67.4%)**. The hard rule held — no silent
fallback to machine translation was needed.

And output purity moved from 0.67 to **0.689**. Two points, for a real
dictionary replacing machine guesses.

The reason was a bug in this code, not a limit of the dictionary. Both
directions were keyed on the Dutch word, so `big`, `large` and `great` all
mapping to `groot` left two of the three ids with **no Dutch rendering at all**.
27,955 matches collapsed to 17,201 pairs: **10,754 renderings discarded for
nothing.**

A collision constrains **input only**:

| direction | collision |
|---|---|
| `groot` → id | unavoidable, one id must be chosen |
| id → `groot` | **no conflict** — many ids may all render as `groot` |

Fixed: the decode map is built from every match, the encode map keeps
first-wins.

## 2026-11-16 · Stop patching files with string replacement

Third file broken this session by a `str.replace` patch — this one a
`SyntaxError` at line 299 from a mangled escape inside a heredoc. The run died
before it started.

**Rule: write the file, do not patch it.** The patch is faster to type and has
now cost three runs.

## 2026-11-16 · Why the decomposition had to come before more lexicon work

Four rungs were spent optimising lexicon SIZE, then one on dictionary QUALITY,
and purity moved 66% → 67% → 68.9%. I should have built the diagnostic first.

It sorts every un-renderable generated token into three buckets, and only one of
them is reachable:

- `subword_fragment` — a BPE piece like `ing`. **No word-level translation
  exists**, in MUSE or in any human dictionary. Whatever share this holds is a
  hard ceiling on the whole method.
- `whole_word_no_entry` — reachable with a bigger dictionary.
- `whole_word_entry_exists` — a code bug, free to fix.

The first number is the honest answer to "how much is left", and it was
obtainable at any point in the last five rungs. Measuring the ceiling before
optimising towards it is cheaper than discovering it by exhaustion.

## 2026-11-16 · My "hard ceiling of 84.8%" was an artefact of my own metric

The v8 decomposition reported 18.3% of generated tokens un-renderable, 83% of
that as `subword_fragment`, and I announced a hard ceiling of 84.8% for the
whole method.

Then I read the examples:

```
subword_fragment  29  ['A','B','A','B','A','B','A','B','innamon']
```

**`A` and `B` are multiple-choice list markers.** They classified as subword
fragments only because they carry no leading space. One real fragment,
`innamon`, in the whole set.

A single letter is as language-neutral as a digit — `A.` is `A.` in Dutch too —
and the purity metric already excluded digits and punctuation for exactly that
reason. It should have excluded single letters. **The ceiling I announced came
from a classification bug in the measuring code, not from a property of the
method.**

Three separate causes had been collapsed into one bucket:

| cause | kind of problem | fix |
|---|---|---|
| `A`, `B` list markers | **metric bug** | treat single letters as language-neutral |
| ` If`, ` It`, ` at` | MUSE genuinely lacks them | hand supplement, closed-class |
| `innamon` | a real fragment | suffix map, decode direction only |

The second is worth noting on its own: `whole_word_entry_exists` came back at
**zero**, which proves those words are absent from the 82,167-headword file
rather than mishandled by my code. MUSE is built by word alignment and curated
for bilingual lexicon induction, so some closed-class words simply are not in
it. That is a property of the resource, and no amount of scanning finds them.

Fragment mappings go to the **decode direction only**. Input is whole words, so
putting fragments in the encode tables would change a prompt's token ids and
break the identity gate for no gain.

**Pattern across this project: three of my announced limits were measurement
artefacts.** The 0.30 anchor, the word-order wall, and now this ceiling. Each
was caught by reading the examples behind the aggregate rather than the
aggregate alone.

## 2026-11-16 · v9: purity 0.701 -> 0.943, and the gap list exposed the resource

Three fixes landed and output purity went from 0.701 to **0.943**, with 7
un-rendered tokens out of 158. Accuracy stayed at the ceiling, ids 34/36,
coverage 100%, weights unchanged.

Then the frequency-ranked gap list said something I had not expected:

```
th in to re of st is be on de wh if it as al an or tr ex se le at ch pr by
```

**`in to of is be on if it as an or at by he we us do up go` are ordinary
English function words, and MUSE contains none of them.** The 82,167-headword
file is built by word alignment and curated for bilingual lexicon induction, so
the closed-class core of the language is partly absent. The hand supplement is
not a garnish on the dictionary - it is load-bearing.

## 2026-11-16 · A collision inside my own supplement

` It` stayed untranslated. Cause: `SEED_NL` holds `het -> the`, my supplement
added `het -> it`, and `setdefault` dropped it. Dutch `het` genuinely carries
both senses, so this is not a mistake in the data - it is the same collision
problem one level up, in hand-written material this time.

And the fix is the same lesson: **a collision constrains input only.** On output
`id(" it")` renders as `" het"` while `id(" the")` also renders as `" het"`,
with no conflict at all. Hence a `DEC_ONLY` table.

That makes three places where the input/output asymmetry mattered - dictionary
collisions, the v7 discarded renderings, and now the hand supplement. It is the
single most productive idea in this project and I failed to generalise it twice
after learning it once.

## 2026-11-16 · Where the residual is genuinely correct

`key` came back un-rendered. MUSE has `key -> sleutel`, so it looks like a gap.
It is not: this `key` is the continuation piece of `monkey`, and rendering it as
`sleutel` would be **wrong**.

> A token with no leading space is a piece, not a word, whatever its shape.

So `continuation_piece` residual is not a shortfall to be driven to zero. Part
of the remaining 4% is the metric correctly declining to do something harmful,
and a run that reported 100% purity would be reporting a bug.
