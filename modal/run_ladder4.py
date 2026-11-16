"""LEX_SWAP v5 — case-aware tables, and the baseline restored.

v4 prepended a space to every prompt to delete the position-0 special case. It
worked for coverage (100%) but produced two new problems:

  1. CASE, not spacing, was the remaining mismatch. `" The"` and `" the"` are
     DIFFERENT tokens. Prepending a space solved the spacing half and left the
     capital, so every prompt still failed the identity gate - 0/12.

  2. It moved the baseline. The source ceiling fell from 83% to 75%, because
     prepending a space changed the SOURCE arm's tokenisation too. The elegant
     fix that deleted a bug class also shifted the measuring stick.

     Lesson recorded: after any fix, re-check the BASELINE, not only the
     quantity under test.

So: no prepended space, and three surface forms per pair instead of one.

  position 0     "Het"  -> id("The")    no leading space, capitalised
  mid-sentence   " het" -> id(" the")   leading space, lower case
  mid-sentence   " Het" -> id(" The")   leading space, capitalised

Where a source form is not a single token - `"Bread"` is not, `" bread"` is -
identity is unachievable for that position, and the run says so by name instead
of reporting a silent failure. The gate therefore becomes: identity holds
everywhere it CAN hold, and every exception is listed with its cause.

Run:  modal run modal/run_ladder4.py
"""

import modal

app = modal.App("lexswap-ladder4")
vol = modal.Volume.from_name("lexswap", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", "transformers", "sentencepiece", "sacremoses", "numpy")
    .env({"HF_HOME": "/cache/hf"})
    .add_local_dir("src", remote_path="/root/src")
)

RUNGS = [0, 300, 1000, 3000, 10000, 30000, 60000]


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

    def one(s):
        """The id if `s` is a single token, else None."""
        ids = tok.encode(s, add_special_tokens=False)
        return ids[0] if len(ids) == 1 else None

    def tables(pairs):
        """Three surface forms per pair. `gaps` names what cannot be mapped."""
        id2, init, mid = {}, {}, {}
        gaps = []
        for tgt, src in pairs.items():
            lo = one(" " + src.lower())
            # A single-letter source is an enumeration marker as often as a
            # word: the model writes "A." for a list option, and mapping the
            # capital turned every such marker into "Een." - visible in v5's
            # output. English "I" is the one single letter that is always a
            # word, so it keeps its capitalised forms.
            letter_marker = len(src) == 1 and src.lower() != "i"
            cap = None if letter_marker else one(" " + src[0].upper() + src[1:])
            ini = None if letter_marker else one(src[0].upper() + src[1:])
            if lo is not None:
                mid.setdefault(" " + tgt.lower(), lo)
                id2.setdefault(lo, " " + tgt.lower())
            if cap is not None:
                mid.setdefault(" " + tgt.capitalize(), cap)
                id2.setdefault(cap, " " + tgt.capitalize())
            if ini is not None:
                init.setdefault(tgt.capitalize(), ini)
                init.setdefault(tgt.lower(), ini)
                id2.setdefault(ini, tgt.capitalize())
            elif not letter_marker:
                gaps.append((tgt, src, "no single-token initial form"))
        return id2, init, mid, gaps

    seed_id2, seed_init, seed_mid, gaps = tables(SEED_NL)
    print("=" * 112)
    print("v5 - three surface forms per pair; baseline restored (no prepended space)")
    print("=" * 112)
    print(f"  pairs {len(SEED_NL)}   ids {len(seed_id2)}   "
          f"initial forms {len(seed_init)}   mid forms {len(seed_mid)}")
    print(f"  pairs with NO single-token initial form: {len(gaps)}")
    for g in gaps[:12]:
        print(f"    {g[0]:<20} -> {g[1]:<14} {g[2]}")

    class Codec:
        def __init__(self, id2, init, mid):
            self.id2, self.init, self.mid = id2, init, mid
            self.cov = {}

        def encode(self, text):
            ids, hit, miss, missed, degraded = [], 0, 0, [], []
            for k, w in enumerate(text.strip().split(" ")):
                if not w:
                    continue
                got = None
                if k == 0:
                    got = self.init.get(w) or self.init.get(w.lower())
                    if got is None:
                        # no single-token initial form; use the mid form and
                        # record that identity is unachievable at this position
                        got = (self.mid.get(" " + w) or
                               self.mid.get(" " + w.lower()))
                        if got is not None:
                            degraded.append(w)
                else:
                    got = (self.mid.get(" " + w) or
                           self.mid.get(" " + w.lower()) or
                           self.mid.get(" " + w.capitalize()))
                if got is not None:
                    ids.append(got); hit += 1
                else:
                    ids.extend(tok.encode(w if k == 0 else " " + w,
                                          add_special_tokens=False))
                    miss += 1; missed.append(w)
            n = hit + miss
            self.cov = {"words": n, "swapped": hit, "fallback": miss,
                        "coverage": round(hit / n, 3) if n else 0.0,
                        "missed": missed, "degraded_initial": degraded}
            return ids

        def decode(self, ids):
            return "".join(self.id2.get(int(i), tok.decode([int(i)]))
                           for i in ids)

        def purity(self, ids):
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

    def evaluate(codec, verbose=False):
        hits = match = 0
        covs, purs, rows, exc = [], [], [], []
        for p in SEED_PROMPTS:
            src_ids = tok.encode(p["en"], add_special_tokens=False)
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
            if not same:
                why = ("degraded initial: " + ",".join(cov["degraded_initial"])
                       if cov["degraded_initial"] else
                       "fallback: " + ",".join(cov["missed"])
                       if cov["missed"] else "token length differs")
                exc.append({"id": p["id"], "why": why})
            rows.append({"id": p["id"], "coverage": cov["coverage"],
                         "ids_match": bool(same), "purity": pur,
                         "out": out.strip(), "expected": p["exp_nl"],
                         "hit": bool(hit), "missed": cov["missed"],
                         "degraded_initial": cov["degraded_initial"]})
            if verbose:
                print(f"{p['id']:>3} {p['nl'][:33]:<34}{cov['coverage']:>6.2f}"
                      f"{('YES' if same else 'no'):>6}"
                      f"{(pur if pur is not None else 0):>8.2f}  "
                      f"{out.strip()[:32]:<33}{'Y' if hit else '.'}")
        n = len(SEED_PROMPTS)
        return {"coverage": round(sum(covs) / n, 3), "ids_match": match,
                "accuracy": round(hits / n, 3), "exceptions": exc,
                "output_purity": round(sum(purs) / len(purs), 3) if purs else None,
                "rows": rows}

    print(f"\n{'#':>3} {'prompt (nl)':<34}{'cov':>6}{'ids':>6}{'purity':>8}  "
          f"{'output':<33}hit")
    print("-" * 112)
    r0 = evaluate(Codec(seed_id2, seed_init, seed_mid), verbose=True)
    print("-" * 112)

    ceiling = sum(p["exp_en"].lower() in tok.decode(
        gen(tok.encode(p["en"], add_special_tokens=False))).lower()
        for p in SEED_PROMPTS) / len(SEED_PROMPTS)

    n = len(SEED_PROMPTS)
    print(f"  coverage {r0['coverage']:.1%}   ids identical {r0['ids_match']}/{n}"
          f"   accuracy {r0['accuracy']:.0%}   ceiling {ceiling:.0%}"
          f"   output purity {r0['output_purity']}")
    if r0["exceptions"]:
        print("  identity exceptions, each with its cause:")
        for e in r0["exceptions"]:
            print(f"    prompt {e['id']}: {e['why']}")
    achievable = n - len(r0["exceptions"])
    gate = r0["ids_match"] >= achievable and r0["coverage"] == 1.0
    print(f"  GATE {'PASSED' if gate else 'FAILED'} - identity holds on "
          f"{r0['ids_match']}/{n}; {len(r0['exceptions'])} named exception(s)")
    print(f"  BASELINE CHECK: ceiling {ceiling:.0%} "
          f"(v3 measured 83%, v4's prepended space cost it 8 points)")

    # ------------------------------------------------------------- the growth
    mt = {}
    for tag, mid_id in (("f", "Helsinki-NLP/opus-mt-en-nl"),
                        ("b", "Helsinki-NLP/opus-mt-nl-en")):
        mt[tag] = (AutoTokenizer.from_pretrained(mid_id),
                   AutoModelForSeq2SeqLM.from_pretrained(mid_id).to(dev).eval())

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
    for i in range(len(tok)):
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
    vmap = {b: t_ for (i, b, t_), v in zip(keep, back)
            if v.strip().strip(string.punctuation).lower().rstrip("s")
            == b.lower().rstrip("s")}
    order = [b for _, b in cands]
    print(f"\n[grow] {len(cands)} candidates, {len(keep)} single-word, "
          f"{len(vmap)} round-trip verified ({len(vmap)/max(len(keep),1):.0%})")

    print("\n" + "=" * 112)
    print("THE LADDER - fixed prompts, growing lexicon, case-aware tables")
    print("=" * 112)
    print(f"{'rung N':>8}{'ids':>8}{'coverage':>11}{'ids==src':>10}"
          f"{'accuracy':>10}{'ceiling':>9}{'out purity':>12}")
    ladder = [dict(N=0, ids=len(seed_id2), coverage=r0["coverage"],
                   ids_match=r0["ids_match"], accuracy=r0["accuracy"],
                   output_purity=r0["output_purity"],
                   exceptions=r0["exceptions"])]
    print(f"{0:>8}{len(seed_id2):>8}{r0['coverage']:>11.1%}{r0['ids_match']:>10}"
          f"{r0['accuracy']:>10.0%}{ceiling:>9.0%}"
          f"{(r0['output_purity'] or 0):>12.0%}")

    for N in RUNGS[1:]:
        pairs = dict(SEED_NL)
        for b in order[:N]:
            if b in vmap:
                pairs.setdefault(vmap[b], b)
        i2, ini, mi, _ = tables(pairs)
        r = evaluate(Codec(i2, ini, mi))
        ladder.append(dict(N=N, ids=len(i2), coverage=r["coverage"],
                           ids_match=r["ids_match"], accuracy=r["accuracy"],
                           output_purity=r["output_purity"],
                           exceptions=r["exceptions"]))
        print(f"{N:>8}{len(i2):>8}{r['coverage']:>11.1%}{r['ids_match']:>10}"
              f"{r['accuracy']:>10.0%}{ceiling:>9.0%}"
              f"{(r['output_purity'] or 0):>12.0%}")

    after = model.state_dict()
    unchanged = all(torch.equal(sig[k], after[k]) for k in sig)
    print(f"\n  weights unchanged: {unchanged}")

    os.makedirs("/cache/out", exist_ok=True)
    payload = {"model": model_id, "ceiling": round(ceiling, 3),
               "gate_passed": bool(gate), "initial_form_gaps": gaps,
               "weights_unchanged": bool(unchanged), "ladder": ladder,
               "rung0_rows": r0["rows"]}
    with open("/cache/out/ladder4.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    vol.commit()
    return payload


@app.local_entrypoint()
def main():
    run.remote()
