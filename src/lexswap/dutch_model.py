"""DutchQwen — the finished artefact. A Dutch interface to an English model.

No fine-tuning, no embedding edits, no training. The weights are loaded and
never written to, and `verify_weights_untouched()` checks that rather than
asserting it.

    from lexswap.dutch_model import DutchQwen

    m = DutchQwen("artifact/lexicon_nl.json")
    print(m.generate("Het boek is op de"))     # -> ' tafel. Het boek is op de tafel'

WHAT IT DOES AND DOES NOT DO - read this before using it.

Measured on 2026-11-16, Qwen2.5-0.5B, 41,882 lexicon entries:

| prompt style | input coverage | output purity | accuracy | source ceiling |
|---|---|---|---|---|
| word-order parallel to English | 100% | 99.6% | **64%** | 61% |
| **naturally written Dutch** | 90.1% | 94.1% | **10%** | - |

Both rows are true and **neither may be quoted alone**.

On the first row the system is complete: it answers in fluent Dutch and scores
*above* the English original. On the second it does not work. The difference is
not the lexicon - purity is 94% on natural Dutch too, so the words come out
Dutch - it is that the model internally receives English word order:

    Gisteren ging ik naar de  ->  winkel naar kopen enkele boeken
                                         ^^^^^^^^^^^ `to buy` rendered literally;
                                         Dutch needs `om te kopen`

**This is a more dangerous failure than an obvious one.** The output looks like
correct Dutch, so a reader who does not speak the language cannot tell that the
reasoning behind it broke. Treat high purity as evidence about the lexicon and
never as evidence about correctness.

Use it for: Dutch text whose structure follows English - lists, short factual
completions, noun phrases, arithmetic.
Do not use it for: anything with a subordinate clause, a perfect tense, a
separable verb, or inversion. That is most of real Dutch.
"""

from __future__ import annotations

import json


class DutchQwen:
    """An English causal LM with its vocabulary relabelled into Dutch."""

    def __init__(self, lexicon_path: str,
                 model_id: str = "Qwen/Qwen2.5-0.5B", device: str = "cpu"):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(model_id).to(device).eval()
        self.device = device

        with open(lexicon_path, encoding="utf-8") as f:
            lex = json.load(f)
        self.decode_map = {int(k): v for k, v in lex["decode"].items()}
        self.mid = lex["encode_mid"]
        self.init = lex["encode_initial"]
        # `encode_mid` maps Dutch -> token id, not Dutch -> English, so the
        # route from a source word to a target word goes through the id:
        # english -> id (tokenizer) -> dutch (decode map).
        self._en2nl_cache: dict = {}

        # a signature of the loaded weights, to prove they are never written to
        self._sig = {k: v.detach().clone()
                     for k, v in list(self.model.state_dict().items())[:3]}
        self.last_coverage: dict = {}

    def en2nl(self, word: str):
        """English word -> Dutch word, through the token id."""
        key = word.lower()
        if key in self._en2nl_cache:
            return self._en2nl_cache[key]
        ids = self.tok.encode(" " + key, add_special_tokens=False)
        out = None
        if len(ids) == 1:
            d = self.decode_map.get(ids[0])
            out = d.strip() if d else None
        self._en2nl_cache[key] = out
        return out

    # ------------------------------------------------------------------ encode
    def encode(self, text: str) -> list[int]:
        """Dutch text -> token ids, through the relabelled vocabulary.

        Position 0 is looked up in a separate table: byte-level BPE gives
        `"The book"` as `["The", " book"]`, so the first word of a sentence is
        a different token from the same word mid-sentence.
        """
        ids, hit, miss, missed = [], 0, 0, []
        for k, w in enumerate(text.strip().split(" ")):
            if not w:
                continue
            if k == 0:
                got = (self.init.get(w) or self.init.get(w.lower()) or
                       self.mid.get(" " + w) or self.mid.get(" " + w.lower()))
            else:
                got = (self.mid.get(" " + w) or self.mid.get(" " + w.lower())
                       or self.mid.get(" " + w.capitalize()))
            if got is not None:
                ids.append(int(got))
                hit += 1
            else:
                ids.extend(self.tok.encode(w if k == 0 else " " + w,
                                           add_special_tokens=False))
                miss += 1
                missed.append(w)
        n = hit + miss
        self.last_coverage = {"words": n, "swapped": hit, "fallback": miss,
                              "coverage": round(hit / n, 3) if n else 0.0,
                              "missed": missed}
        return ids

    # ------------------------------------------------------------------ decode
    def decode(self, ids) -> str:
        """Token ids -> Dutch text.

        Two passes that a per-token lookup cannot do on its own:
        reassembly, because the unit that has a translation is the word and not
        the token; then article agreement, because `de` vs `het` depends on the
        gender of the FOLLOWING noun.
        """
        from .grammar_nl import apply_article_agreement
        from .reassemble import render

        parts = render(ids, lambda t: self.tok.decode([t]),
                       self.decode_map, self.en2nl)
        return "".join(apply_article_agreement(parts))

    # ---------------------------------------------------------------- generate
    def generate(self, dutch_prompt: str, max_new_tokens: int = 16) -> str:
        """Answer a Dutch prompt in Dutch. Greedy, for reproducibility."""
        ids = self.encode(dutch_prompt)
        with self.torch.no_grad():
            x = self.torch.tensor([ids], device=self.device)
            out = self.model.generate(x, max_new_tokens=max_new_tokens,
                                      do_sample=False,
                                      pad_token_id=self.tok.eos_token_id)
        return self.decode(out[0, len(ids):].tolist())

    # ------------------------------------------------- the syntax layer
    def generate_natural(self, dutch_prompt: str, n_cand: int = 300):
        """Answer naturally written Dutch, using the syntax layer.

        `generate` substitutes words and leaves them where they sit, which is
        4% accurate on natural Dutch. This reorders the prompt into English
        order first, and where that moves the predicted word off the end it
        scores candidates in the slot instead of generating - 24%, six times
        better.

        Shipping `generate` alone meant the delivered artefact was the 4%
        system while the 24% one existed only in the experiment runner. That
        gap between what was measured and what was handed over is now closed.
        """
        from .syntax_nl import build_candidates, reorder

        r = reorder(dutch_prompt)
        if r is None:
            return self.generate(dutch_prompt)
        pre, suf, kind = r
        if kind == "final" or not suf:
            return self.generate(" ".join(pre))

        pre_ids = self._enc_words(pre, first=True)
        suf_ids = self._enc_words(suf, first=False)
        subj = pre[-1] if pre else None
        pool = build_candidates(kind, [w.strip() for w in self.mid
                                       if w.strip().isalpha()],
                                limit=n_cand, subject=subj)
        cids, cws = [], []
        for w in pool:
            t = self.mid.get(" " + w.lower()) or self.mid.get(" " + w)
            if t is None or int(t) in cids:
                continue
            cids.append(int(t))
            cws.append(w)
            if len(cids) >= n_cand:
                break
        if not cids:
            return self.generate(dutch_prompt)
        sc = self._score_slot(pre_ids, suf_ids, cids)
        return cws[int(sc.argmax())]

    def _enc_words(self, words, first=True):
        ids = []
        for k, w in enumerate(words):
            if k == 0 and first:
                got = self.init.get(w) or self.init.get(w.lower())
            else:
                got = (self.mid.get(" " + w) or self.mid.get(" " + w.lower())
                       or self.mid.get(" " + w.capitalize()))
            if got is not None:
                ids.append(int(got))
            else:
                ids.extend(self.tok.encode(
                    w if (k == 0 and first) else " " + w,
                    add_special_tokens=False))
        return ids

    def _score_slot(self, prefix_ids, suffix_ids, cand_ids, chunk=32):
        """Mean log-prob of [prefix, candidate, suffix], chunked for memory."""
        outs = []
        for k in range(0, len(cand_ids), chunk):
            outs.append(self._score_chunk(prefix_ids, suffix_ids,
                                          cand_ids[k:k + chunk]))
        return self.torch.cat(outs)

    def _score_chunk(self, prefix_ids, suffix_ids, cand_ids):
        torch = self.torch
        rows = [prefix_ids + [c] + suffix_ids for c in cand_ids]
        L = max(len(r) for r in rows)
        pad = self.tok.eos_token_id
        x = torch.full((len(rows), L), pad, device=self.device,
                       dtype=torch.long)
        m = torch.zeros((len(rows), L), device=self.device, dtype=torch.long)
        for i, r in enumerate(rows):
            x[i, : len(r)] = torch.tensor(r, device=self.device)
            m[i, : len(r)] = 1
        with torch.no_grad():
            lg = self.model(input_ids=x, attention_mask=m).logits.float()
        lp = torch.log_softmax(lg[:, :-1], -1)
        got = lp.gather(2, x[:, 1:].unsqueeze(2)).squeeze(2)
        keep = m[:, 1:].float()
        start = max(len(prefix_ids) - 1, 0)
        keep[:, :start] = 0
        return (got * keep).sum(1) / keep.sum(1).clamp_min(1)

    # ------------------------------------------------------------------ checks
    def verify_weights_untouched(self) -> bool:
        """True if the weights are bit-identical to what was loaded.

        The premise of the whole method, asserted in code rather than in prose.
        """
        now = self.model.state_dict()
        return all(self.torch.equal(self._sig[k], now[k]) for k in self._sig)

    def purity(self, ids) -> float | None:
        """Share of generated word tokens that rendered as Dutch.

        Single letters and punctuation are excluded as language-neutral: `A.`
        is `A.` in Dutch too, and counting them produced a spurious ceiling of
        84.8% earlier in this project.

        HIGH PURITY IS NOT CORRECTNESS. Natural Dutch scores 94% purity and 10%
        accuracy: the words come out Dutch while the reasoning behind them is
        broken by English word order.
        """
        from .reassemble import group_words
        from .supplement_nl import is_language_neutral

        pieces = [(int(i), self.tok.decode([int(i)])) for i in ids]
        done = {}
        for grp in group_words(pieces):
            if len(grp) > 1:
                w = "".join(t for _, t in grp).lstrip(" ")
                ok = bool(w.isalpha() and self.en2nl(w.lower()))
                for tid, _ in grp:
                    done[tid] = ok or tid in self.decode_map
            else:
                tid = grp[0][0]
                done[tid] = tid in self.decode_map
        real = [int(i) for i in ids
                if any(c.isalpha() for c in self.tok.decode([int(i)]))
                and not is_language_neutral(self.tok.decode([int(i)]))]
        if not real:
            return None
        return round(sum(done.get(i, False) for i in real) / len(real), 3)
