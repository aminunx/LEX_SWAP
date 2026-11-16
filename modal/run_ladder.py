"""LEX_SWAP v3 — the ladder. One rung at a time, as the project owner directed.

The first two runs changed five things at once: coverage, collisions, word
sense, word order and morphology. So when Dutch scored 32% and Indonesian 21%,
neither number could be attributed to anything. And a prediction made on that
basis was wrong: Indonesian was supposed to beat Dutch on word_order because it
is SVO with no conjugation, and it scored 0% against Dutch's 12%. The word-order
account did not survive, which is exactly the lesson - with five variables
moving, I believed I knew which one was responsible, and I did not.

So: start as small as a thing can be, verify it completely, then grow one rung
at a time and watch where it breaks.

  rung 0   hand-made seed lexicon, ~60 pairs, 100% coverage on its own prompts.
           NOT an experiment yet - a CORRECTNESS TEST. Every Dutch prompt is a
           word-for-word parallel of its English twin through the seed, so the
           swap arm must encode to the SAME ids and produce an IDENTICAL
           continuation. If it does not, the codec is broken and nothing above
           this rung means anything.

  rung 1+  the seed, plus the N most frequent whole words auto-translated with
           round-trip verification, for N in 100, 300, 1000, 3000, 10000.
           The seed always wins a conflict, so the clean core is never
           overwritten by machine translation.

The prompt set is FIXED across all rungs. Only the lexicon grows. So accuracy
as a function of N isolates one thing: how much noise automatic translation
injects, and at what size it starts to cost more than it adds.

Run:  modal run modal/run_ladder.py
"""

import modal

app = modal.App("lexswap-ladder")
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
    from src.lexswap.seed_nl import SEED_NL, SEED_PROMPTS, check

    torch.manual_seed(seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id).to(dev).eval()
    sig = {k: v.detach().clone() for k, v in list(model.state_dict().items())[:3]}

    # --------------------------------------------------- rung 0: verify the seed
    rep = check(tok)
    print("=" * 110)
    print("RUNG 0 - verifying the hand-made seed before using it")
    print("=" * 110)
    print(f"  pairs declared        : {len(SEED_NL)}")
    print(f"  usable (1 token each) : {len(rep['usable'])}")
    if rep["multi_token"]:
        print(f"  DROPPED, multi-token  : "
              f"{[(nl, en, k) for nl, en, k in rep['multi_token']]}")
    if rep["english_side_shared"]:
        print(f"  English side shared   : {rep['english_side_shared']}")
        print("    (several Dutch words meaning one English word - expected for")
        print("     de/het, and harmless for encoding)")

    def build_seed_tables():
        id2 = {}
        tgt2 = {}
        for nl, en in SEED_NL.items():
            ids = tok.encode(" " + en, add_special_tokens=False)
            if len(ids) != 1:
                continue
            i = ids[0]
            tgt2.setdefault(" " + nl, i)
            tgt2.setdefault(" " + nl.capitalize(), i)
            id2.setdefault(i, " " + nl)
        return id2, tgt2

    seed_id2, seed_tgt2 = build_seed_tables()
    print(f"  seed covers {len(seed_id2)} distinct ids, "
          f"{len(seed_tgt2)} Dutch surface forms")

    # ------------------------------------------------------------ the codec
    class Codec:
        def __init__(self, id2, tgt2):
            self.id2, self.tgt2 = id2, tgt2
            self.cov = {}

        def encode(self, text):
            ids, hit, miss, missed = [], 0, 0, []
            for k, w in enumerate(text.split(" ")):
                if not w:
                    continue
                key = w if k == 0 else " " + w
                got = (self.tgt2.get(key) or self.tgt2.get(" " + w) or
                       self.tgt2.get(" " + w.lower()) or
                       self.tgt2.get(" " + w.capitalize()))
                if got is not None:
                    ids.append(got); hit += 1
                else:
                    ids.extend(tok.encode(key, add_special_tokens=False))
                    miss += 1; missed.append(w)
            n = hit + miss
            self.cov = {"words": n, "swapped": hit, "fallback": miss,
                        "coverage": round(hit / n, 3) if n else 0.0,
                        "missed": missed}
            return ids

        def decode(self, ids):
            return "".join(self.id2.get(int(i), tok.decode([int(i)]))
                           for i in ids)

    @torch.no_grad()
    def gen(ids):
        x = torch.tensor([ids], device=dev)
        out = model.generate(x, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
        return out[0, len(ids):].tolist()

    # ------------------------------------- rung 0 run: ids must match exactly
    codec0 = Codec(seed_id2, seed_tgt2)
    print(f"\n{'#':>3} {'prompt (nl)':<36}{'cov':>6}{'ids match en':>14}"
          f"  {'swap output':<22}{'english output':<22}")
    print("-" * 110)
    identical, rows0 = 0, []
    for p in SEED_PROMPTS:
        en_ids = tok.encode(p["en"], add_special_tokens=False)
        nl_ids = codec0.encode(p["nl"])
        cov = dict(codec0.cov)
        same = en_ids == nl_ids
        identical += int(same)
        en_out = tok.decode(gen(en_ids))
        nl_out = codec0.decode(gen(nl_ids))
        rows0.append({"id": p["id"], "coverage": cov["coverage"],
                      "ids_match": bool(same), "missed": cov["missed"],
                      "en_out": en_out.strip(), "swap_out": nl_out.strip(),
                      "exp_nl": p["exp_nl"],
                      "hit": p["exp_nl"].lower() in nl_out.lower()})
        print(f"{p['id']:>3} {p['nl'][:35]:<36}{cov['coverage']:>6.2f}"
              f"{('YES' if same else 'no'):>14}  {nl_out.strip()[:21]:<22}"
              f"{en_out.strip()[:21]:<22}")
        if cov["missed"]:
            print(f"      not in seed: {cov['missed']}")

    cov0 = sum(r["coverage"] for r in rows0) / len(rows0)
    acc0 = sum(r["hit"] for r in rows0) / len(rows0)
    print("-" * 110)
    print(f"  mean coverage {cov0:.1%}   ids identical to English "
          f"{identical}/{len(SEED_PROMPTS)}   accuracy {acc0:.0%}")
    gate = identical == len(SEED_PROMPTS) and cov0 == 1.0
    if gate:
        print("  RUNG 0 PASSED - the codec is correct; the swap reproduces")
        print("  English exactly, which is what a lossless lexicon must do.")
    else:
        print("  RUNG 0 FAILED - the codec or the seed is wrong. Everything")
        print("  above this rung is uninterpretable until this is fixed.")

    # ------------------------------------------------ rungs 1+: grow the lexicon
    mt_t = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-en-nl")
    mt_f = AutoModelForSeq2SeqLM.from_pretrained(
        "Helsinki-NLP/opus-mt-en-nl").to(dev).eval()
    bk_t = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-nl-en")
    bk_f = AutoModelForSeq2SeqLM.from_pretrained(
        "Helsinki-NLP/opus-mt-nl-en").to(dev).eval()

    @torch.no_grad()
    def tr(t, m, words):
        out = []
        for k in range(0, len(words), 64):
            enc = t(words[k:k + 64], return_tensors="pt", padding=True,
                    truncation=True).to(dev)
            g = m.generate(**enc, max_new_tokens=8, num_beams=1)
            out += t.batch_decode(g, skip_special_tokens=True)
        return out

    AL = set(string.ascii_letters)
    cands = []
    for i in range(30_000):
        s = tok.decode([i])
        b = s.lstrip(" ")
        if s.startswith(" ") and len(b) > 1 and all(c in AL for c in b):
            cands.append((i, s, b))
    print(f"\n[grow] {len(cands)} whole-word candidates in the first 30000 ids")

    biggest = max(RUNGS)
    sub = cands[:biggest]
    fwd = tr(mt_t, mt_f, [b for _, _, b in sub])
    keep = [(i, s, b, f.strip().split()) for (i, s, b), f in zip(sub, fwd)]
    keep = [(i, s, b, f[0]) for i, s, b, f in keep
            if len(f) == 1 and all(c in AL for c in f[0])]
    back = tr(bk_t, bk_f, [t_ for _, _, _, t_ in keep])
    verified = [(i, s, b, t_) for (i, s, b, t_), v in zip(keep, back)
                if v.strip().strip(string.punctuation).lower().rstrip("s")
                == b.lower().rstrip("s")]
    print(f"[grow] {len(keep)} single-word translations, "
          f"{len(verified)} survived the round trip "
          f"({len(verified) / max(len(keep), 1):.0%})")
    vmap = {i: (s, t_) for i, s, _, t_ in verified}

    print("\n" + "=" * 110)
    print("THE LADDER - same prompts at every rung; only the lexicon grows")
    print("=" * 110)
    print(f"{'rung N':>8}{'lexicon ids':>13}{'coverage':>11}{'ids==en':>9}"
          f"{'accuracy':>10}{'english':>9}")
    ladder = [{"N": 0, "ids": len(seed_id2), "coverage": round(cov0, 3),
               "ids_match": identical, "accuracy": round(acc0, 3),
               "rows": rows0}]
    en_acc = sum(p["exp_en"].lower() in tok.decode(
        gen(tok.encode(p["en"], add_special_tokens=False))).lower()
        for p in SEED_PROMPTS) / len(SEED_PROMPTS)
    print(f"{0:>8}{len(seed_id2):>13}{cov0:>11.1%}"
          f"{identical:>9}{acc0:>10.0%}{en_acc:>9.0%}")

    for N in RUNGS[1:]:
        id2 = dict(seed_id2)
        tgt2 = dict(seed_tgt2)
        for i, s, b in cands[:N]:
            if i in vmap and i not in id2:
                _, t_ = vmap[i]
                id2[i] = " " + t_
                tgt2.setdefault(" " + t_, i)
                tgt2.setdefault(" " + t_.capitalize(), i)
        c = Codec(id2, tgt2)
        hits, match, covs, rows = 0, 0, [], []
        for p in SEED_PROMPTS:
            ids = c.encode(p["nl"])
            cov = dict(c.cov)
            same = ids == tok.encode(p["en"], add_special_tokens=False)
            out = c.decode(gen(ids))
            hit = p["exp_nl"].lower() in out.lower()
            hits += hit; match += same; covs.append(cov["coverage"])
            rows.append({"id": p["id"], "out": out.strip(), "hit": bool(hit),
                         "ids_match": bool(same), "coverage": cov["coverage"]})
        cv, ac = sum(covs) / len(covs), hits / len(SEED_PROMPTS)
        ladder.append({"N": N, "ids": len(id2), "coverage": round(cv, 3),
                       "ids_match": match, "accuracy": round(ac, 3),
                       "rows": rows})
        print(f"{N:>8}{len(id2):>13}{cv:>11.1%}{match:>9}{ac:>10.0%}"
              f"{en_acc:>9.0%}")

    print("\n" + "=" * 110)
    print("HOW TO READ THE LADDER")
    print("=" * 110)
    print("  accuracy flat at the English level   the lexicon is lossless so far")
    print("  accuracy falls as N grows            machine translation is")
    print("                                       injecting noise; the rung")
    print("                                       where it turns is the budget")
    print("  ids==en drops below 12               a growth entry OVERWROTE a")
    print("                                       seed word - a bug, not a finding")

    after = model.state_dict()
    unchanged = all(torch.equal(sig[k], after[k]) for k in sig)
    print(f"\n  weights unchanged: {unchanged}")

    os.makedirs("/cache/out", exist_ok=True)
    payload = {"model": model_id, "rung0_gate": bool(gate),
               "english_accuracy": round(en_acc, 3),
               "seed_report": {"declared": len(SEED_NL),
                               "usable": len(rep["usable"]),
                               "multi_token": rep["multi_token"],
                               "shared_english": rep["english_side_shared"]},
               "weights_unchanged": bool(unchanged), "ladder": ladder}
    with open("/cache/out/ladder.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    vol.commit()
    return payload


@app.local_entrypoint()
def main():
    run.remote()
