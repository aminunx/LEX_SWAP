"""LEX_SWAP v4 — two fixes, one rung at a time.

STEP 1: remove the sentence-initial special case instead of handling it.

v3 kept two tables because byte-level BPE gives `"The book"` as
`["The", " book"]` - position 0 has no leading space. That fixed 11 of 12
prompts, and the twelfth failed because `"Bread"` is not a single token while
`" bread"` is (METHODOLOGY 2.2).

Handling the exception is the wrong fix. Prepending a single space to every
prompt in EVERY arm makes all words space-prefixed, so one table suffices and
position 0 stops being a case at all. The id-identity gate should then reach
12/12.

STEP 2: measure output purity, the axis named in METHODOLOGY 2.5 and never
measured. Input coverage asks whether the prompt's words are in the lexicon.
Output purity asks whether the words the MODEL GENERATES are - and that is what
decides whether the answer reads as the target language or as a mixture. It is
why v3's accuracy ROSE from 67% to 83% as the lexicon grew, against the
prediction that growth would inject noise.

Run:  modal run modal/run_ladder2.py
"""

import modal

app = modal.App("lexswap-ladder2")
vol = modal.Volume.from_name("lexswap", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", "transformers", "sentencepiece", "sacremoses", "numpy")
    .env({"HF_HOME": "/cache/hf"})
    .add_local_dir("src", remote_path="/root/src")
)

RUNGS = [0, 100, 300, 1000, 3000, 10000]


@app.function(image=image, gpu="A10G", volumes={"/cache": vol}, timeout=14400)
def run(model_id: str = "Qwen/Qwen2.5-0.5B", max_new: int = 8, seed: int = 0):
    import json
    import os
    import string
    import sys

    import torch
    from transformers import (AutoModelForCausalLM, AutoModelForSeq2SeqLM,
                              AutoTokenizer)

    sys.path.insert(0, "/root")
    from src.lexswap.seed_nl import SEED_NL, SEED_PROMPTS

    torch.manual_seed(seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id).to(dev).eval()
    sig = {k: v.detach().clone() for k, v in list(model.state_dict().items())[:3]}

    AL = set(string.ascii_letters)

    # ------------------------------------------------------------------ STEP 1
    # every word space-prefixed, in every arm, so there is no position 0 case
    def enc_src(text):
        return tok.encode(" " + text.strip(), add_special_tokens=False)

    def seed_tables():
        id2, tgt2, dropped = {}, {}, []
        for nl, en in SEED_NL.items():
            ids = tok.encode(" " + en, add_special_tokens=False)
            if len(ids) != 1:
                dropped.append((nl, en, len(ids)))
                continue
            i = ids[0]
            tgt2.setdefault(" " + nl, i)
            tgt2.setdefault(" " + nl.capitalize(), i)
            id2.setdefault(i, " " + nl)
        return id2, tgt2, dropped

    seed_id2, seed_tgt2, dropped = seed_tables()
    print("=" * 112)
    print("STEP 1 - uniform space-prefixed encoding; no sentence-initial case")
    print("=" * 112)
    print(f"  seed pairs {len(SEED_NL)}   usable ids {len(seed_id2)}   "
          f"surface forms {len(seed_tgt2)}")
    if dropped:
        print(f"  dropped (source side not a single token): {dropped}")

    class Codec:
        def __init__(self, id2, tgt2):
            self.id2, self.tgt2 = id2, tgt2
            self.cov = {}

        def encode(self, text):
            ids, hit, miss, missed = [], 0, 0, []
            for w in text.strip().split(" "):
                if not w:
                    continue
                got = (self.tgt2.get(" " + w) or self.tgt2.get(" " + w.lower())
                       or self.tgt2.get(" " + w.capitalize()))
                if got is not None:
                    ids.append(got); hit += 1
                else:
                    ids.extend(tok.encode(" " + w, add_special_tokens=False))
                    miss += 1; missed.append(w)
            n = hit + miss
            self.cov = {"words": n, "swapped": hit, "fallback": miss,
                        "coverage": round(hit / n, 3) if n else 0.0,
                        "missed": missed}
            return ids

        def decode(self, ids):
            return "".join(self.id2.get(int(i), tok.decode([int(i)]))
                           for i in ids)

        # ---------------------------------------------------------- STEP 2
        def purity(self, ids):
            """Fraction of GENERATED tokens the lexicon can render.

            A token outside the lexicon is emitted in the source language, so
            this is what decides whether an answer reads as the target language
            or as a mixture. Punctuation and digits are excluded - they are
            language-neutral and would inflate the number.
            """
            real = [int(i) for i in ids
                    if any(c in AL for c in tok.decode([int(i)]))]
            if not real:
                return None
            return round(sum(int(i) in self.id2 for i in real) / len(real), 3)

    @torch.no_grad()
    def gen(ids):
        x = torch.tensor([ids], device=dev)
        out = model.generate(x, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
        return out[0, len(ids):].tolist()

    def evaluate(codec, label, verbose=False):
        hits = match = 0
        covs, purs, rows = [], [], []
        for p in SEED_PROMPTS:
            src_ids = enc_src(p["en"])
            ids = codec.encode(p["nl"])
            cov = dict(codec.cov)
            same = ids == src_ids
            out_ids = gen(ids)
            out = codec.decode(out_ids)
            pur = codec.purity(out_ids)
            hit = p["exp_nl"].lower() in out.lower()
            hits += hit; match += same
            covs.append(cov["coverage"])
            if pur is not None:
                purs.append(pur)
            rows.append({"id": p["id"], "coverage": cov["coverage"],
                         "ids_match": bool(same), "missed": cov["missed"],
                         "purity": pur, "out": out.strip(),
                         "expected": p["exp_nl"], "hit": bool(hit)})
            if verbose:
                print(f"{p['id']:>3} {p['nl'][:34]:<35}{cov['coverage']:>6.2f}"
                      f"{('YES' if same else 'no'):>8}"
                      f"{(pur if pur is not None else float('nan')):>8.2f}"
                      f"  {out.strip()[:34]:<35}{'Y' if hit else '.'}")
                if cov["missed"]:
                    print(f"      not in lexicon: {cov['missed']}")
        n = len(SEED_PROMPTS)
        return {"label": label, "coverage": round(sum(covs) / n, 3),
                "ids_match": match, "accuracy": round(hits / n, 3),
                "output_purity": round(sum(purs) / len(purs), 3) if purs else None,
                "rows": rows}

    # --------------------------------------------------------- rung 0 + gate
    print(f"\n{'#':>3} {'prompt (nl)':<35}{'cov':>6}{'ids':>8}{'purity':>8}"
          f"  {'output':<35}hit")
    print("-" * 112)
    r0 = evaluate(Codec(seed_id2, seed_tgt2), "rung0", verbose=True)
    print("-" * 112)
    gate = r0["ids_match"] == len(SEED_PROMPTS) and r0["coverage"] == 1.0
    print(f"  coverage {r0['coverage']:.1%}   ids identical "
          f"{r0['ids_match']}/{len(SEED_PROMPTS)}   accuracy {r0['accuracy']:.0%}"
          f"   output purity {r0['output_purity']}")
    print(f"  GATE {'PASSED - the codec is correct' if gate else 'FAILED - fix before reading anything above'}")

    src = evaluate(Codec({}, {}), "source_ignored")
    src_acc = sum(p["exp_en"].lower() in tok.decode(gen(enc_src(p["en"]))).lower()
                  for p in SEED_PROMPTS) / len(SEED_PROMPTS)
    print(f"  source-language ceiling on the same prompts: {src_acc:.0%}")

    # -------------------------------------------------------------- the growth
    mt = {}
    for tag, mid in (("f", "Helsinki-NLP/opus-mt-en-nl"),
                     ("b", "Helsinki-NLP/opus-mt-nl-en")):
        mt[tag] = (AutoTokenizer.from_pretrained(mid),
                   AutoModelForSeq2SeqLM.from_pretrained(mid).to(dev).eval())

    @torch.no_grad()
    def tr(tag, words):
        t, m = mt[tag]
        out = []
        for k in range(0, len(words), 64):
            e = t(words[k:k + 64], return_tensors="pt", padding=True,
                  truncation=True).to(dev)
            out += t.batch_decode(m.generate(**e, max_new_tokens=8, num_beams=1),
                                  skip_special_tokens=True)
        return out

    cands = []
    for i in range(30_000):
        s = tok.decode([i])
        b = s.lstrip(" ")
        if s.startswith(" ") and len(b) > 1 and all(c in AL for c in b):
            cands.append((i, b))
    sub = cands[:max(RUNGS)]
    fwd = tr("f", [b for _, b in sub])
    keep = [(i, b, f.strip().split()) for (i, b), f in zip(sub, fwd)]
    keep = [(i, b, f[0]) for i, b, f in keep
            if len(f) == 1 and all(c in AL for c in f[0])]
    back = tr("b", [t_ for _, _, t_ in keep])
    vmap = {i: t_ for (i, b, t_), v in zip(keep, back)
            if v.strip().strip(string.punctuation).lower().rstrip("s")
            == b.lower().rstrip("s")}
    print(f"\n[grow] {len(cands)} candidates, {len(keep)} single-word, "
          f"{len(vmap)} round-trip verified ({len(vmap)/max(len(keep),1):.0%})")

    print("\n" + "=" * 112)
    print("THE LADDER - fixed prompts, growing lexicon")
    print("=" * 112)
    print(f"{'rung N':>8}{'ids':>8}{'coverage':>11}{'ids==src':>10}"
          f"{'accuracy':>10}{'ceiling':>9}{'out purity':>12}")
    ladder = [dict(N=0, ids=len(seed_id2), **{k: r0[k] for k in
                   ("coverage", "ids_match", "accuracy", "output_purity")})]
    print(f"{0:>8}{len(seed_id2):>8}{r0['coverage']:>11.1%}"
          f"{r0['ids_match']:>10}{r0['accuracy']:>10.0%}{src_acc:>9.0%}"
          f"{(r0['output_purity'] or 0):>12.0%}")

    for N in RUNGS[1:]:
        id2, tgt2 = dict(seed_id2), dict(seed_tgt2)
        for i, b in cands[:N]:
            if i in vmap and i not in id2:
                t_ = vmap[i]
                id2[i] = " " + t_
                tgt2.setdefault(" " + t_, i)
                tgt2.setdefault(" " + t_.capitalize(), i)
        r = evaluate(Codec(id2, tgt2), f"rung{N}")
        ladder.append(dict(N=N, ids=len(id2), **{k: r[k] for k in
                      ("coverage", "ids_match", "accuracy", "output_purity")}))
        print(f"{N:>8}{len(id2):>8}{r['coverage']:>11.1%}{r['ids_match']:>10}"
              f"{r['accuracy']:>10.0%}{src_acc:>9.0%}"
              f"{(r['output_purity'] or 0):>12.0%}")
        ladder[-1]["rows"] = r["rows"]

    print("\n" + "=" * 112)
    print("READING IT")
    print("  accuracy == ceiling        full preservation on these prompts")
    print("  purity rising with N       growth is buying OUTPUT coverage, which")
    print("                             is why v3 improved instead of degrading")
    print("  ids==src below 12          a growth entry overwrote a seed word: a bug")

    after = model.state_dict()
    unchanged = all(torch.equal(sig[k], after[k]) for k in sig)
    print(f"\n  weights unchanged: {unchanged}")

    os.makedirs("/cache/out", exist_ok=True)
    payload = {"model": model_id, "gate_passed": bool(gate),
               "ceiling": round(src_acc, 3), "dropped_pairs": dropped,
               "weights_unchanged": bool(unchanged), "ladder": ladder,
               "rung0_rows": r0["rows"]}
    with open("/cache/out/ladder2.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    vol.commit()
    return payload


@app.local_entrypoint()
def main():
    run.remote()
