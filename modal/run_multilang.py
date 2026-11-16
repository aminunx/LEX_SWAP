"""LEX_SWAP v2 — Dutch vs Indonesian, one controlled difference.

The first run measured Dutch: the swap recovered 21% against 62% for native
English, and scored a flat 0% on subordinate clauses where Dutch puts the verb
last. That identified word order as the wall, but with a single language it
could not be told apart from the swap simply being weak.

So the same pipeline now runs a second language chosen to differ in exactly
that one property:

  Dutch       Germanic, verb-final subordinate clauses, four forms per verb
  Indonesian  Austronesian, SVO in every clause, NO verb conjugation

Both get the identical dictionary method, the identical four arms, and the
identical prompts. The only variable is the language. If `word_order` rises for
Indonesian, word order was the wall and the claim "yes for languages whose
order matches English" is carried by data.

Also fixes the largest measured loss. The first run lost 10,198 ids to
collisions, because a translation model fed a bare context-free word returns
the most frequent sense and many English words collapse onto one target word.
Every candidate mapping is now translated back, and kept only if the round trip
returns the word it started from. That trades coverage for precision, and both
numbers are reported.

Four arms per language:
  english    native English, original tokenizer       - the ceiling
  swap       target language -> swapped vocab         - the claim
  native     target language, original tokenizer      - required for attribution
  shuffled   the same pipeline, randomised dictionary - the floor

Run:  modal run modal/run_multilang.py
"""

import modal

app = modal.App("lexswap-multilang")
vol = modal.Volume.from_name("lexswap", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", "transformers", "sentencepiece", "sacremoses", "numpy")
    .env({"HF_HOME": "/cache/hf"})
    .add_local_dir("src", remote_path="/root/src")
)


@app.function(image=image, gpu="A10G", volumes={"/cache": vol}, timeout=14400)
def run(model_id: str = "Qwen/Qwen2.5-0.5B", n_vocab: int = 30_000,
        max_new: int = 8, seed: int = 0, roundtrip: bool = True):
    import json
    import os
    import random
    import sys

    import torch
    from transformers import (AutoModelForCausalLM, AutoModelForSeq2SeqLM,
                              AutoTokenizer)

    sys.path.insert(0, "/root")
    from src.lexswap.core import SwapCodec, build_table
    from src.lexswap.prompts import GROUPS, LANGS, PROMPTS

    random.seed(seed); torch.manual_seed(seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id).to(dev).eval()
    sig = {k: v.detach().clone() for k, v in
           list(model.state_dict().items())[:3]}
    print(f"[load] {model_id}  vocab={len(tok)}  device={dev}  "
          f"roundtrip={roundtrip}")

    def mt_pair(fwd_id, back_id):
        ft, fm = (AutoTokenizer.from_pretrained(fwd_id),
                  AutoModelForSeq2SeqLM.from_pretrained(fwd_id).to(dev).eval())
        bt, bm = (AutoTokenizer.from_pretrained(back_id),
                  AutoModelForSeq2SeqLM.from_pretrained(back_id).to(dev).eval())

        @torch.no_grad()
        def mk(t, m):
            def f(words):
                enc = t(list(words), return_tensors="pt", padding=True,
                        truncation=True).to(dev)
                out = m.generate(**enc, max_new_tokens=8, num_beams=1)
                return t.batch_decode(out, skip_special_tokens=True)
            return f
        return mk(ft, fm), mk(bt, bm)

    @torch.no_grad()
    def gen(ids):
        x = torch.tensor([ids], device=dev)
        out = model.generate(x, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
        return out[0, len(ids):].tolist()

    def plain(text):
        return tok.decode(gen(tok.encode(text, add_special_tokens=False))), \
               {"coverage": 1.0}

    results, tables = {}, {}
    for code, cfg in LANGS.items():
        print("\n" + "#" * 118)
        print(f"# {cfg['name']} ({cfg['family']}) — {cfg['note']}")
        print("#" * 118)

        fwd, back = mt_pair(cfg["mt"], cfg["back"])
        table = build_table(tok, fwd, n=n_vocab,
                            back_translate=back if roundtrip else None)
        print(f"[dict {code}] " + json.dumps(table.stats))
        tables[code] = table.stats

        shuf = build_table(tok, lambda ws: list(ws), n=n_vocab)
        vals = [shuf.id2tgt[i] for i in sorted(shuf.id2tgt)]
        random.Random(seed).shuffle(vals)
        shuf.id2tgt = dict(zip(sorted(shuf.id2tgt), vals))
        shuf.tgt2id = {}
        for i in sorted(shuf.id2tgt):
            shuf.tgt2id.setdefault(shuf.id2tgt[i], i)

        codec, codec_s = SwapCodec(tok, table), SwapCodec(tok, shuf)

        def swapped(text, c):
            ids = c.encode(text)
            return c.decode(gen(ids)), dict(c.last_coverage)

        rows, covs = [], []
        print(f"\n{'#':>3} {'group':<12}{'arm':<10}{'prompt':<36}"
              f"{'continuation':<24}{'hit':>4}{'cov':>6}")
        print("-" * 118)
        for p in PROMPTS:
            r = {"id": p["id"], "group": p["group"]}
            for arm in ("english", "swap", "native", "shuffled"):
                if arm == "english":
                    txt, exp = p["en"], p["exp_en"]
                    out, cov = plain(txt)
                else:
                    txt, exp = p[cfg["prompt"]], p[cfg["expect"]]
                    if arm == "native":
                        out, cov = plain(txt)
                    else:
                        out, cov = swapped(txt, codec if arm == "swap" else codec_s)
                hit = exp.lower() in out.lower()
                r[arm] = {"prompt": txt, "out": out.strip(), "expected": exp,
                          "hit": bool(hit), **cov}
                if arm == "swap":
                    covs.append(cov.get("coverage", 0.0))
                print(f"{p['id']:>3} {p['group']:<12}{arm:<10}{txt[:35]:<36}"
                      f"{out.strip()[:23]:<24}{'Y' if hit else '.':>4}"
                      f"{cov.get('coverage', 0):>6.2f}")
            rows.append(r)

        summary = {}
        print(f"\n{'group':<14}{'n':>4}" +
              "".join(f"{a:>12}" for a in ("english", "swap", "native", "shuffled")))
        for g in GROUPS + ["ALL"]:
            sel = [r for r in rows if g == "ALL" or r["group"] == g]
            summary[g] = {"n": len(sel)}
            line = f"{g:<14}{len(sel):>4}"
            for a in ("english", "swap", "native", "shuffled"):
                acc = sum(r[a]["hit"] for r in sel) / len(sel)
                summary[g][a] = round(acc, 3)
                line += f"{acc:>11.0%} "
            print(line)
        mc = sum(covs) / len(covs) if covs else 0.0
        print(f"  mean swap coverage {mc:.1%}")
        results[code] = {"summary": summary, "rows": rows,
                         "mean_coverage": round(mc, 3), "dict": table.stats}
        table.save(f"/cache/out/swap_{code}.json") if os.path.isdir("/cache/out") \
            else (os.makedirs("/cache/out", exist_ok=True),
                  table.save(f"/cache/out/swap_{code}.json"))

    # ------------------------------------------------------ the comparison
    print("\n" + "=" * 118)
    print("THE CONTROLLED COMPARISON — one variable: the language")
    print("=" * 118)
    print(f"{'group':<14}" + "".join(f"{LANGS[c]['name'][:10]:>22}" for c in LANGS))
    print(f"{'':<14}" + "".join(f"{'swap':>11}{'native':>11}" for _ in LANGS))
    for g in GROUPS + ["ALL"]:
        line = f"{g:<14}"
        for c in LANGS:
            s = results[c]["summary"][g]
            line += f"{s['swap']:>10.0%} {s['native']:>10.0%} "
        print(line)

    nl_wo = results["nl"]["summary"]["word_order"]["swap"]
    id_wo = results["idn"]["summary"]["word_order"]["swap"]
    print(f"\n  word_order under swap:  Dutch {nl_wo:.0%}   Indonesian {id_wo:.0%}")
    if id_wo > nl_wo:
        print("  -> word order was the wall. The claim is carried by data.")
    elif id_wo == nl_wo == 0:
        print("  -> both at zero. The wall is NOT word order alone - something")
        print("     deeper limits the swap, and that is the more valuable finding.")
    else:
        print("  -> Indonesian did not beat Dutch here. The word-order account")
        print("     does not survive, and must not be reported as if it did.")

    after = model.state_dict()
    ok = all(torch.equal(sig[k], after[k]) for k in sig)
    print(f"\n  weights unchanged: {ok}   <- the premise, verified not assumed")

    os.makedirs("/cache/out", exist_ok=True)
    payload = {"model": model_id, "n_vocab": n_vocab, "roundtrip": roundtrip,
               "weights_unchanged": bool(ok), "languages": results,
               "dicts": tables}
    with open("/cache/out/multilang.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    vol.commit()
    return payload


@app.local_entrypoint()
def main(n_vocab: int = 30_000, roundtrip: bool = True):
    run.remote(n_vocab=n_vocab, roundtrip=roundtrip)
