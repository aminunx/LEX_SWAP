# LEX_SWAP

**What survives when you replace a language model's dictionary and nothing else?**

No fine-tuning. No embedding edits. No training of any kind. The weights are
loaded, verified bit-identical at the end of the run, and never written to.
Only the tokenizer's ID ↔ string table changes.

```
Dutch question → [swapped vocab] → token ids → UNCHANGED MODEL
               → token ids → [swapped vocab] → Dutch text
```

> English is the primary language of this README because the result is aimed at
> an international audience. Arabic summary at the bottom.

---

## The honest framing

A causal LM never sees text. It sees integer ids. So if token `567` stops
rendering as `" the"` and starts rendering as `" de"`, the arithmetic inside the
network is **byte-identical**. The substitution happens entirely outside the
model, at both ends.

That has a consequence worth stating plainly, because it decides what this
repository can and cannot claim:

| | |
|---|---|
| **This measures** | how much meaning a word-for-word lexical substitution preserves between two languages, with the model as a fixed instrument |
| **This does not measure** | whether the model's internal representations are language-independent — they are never shown Dutch |

The mechanism is not new. Vocabulary-and-embedding replacement for
cross-lingual transfer is an established line of work, and **every method in it
follows the swap with training**, because the swap alone is known to be
insufficient. See [`docs/prior-art.md`](docs/prior-art.md).

**What is worth contributing here is the measurement, not the method**: a
controlled anatomy of exactly what survives a pure lexical swap and what
breaks, with baselines that make the answer attributable. A precisely dissected
negative result is publishable. An overstated positive one does not survive
first review.

## Four arms, and why each exists

| arm | what it is | what it bounds |
|---|---|---|
| `english` | native English, original tokenizer | the ceiling |
| `swap` | Dutch → swapped vocab → unchanged model | the claim |
| **`native_nl`** | **Dutch, original tokenizer, no swap** | **required for attribution** |
| `shuffled` | the same pipeline, randomised dictionary | the floor |

`native_nl` is the arm the original spec was missing, and it is the most
informative one. Qwen2.5 is multilingual and already speaks some Dutch. Without
it, a poor `swap` score cannot be told apart from the model simply being weak in
Dutch — and if `swap` *beats* `native_nl`, that is the genuinely surprising
result and the one worth writing up.

`shuffled` bounds the other end. A dictionary that is pure noise must score near
zero. If it does not, the metric is measuring something other than meaning.

## The evaluation set is designed to fail in a specific place

24 prompts in three groups ([`src/lexswap/prompts.py`](src/lexswap/prompts.py)):

- **`easy`** — main clauses whose word order matches English. These should work
  if the lexicon is any good.
- **`arithmetic`** — numbers are never substituted, so these **must** match the
  English baseline exactly. This is the internal control: arithmetic surviving
  while facts fail localises the failure to the lexicon rather than the pipeline.
- **`word_order`** — Dutch subordinate clauses put the verb last, and separable
  verbs split. Word-for-word substitution turns these into broken English.

**The `word_order` group is pre-registered as the expected failure.** A failure
there confirms a prediction; it is not a surprise and will not be reported as one.

## Predictions recorded before the first run

| prediction | basis |
|---|---|
| `word_order` ≪ `easy` | Dutch V2 and verb-final clauses survive no word-for-word mapping |
| `arithmetic` == `english` exactly | numbers bypass the swap, so any gap is a bug in the codec |
| collisions will be large | `big · large · great · huge` all map to `groot`, and first-occurrence-wins must lose information |
| coverage will cap the result | most of a BPE vocabulary is sub-word fragments, not whole words |

Coverage is the number to read first. Where the dictionary does not cover a
word, it falls back to the model's own native Dutch tokens — which **mixes two
regimes in one sequence**: relabelled English embeddings sitting next to genuine
Dutch ones. The runner reports that proportion per prompt, and no result should
be read without it.

## Measured so far

| lexicon | method | accuracy | source baseline |
|---|---|---|---|
| 14,860 pairs | machine-translated | 21% | 62% |
| 10,820 pairs | + round-trip verified | 32% | 62% |
| **63 pairs** | **hand-made seed** | **67%** | 83% |
| **2,244 pairs** | **seed + verified growth** | **83%** | **83%** |

**At 2,244 pairs the swap matches the source baseline exactly — 83% against
83%.** Full preservation on prompts that are word-for-word parallel with
English, with no training and weights verified unchanged.

On *naturally written* Dutch, with its own word order, the same pipeline reaches
**32%**. **The gap between those two numbers is the whole limitation of the
method, and it is word order.**

A 63-pair hand-made lexicon beat a 10,820-pair machine-translated one by two to
three times. Small and exact beats large and noisy.

## Read this first

[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — the playbook for applying this to
any model, written from the errors that produced it: four correctness gates to
run before any experiment, seven logged bugs with their symptoms and fixes, and
three predictions that failed with what each cost.

## Run

```bash
modal run modal/run_ladder.py      # the ladder: seed, then geometric growth
modal run modal/run_multilang.py   # Dutch vs Indonesian, one variable
```

Results and the full swap table are written to the `lexswap` volume under
`/out/`.

## Layout

| path | |
|---|---|
| [`SPEC.md`](SPEC.md) | the original specification, recorded verbatim as the contract |
| [`docs/what-this-measures.md`](docs/what-this-measures.md) | pre-run analysis of what the design does and does not test |
| [`docs/prior-art.md`](docs/prior-art.md) | existing work on vocabulary replacement, and how this differs |
| [`src/lexswap/core.py`](src/lexswap/core.py) | swap table construction and the word-level codec |
| [`src/lexswap/prompts.py`](src/lexswap/prompts.py) | the 24-prompt evaluation set |
| [`modal/run_lexswap.py`](modal/run_lexswap.py) | the four-arm experiment |

---

## ملخّص بالعربية

**السؤال:** ماذا ينجو من قدرة نموذج لغوي إذا استُبدل قاموسه وحده؟

بلا تدريب، وبلا تعديل أي وزن — والأوزان تُقارَن في نهاية التشغيل للتأكّد من أنها
لم تتغيّر بتةً واحدة. يُستبدَل جدول `الرقم ↔ النص` فقط.

**وما يجب أن يُقال صريحاً:** النموذج لا يرى هولندية أبداً. يرى أرقاماً إنكليزية،
والاستبدال كلّه خارجه. فالتجربة تقيس **كم يحفظ الاستبدال كلمةً-بكلمة من المعنى
بين اللغتين** — لا استقلال التمثيلات الداخلية عن اللغة.

**والآلية ليست جديدة.** استبدال المعجم للنقل بين اللغات خطٌّ قائم، وكلّ طرائقه
تُتبع الاستبدال **بتدريب**، لأن الاستبدال وحده معروفٌ أنه لا يكفي.

**فما يستحقّ النشر هنا هو القياس لا الطريقة:** تشريحٌ مضبوط لما ينجو وما ينكسر،
بخطوط أساس تجعل الجواب قابلاً للنسبة إلى سببه. والنتيجة السلبية المُشرَّحة بدقّة
تُنشَر وتُحترَم؛ والمضخَّمة تُكشَف في أول مراجعة.

**وأربعة أذرع**، أهمّها `native_nl` — أن نسأل النموذج بالهولندية **مباشرة**. فبلا
هذا الذراع لا نعرف: هل جاء الفشل من الاستبدال أم من ضعف النموذج بالهولندية
أصلاً؟ وإن **تفوّق** الاستبدال عليه، فتلك هي النتيجة المثيرة فعلاً.
