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

## 2026-11-16 · v10: the lexicon is complete by the word criterion

```
output purity   0.956
rendered        154/158  (97.5%)
not rendered      4      (2.5%)  - ALL continuation_piece
whole_word_no_entry       0
whole_word_entry_exists   0
lexicon         41,883 decode entries, exported to lexicon_nl.json
```

**Both fixable buckets are zero.** Every whole word the model generates has a
Dutch rendering. The residual is the metric correctly refusing to translate
mid-word pieces, which was established as the right behaviour before the number
arrived.

Fluent output:

```
Rood groen en         ->  blauw zijn drie kleuren van licht
De kleur van gras is  ->  groen. De kleur van een auto is
De man en de          ->  vrouw zijn in de zelfde kamer
De hond en de         ->  kat zijn spelen met een bal
```

## 2026-11-16 · A failure of a different KIND, visible only in the text

```
Het boek is op de  ->  tafel. De boek is op de tafel
                              ^^ should be `Het boek`
```

Dutch has two definite articles chosen by noun gender: `de` for common, `het`
for neuter. English has one. **A token-by-token map cannot choose, because the
information needed is in the NEXT word, not in the token being rendered.**

Everything fixed until now was a property of the mapping **tables** -
collisions, missing entries, fragments, casing. This is a property of the
**decoding procedure**: rendering one token at a time is structurally unable to
express the rule, no matter how good the lexicon becomes.

So the fix is not more lexicon. It is a one-token lookahead in decode, which is
a change in *kind* and the smallest one that can state the rule at all.

> **Rule for the methodology:** when a residual error cannot be removed by any
> entry in the table, the table is not the thing that is wrong. Ask what the
> procedure cannot express.

Limit recorded honestly: `HET_NOUNS` is hand-built and not exhaustive - Dutch
gender is not predictable from form, and a complete list needs a real Dutch
lexical database. So the article is corrected where the noun is known and `de`
remains the fallback, being the more common article and the better default.

## 2026-11-16 · MUSE returns inflected forms, not lemmas

`De kleur van melk is gele` - predicative adjectives are uninflected in Dutch,
so `geel` is right and `gele` is wrong. The dictionary gave the inflected form.

Fixed by hand entries, which already take priority over the dictionary. Worth
noting as a property of the resource: **a bilingual word list is not a lemma
list**, and for predicative positions that difference is visible in the output.

## 2026-11-16 · The third error is not fixable here

`kat zijn spelen met een bal` - two verbs in sequence, from word-for-word
mapping of a compound tense. This belongs to word order and morphology, and no
dictionary or lookahead addresses it. Recorded as a limit, not queued as a fix.

## 2026-11-16 · v11: both grammar fixes landed, and the swap passed the ceiling

```
Het boek is op de     ->  tafel. Het boek is op de tafel     article correct
De kleur van melk is  ->  geel. De kleur van melk is geel     lemma correct
accuracy 64%   ceiling 61%
```

The one-token lookahead fixed `De boek` to `Het boek`, and the hand lemma
entries fixed `gele` to `geel`. And accuracy came out at **64% against a 61%
ceiling** - the swapped Dutch now scores *above* the source English on this
set. Small sample, and the direction is the one the whole project was built to
test.

## 2026-11-16 · `Brood en -> Cinnamon` at purity 0.00, and the unit was wrong

The word is correct and un-rendered. The model spells it as **two tokens**,
`" C"` + `"innamon"`, so a per-token renderer sees a language-neutral single
letter followed by a fragment with no word-level entry.

That also explains `fl`, `oul` and `key` in every earlier residual: they are
pieces of multi-token words, not stray morphology.

**Cause: the procedure renders one token at a time, but the unit that has a
translation is the WORD.** Any word costing more than one token - which is most
of the long tail of a BPE vocabulary - is unreachable per-token however complete
the lexicon becomes.

Second instance of the rule from the last round, and it generalises:

> when a residual error cannot be removed by any entry in the table, the table
> is not what is wrong - ask what the procedure cannot express.

Fix: group the token stream into words before rendering, look the assembled word
up whole, fall back to the per-token path when it is not found. The fallback
means reassembly can only add renderings, never remove one, so purity cannot
regress.

**And a measurement consequence I nearly missed.** With reassembly, `id in id2`
is no longer the right test for "was this token rendered" - a multi-token word
translated as a whole leaves all of its tokens rendered while none of them is
in `id2`. Purity and the residual decomposition now both compute from the
grouping. Had I left the old test in place, the fix would have worked and the
metric would have reported no change - the exact shape of the v4 mistake, where
the ruler moved under the measurement.

## 2026-11-16 · v12: purity 0.996, and reassembly proved the diagnosis

```
Brood en  ->  Kaneel        purity 1.00     ("C" + "innamon" assembled, then translated)
rendered  157/158  (99.4%)
not rendered  1    (0.6%)   ['fl']
whole_word_no_entry      0
whole_word_entry_exists  0
```

`fl` is an orphan: it follows a non-letter, so there is no word to assemble it
into. One token out of 158.

| | |
|---|---|
| output purity | **99.6%** |
| input coverage | **100%** |
| accuracy | **64%** vs ceiling **61%** |
| weights | untouched, verified |
| lexicon | 41,882 entries |

## 2026-11-16 · Why I will not call this complete yet

Every one of those numbers is on **36 prompts constructed to be word-for-word
parallel with English**. That was the right design - it is what makes the
identity gate possible, and it let the lexicon be fixed separately from word
order. But they are English in Dutch clothing, and a system that only handles
them is not a Dutch model.

The first full run measured naturally written Dutch at **32%**.

So the remaining work is not pushing purity from 99.6% to 100%. It is testing
the finished system on Dutch that is actually Dutch: verb-final subordinate
clauses, perfect tenses with the participle last, inversion after a fronted
element, separable verbs. `natural_nl.py` is that set, 20 prompts, each tagged
with the construction English does not share.

Whatever it scores is the real answer, and it must be quoted **next to** the
parallel-set result rather than instead of it. Reporting 99.6% purity and 64%
accuracy without the natural-Dutch number would be the most misleading thing
this project could publish, precisely because every individual number is true.

## 2026-11-16 · v13: the honest number, and what it demands next

```
natural Dutch      coverage 90.1%   purity 0.941   accuracy 10%
parallel-order     coverage 100%    purity 0.996   accuracy 64%
```

The lexicon is not what fails. **Purity is 94% on natural Dutch too** - the
words come out Dutch. The model internally receives English word order:

```
Gisteren ging ik naar de  ->  winkel naar kopen enkele boeken
                                     ^^^^^^^^^^^ `to buy` literal; Dutch wants `om te kopen`
Ik weet dat hij het boek  ->  is een goed boek      (should be `leest`)
```

**More dangerous than an obvious failure**: the output reads as correct Dutch,
so someone who does not speak it cannot see that the reasoning broke. High
purity is evidence about the lexicon and never about correctness.

## 2026-11-16 · The missing layer was syntactic, and I had not built one at all

Asking the rule again - *what can the procedure not express?* - the answer this
time is not a detail. **There was no syntactic procedure.** Substitution
replaces words and leaves them where they sat, so word order was never
addressed by anything in the pipeline.

That is a build gap, not a hard limit, and it is still reachable without
training: reorder Dutch into English order *before* the lexical map.

## 2026-11-16 · And the obstacle that makes it non-trivial

Reordering an INCOMPLETE sentence moves the predicted word off the end.

```
Ik weet dat hij het boek ___      expects `leest`
I know that he ___ the book       the verb sits BEFORE the object
```

Left-to-right generation cannot reach a slot that is not final. Feeding
`I know that he` and generating does give a verb, but discards `het boek` -
exactly the evidence that makes `reads` likelier than `is`.

**So the model is used as a SCORER, not a generator.** Build the English-order
template with the object in place, put each candidate in the hole, score the
whole sequence, take the best. That is the only way to query a non-final
position, and it needs no training because scoring is what a causal LM already
does.

Three arms, so the contribution is attributable: `lexical` reproduces v13,
`syntax` adds reordering plus slot scoring, and `oracle_slot` scores only the
correct answer against distractors. The third bounds the approach: if `syntax`
sits far below `oracle`, the **rules** are the limit and more rules pay; if both
are low, **scoring** is the limit, which is a different problem with a different
fix. Without that arm a low result would be unattributable - the same mistake as
the five-variable runs at the start of this project.

## 2026-11-16 · v14 crashed on a direction confusion, in this project of all projects

```
AttributeError: 'int' object has no attribute 'strip'
```

`encode_mid` maps **Dutch -> token id**. I read it as Dutch -> English and
called `.strip()` on an integer.

The route from a source word to a target word necessarily goes through the id:

```
english  ->  id (tokenizer)  ->  dutch (decode map)
```

There is no direct source-to-target table, and there never was - the asymmetry
between the two directions has been the single most productive idea in this
project, and I still mixed them up in the type system. Fourth time the
input/output distinction has bitten, and the first time it crashed rather than
quietly degrading.

The same bug was in the shipped `dutch_model.py`, so the delivered artefact
would have failed on its first multi-token word. Caught only because v14
exercised the same code path. **An artefact that is committed is not an artefact
that has been run** - and nothing in the delivery commit had actually executed
the wrapper.

## 2026-11-16 · v14 run 2: two bugs, and one of them was a lie about capability

**OOM, 15.85 GiB requested.** The candidate-selection loop broke on
`len(cids) >= n_cand AND exp in cws`, so whenever the expected answer was not
in the pool it never broke at all and the list grew to 4,000. Full logits are
candidates x length x 151,936 vocab, which is about 29 GB. Fixed with an
unconditional cap and chunked scoring, so memory no longer depends on the
candidate count.

**And the one that matters: `build_candidates` was written and never called.**

The visible syntax-arm outputs were `een`, `de`, `is`, `ik` - function words
where verbs were wanted. The pool was the first 4,000 Dutch surface forms in
dictionary order, unfiltered, so the scorer did its job correctly and picked the
most probable words in the language.

The syntax arm therefore scored *below* the lexical arm on prompt 2, and had I
read only the totals I would have concluded **"the syntax layer does not help"**
and abandoned the right idea for a reason that was a missing function call.

> A function that is written but never called is worse than one that was never
> written: the first makes you believe the capability is present.

That is now the fifth result in this project that would have been
mis-attributed by reading an aggregate instead of its examples. The pattern is
no longer a coincidence, and it belongs in the methodology as its first rule
rather than its last.

## 2026-11-16 · v14 run 3: the oracle arm earned its place

```
lexical only (v13)      2/20   10%
+ syntax layer          2/20   10%
oracle slot (bound)     1/20    5%
```

`oracle` **below** `syntax`. The oracle scores the correct answer against only
20 distractors, so failing there means the scoring was never working - and that
is a different problem from the reordering rules.

Reading the examples found it, in my code:

```python
nl2id = {k.strip().lower(): int(v) for k, v in mid.items()}
```

`mid` holds both `" leest" -> id(" reads")` and `" Leest" -> id(" Reads")`.
Collapsing the key with `.strip().lower()` let the **capitalised** id win, so
every candidate - the correct answer included - was scored mid-sentence in its
sentence-initial form:

```
I know that he Reads the book      what was actually scored
I know that he reads the book      what was intended
```

So the 5% oracle was not a bound on the approach. **The approach had never been
tested** - it had been fed corrupted inputs, and the correct answer was
corrupted along with the distractors.

**Without the oracle arm I would have read `syntax == lexical` and concluded
that scoring does not work, and abandoned a correct idea.** That arm was
pre-registered for exactly this and it is the only reason the distinction
between "the method fails" and "the experiment is broken" was available.

Second fix in the same place: `een` ends in `-en` and passed the infinitive
filter, `de` passed the verb filter. The commonest words in the language beat
any real verb on probability, so they are now excluded by name rather than by
suffix shape.

Sixth mis-attribution caught by examples rather than aggregates. In all six the
fault was in my measurement code, never in the method under test.

## 2026-11-16 · The instrumentation paid for itself on the first line

I stopped guessing and printed what the model is actually fed. Three bugs were
visible immediately, none of which I would have found from outputs:

```
#1  english : 'I knows that he' [___] 'The book'
#2  english : 'They said that the house' [___] 'Big'
#16 english : 'I think that they' [___] 'Morning not'
#7  answer tok: None   in pool: False
```

**1. The suffix was encoded as a sentence start.** `enc_words` treated index 0
as sentence-initial unconditionally, so the suffix of every reordered template
came out capitalised and without a leading space: `The book`, `Big`. The model
was scored on `I knows that he reads The book`.

**So the scoring was never at its limit. It was being fed broken English.** The
oracle arm's 5% measured my encoder, not the method.

**2. `weet -> knows`.** The Dutch-to-English direction carries wrong
inflections, so `Ik weet` becomes `I knows`. Same class of problem as `gele` vs
`geel`, in the opposite direction.

**3. `morgen -> Morning`.** Dutch `morgen` is both *tomorrow* and *morning*, and
the dictionary chose the wrong sense, leaving `I think that they ___ Morning
not`. With a template that means nothing, `comes` loses to `were` and `all` -
correctly.

**4. `gelezen` has no token mapping at all**, so prompt 7 was unanswerable. A
target the system cannot emit bounds accuracy; it is not a wrong prediction.
That is now measured and printed as REACHABILITY, because an accuracy ceiling
imposed by missing vocabulary must not be read as a failure of the method.

Fixing one thing this round - the suffix encoding - so the effect stays
attributable. The other two are real and queued.

**The lesson is not that I had bugs.** It is that six rounds of reading outputs
found none of these, and one round of printing the intermediate representation
found four. Outputs tell you something is wrong; only the intermediate tells you
what.

## 2026-11-16 · v14 final: the syntax layer works, and the asymptote is visible

```
REACHABILITY            20/20   (was 16/20)   no vocabulary excuse remains
lexical only (v13)       2/20   10%
+ syntax layer           3/20   15%
oracle slot (bound)      6/20   30%   (was 5%)
```

Two things settled.

**The syntax layer helps.** 15% against 10%. Word order was addressable without
training, by reordering plus scoring rather than by lexicon - which is what the
earlier "word order is the wall" claim denied.

**And the diagnostic flipped.** `oracle` is now ABOVE `syntax`, so the limit is
the reordering rules rather than the scoring. The earlier 5% was my encoder,
measured three bugs ago. That correction is now complete.

### But the trajectory has to be stated plainly

On a 20-prompt set, **10% to 15% is one prompt.** That is inside the noise of
this sample, and nine iterations of v14 have cost nine GPU runs for roughly
that. The honest reading is not "progress is slow" but "the measurement is too
small to resolve what the fixes are doing".

And the bound is visible. `oracle` scores the correct answer against only 20
distractors and still wins just 6/20. Even perfect reordering and perfect
candidate restriction leave scoring picking right under a third of the time in
the EASY setting. That is a property of using an English-order model to produce
Dutch inflections, not a bug left to find.

### What remains, named rather than promised

Five of twenty prompts match no rule at all - relative clauses (`die daar
woont`, `dat daar speelt`), perfect with an intervening object (`hebben
gisteren een film`), concessives (`Hoewel ... gingen wij`). Those fall through
to the lexical path untouched.

The near misses are semantic neighbours: `verstuurd` (sent) for `gelezen`
(read), `gegeven` (given) for `gezegd` (said), `kocht` (bought) for `leest`
(reads). The slot and the category are right; the lexical choice is not.

**100% on natural Dutch is not reachable by vocabulary swap plus hand-written
syntax rules.** That is the measured conclusion, not a prediction. What closes
it is training on Dutch word order - and the value of everything above is that
it says how little might be needed, since the swap is free and already carries
the lexicon at 99.6% purity.

## 2026-11-16 · Correcting myself: "cannot reach 100%" is not "nothing left to do"

I conflated two claims and the second was wrong. Re-reading the v14 rows found
concrete, named work rather than a tail of diminishing returns:

**Five of twenty prompts matched NO reorder rule at all** - a quarter of the set
never touched by the syntax layer. Specifically:

| prompt | why no rule |
|---|---|
| `Wij hebben gisteren een film` | R2 required a negation in the tail; there is none |
| `De man die daar woont is` | relative clause with the verb last - no rule existed |
| `Het kind dat daar speelt is` | same |
| `Hoewel het koud was gingen wij` | concessive plus inversion |

**And twenty prompts is too small to measure with.** One prompt is 5%, which is
wider than any effect the fixes produce, so every number in the last nine runs
was being read off a scale too coarse to resolve it.

Both fixed this round:

- **R2b** - perfect tense with an object or adverbial between auxiliary and
  participle, no negation required.
- **R5** - relative clause with the verb last: English puts the verb straight
  after the relative pronoun, Dutch puts it at the clause end.
- **Test set 20 -> 50**, same construction families, originals kept intact and
  scored separately so the whole series stays comparable.

Verified locally before pushing: rule coverage **47/50 (94%)**, and on the
original twenty it rises from **15/20 to 18/20** without breaking any rule that
already worked.
