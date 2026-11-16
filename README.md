# LEX_SWAP — a Dutch interface to an English model, with no training

Replace a causal LM's tokenizer ID ↔ string table and nothing else. No
fine-tuning, no embedding edits, no training of any kind. The weights are
loaded, checked bit-identical in code, and never written to.

```
Dutch question → [relabelled vocab] → token ids → UNCHANGED MODEL
               → token ids → [relabelled vocab] → Dutch text
```

---

## The result, both halves

Qwen2.5-0.5B · 41,882 lexicon entries · MUSE en-nl + 343 hand-made pairs ·
measured 2026-11-16

| prompt style | input coverage | output purity | **accuracy** | English ceiling |
|---|---|---|---|---|
| word-order parallel to English | 100% | **99.6%** | **64%** | 61% |
| **naturally written Dutch** | 90.1% | 94.1% | **10%** | — |

**Both rows are true. Neither may be quoted alone.**

On the first row the system is finished: it answers in fluent Dutch and scores
*above* the English original it was built from. On the second it does not work.

## Why the second row is low, and why that matters more than the first

The lexicon is not the problem. Purity is 94% on natural Dutch too — the words
come out Dutch. What breaks is that the model internally receives **English word
order**:

```
Gisteren ging ik naar de  →  winkel naar kopen enkele boeken
                                    ^^^^^^^^^^^  `to buy` rendered literally
                                                 Dutch needs `om te kopen`

Ik weet dat hij het boek  →  is een goed boek. Hij weet
                              should be `leest` — the verb belongs last, and
                              word-for-word substitution cannot move it
```

**This is more dangerous than an obvious failure.** The output looks like
correct Dutch, so a reader who does not speak the language cannot tell that the
reasoning behind it broke. **High purity is evidence about the lexicon and never
about correctness.**

No dictionary closes this gap. It is word order, and word order is not lexical.

## What it is honestly good for

| use it for | do not use it for |
|---|---|
| Dutch whose structure follows English | subordinate clauses (`dat hij … leest`) |
| lists, noun phrases, short factual completions | perfect tenses (`heb … gelezen`) |
| arithmetic — numbers bypass the swap entirely | separable verbs (`wil je opbellen`) |
| | inversion (`Gisteren ging ik`) |

The right-hand column is most of real Dutch.

## Use it

```python
from lexswap.dutch_model import DutchQwen

m = DutchQwen("artifact/lexicon_nl.json")
m.generate("Het boek is op de")        # ' tafel. Het boek is op de tafel'
m.verify_weights_untouched()           # True
m.last_coverage                        # {'coverage': 1.0, ...}
```

The lexicon ships in [`artifact/lexicon_nl.json`](artifact/lexicon_nl.json) and
the full measurement in
[`artifact/results_v13.json`](artifact/results_v13.json).

## How it got here

Thirteen runs. Every error, its cause and its fix are in
[`docs/NOTES.md`](docs/NOTES.md), and the reusable playbook in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

| | output purity |
|---|---|
| machine translation, 14,860 pairs | 0.67 |
| MUSE real dictionary | 0.689 |
| + recover renderings discarded to collisions | 0.701 |
| + fix the purity metric, supplement MUSE's gaps, map suffixes | 0.943 |
| + decode-only entries, stem+suffix | 0.956 |
| + **translate words instead of tokens** | **0.996** |

**63 hand-made pairs beat 10,820 machine-translated ones by two to three
times.** Small and exact beat large and noisy at every stage.

### The two lessons worth taking elsewhere

**Gate before you measure.** A test that must return a known value catches bugs
accuracy cannot see. One run showed 100% coverage and 67% accuracy while
matching token ids on **0 of 12** prompts — the renderer was wrong at the first
word of every sentence, and the aggregate looked like success.

**When no table entry can fix a residual error, the table is not what is
wrong.** Ask what the *procedure* cannot express. Twice this was the answer:
`de` vs `het` needs the *next* word, so decode needed a lookahead; and a word
costing two tokens is unreachable per-token, so decode needed to assemble words
first. Both were invisible as lexicon problems.

### Three announced limits that were my own measurement artefacts

| claimed | actually |
|---|---|
| hard ceiling of 84.8% purity | `A`/`B` list markers misclassified as subword fragments |
| "word order is the wall" | failed its first controlled test (Indonesian 0%, Dutch 12%) |
| wider vocabulary scan will raise purity | 2.5× the lexicon bought one point |

Each was caught by reading the examples behind the aggregate rather than the
aggregate itself.

## Prior art

Vocabulary-and-embedding replacement for cross-lingual transfer is an
established line — `WECHSEL`, `FOCUS`, `Trans-Tokenization`,
`Zero-Shot Tokenizer Transfer`. **Every method in it follows the swap with
training**, which is itself the strongest evidence that the swap alone is
insufficient — and the 64%-versus-10% split above is that insufficiency
measured. See [`docs/prior-art.md`](docs/prior-art.md).

What this repository contributes is the measurement, not the method.

---

## ملخّص بالعربية

**نموذج هولندي باستبدال القاموس وحده، بلا أي تدريب.** الأوزان تُحمَّل ويُتحقَّق
في الكود من أنها لم تتغيّر بتةً واحدة.

| نمط المُدخَل | تغطية | نقاء الخرج | **الدقّة** | سقف الإنكليزية |
|---|---|---|---|---|
| موازي الترتيب للإنكليزية | 100% | **99.6%** | **64%** | 61% |
| **هولندية مكتوبة طبيعياً** | 90.1% | 94.1% | **10%** | — |

**الصفّان صحيحان، ولا يجوز اقتباس أحدهما منفرداً.**

على الأول **النظام مكتمل** ويتفوّق على الإنكليزية الأصلية. وعلى الثاني **لا يعمل**.

**والسبب ليس المعجم** — النقاء ٩٤٪ على الطبيعية أيضاً، فالكلمات تخرج هولندية.
بل أن النموذج يتلقّى داخلياً **ترتيب الإنكليزية**:

```
Gisteren ging ik naar de  →  winkel naar kopen
                                    ^^^^^ "to buy" حرفياً، والصواب om te kopen
```

**وهذا أخطر من فشلٍ ظاهر:** المخرَج يبدو هولندياً سليماً، فمن لا يعرف اللغة لا
يرى أن الاستدلال خلفه قد انكسر. **النقاء العالي دليلٌ على المعجم، لا على الصحّة.**

ولا يُغلق هذا الفرق بأي معجم — فهو **ترتيب الكلمات**، وترتيب الكلمات ليس معجمياً.
