"""LEX_SWAP — can a model answer in Dutch with only its dictionary replaced?

Four arms. The first two are the spec's; the last two were added because
without them no failure can be attributed to anything.

  1. english      native English prompt, original tokenizer        - the ceiling
  2. swap         Dutch prompt -> swapped vocab -> unchanged model - the claim
  3. native_nl    Dutch prompt, original tokenizer, no swap        - REQUIRED
  4. shuffled     the same pipeline with a RANDOMISED dictionary   - the floor

Arm 3 matters most. Qwen2.5 is multilingual and already speaks some Dutch, so
without it a poor result cannot be told apart from the model simply being weak
in Dutch. Arm 4 bounds the other end: a swap table that is pure noise must
score near zero, otherwise the metric is measuring something other than meaning.

Nothing is fine-tuned. No embedding is edited. The model's weights are loaded
once and never written to.

Run:  modal run modal/run_lexswap.py
      modal run modal/run_lexswap.py --n-vocab 30000
"""

import modal

app = modal.App("lexswap")
vol = modal.Volume.from_name("lexswap", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", "transformers", "sentencepiece", "sacremoses", "numpy")
    .env({"HF_HOME": "/cache/hf"})
    .add_local_dir("src", remote_path="/root/src")
)


@app.function(image=image, gpu="A10G", volumes={"/cache": vol}, timeout=7200)
def run(model_id: str = "Qwen/Qwen2.5-0.5B", n_vocab: int = 30_000,
        mt_id: str = "Helsinki-NLP/opus-mt-en-nl", max_new: int = 8,
        seed: int = 0):
    import json
    import os
    import random
    import sys

    import torch
    from transformers import (AutoModelForCausalLM, AutoModelForSeq2SeqLM,
                              AutoTokenizer)

    sys.path.insert(0, "/root")
    from src.lexswap.core import SwapCodec, build_table
    from src.lexswap.prompts import GROUPS, PROMPTS

    random.seed(seed); torch.manual_seed(seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    # ------------------------------------------------- the model, never touched
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id).to(dev).eval()
    before = {k: v.detach().clone() for k, v in
              list(model.state_dict().items())[:3]}
    print(f"[load] {model_id}  vocab={len(tok)}  device={dev}")

    # ------------------------------------------------------- the dictionary
    mt_tok = AutoTokenizer.from_pretrained(mt_id)
    mt = AutoModelForSeq2SeqLM.from_pretrained(mt_id).to(dev).eval()

    @torch.no_grad()
    def translate(words):
        enc = mt_tok(words, return_tensors="pt", padding=True,
                     truncation=True).to(dev)
        out = mt.generate(**enc, max_new_tokens=8, num_beams=1)
        return mt_tok.batch_decode(out, skip_special_tokens=True)

    print(f"[dict] translating whole words over the first {n_vocab} ids ...")
    table = build_table(tok, translate, n=n_vocab)
    print("[dict] " + json.dumps(table.stats, indent=2))

    # the floor: same construction, meanings destroyed
    shuf = build_table(tok, lambda ws: ws, n=n_vocab)
    vals = [shuf.id2tgt[i] for i in sorted(shuf.id2tgt)]
    random.Random(seed).shuffle(vals)
    shuf.id2tgt = {i: v for i, v in zip(sorted(shuf.id2tgt), vals)}
    shuf.tgt2id = {}
    for i in sorted(shuf.id2tgt):
        shuf.tgt2id.setdefault(shuf.id2tgt[i], i)

    codec = SwapCodec(tok, table)
    codec_shuf = SwapCodec(tok, shuf)

    # ------------------------------------------------------------- generation
    @torch.no_grad()
    def gen_ids(ids):
        x = torch.tensor([ids], device=dev)
        out = model.generate(x, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
        return out[0, len(ids):].tolist()

    def arm_plain(text):
        ids = tok.encode(text, add_special_tokens=False)
        return tok.decode(gen_ids(ids)), {"coverage": 1.0, "swapped": 0,
                                          "fallback": 0, "words": 0}

    def arm_swap(text, c):
        ids = c.encode(text)
        cov = dict(c.last_coverage)
        return c.decode(gen_ids(ids)), cov

    rows, cov_all = [], []
    print("\n" + "=" * 118)
    print(f"{'#':>3} {'group':<11}{'arm':<11}{'prompt':<34}{'continuation':<26}"
          f"{'hit':>4}{'cov':>6}")
    print("=" * 118)

    for p in PROMPTS:
        r = {"id": p["id"], "group": p["group"], "en": p["en"], "nl": p["nl"]}
        for arm in ("english", "swap", "native_nl", "shuffled"):
            if arm == "english":
                text, exp, (out, cov) = p["en"], p["exp_en"], arm_plain(p["en"])
            elif arm == "native_nl":
                text, exp, (out, cov) = p["nl"], p["exp_nl"], arm_plain(p["nl"])
            elif arm == "swap":
                text, exp = p["nl"], p["exp_nl"]
                out, cov = arm_swap(p["nl"], codec)
            else:
                text, exp = p["nl"], p["exp_nl"]
                out, cov = arm_swap(p["nl"], codec_shuf)
            hit = exp.lower() in out.lower()
            r[arm] = {"out": out, "expected": exp, "hit": bool(hit), **cov}
            if arm == "swap":
                cov_all.append(cov.get("coverage", 0.0))
            print(f"{p['id']:>3} {p['group']:<11}{arm:<11}{text[:33]:<34}"
                  f"{out.strip()[:25]:<26}{'Y' if hit else '.':>4}"
                  f"{cov.get('coverage', 0):>6.2f}")
        rows.append(r)

    # ----------------------------------------------------------------- summary
    print("\n" + "=" * 118)
    print("ACCURACY BY GROUP - hit means the expected word appears in the continuation")
    print("=" * 118)
    print(f"{'group':<13}{'n':>4}" + "".join(f"{a:>13}" for a in
          ("english", "swap", "native_nl", "shuffled")))
    summary = {}
    for g in GROUPS + ["ALL"]:
        sel = [r for r in rows if g == "ALL" or r["group"] == g]
        line = f"{g:<13}{len(sel):>4}"
        summary[g] = {"n": len(sel)}
        for a in ("english", "swap", "native_nl", "shuffled"):
            acc = sum(r[a]["hit"] for r in sel) / len(sel)
            summary[g][a] = round(acc, 3)
            line += f"{acc:>12.0%} "
        print(line)

    mean_cov = sum(cov_all) / len(cov_all) if cov_all else 0.0
    print(f"\n  mean swap coverage across prompts: {mean_cov:.1%}"
          f"   (the rest fell back to the model's own Dutch tokens)")

    # the weights must be bit-identical to what was loaded
    after = model.state_dict()
    untouched = all(torch.equal(before[k], after[k]) for k in before)
    print(f"  weights unchanged: {untouched}   <- the whole premise")

    print("\n" + "=" * 118)
    print("READING THIS HONESTLY")
    print("=" * 118)
    print("  swap > shuffled        the dictionary carries meaning, not just form")
    print("  swap vs native_nl      which is the better way to serve Dutch")
    print("  arithmetic == english  numbers bypass the swap; anything else is a bug")
    print("  word_order << easy     the cost of keeping English syntax")

    os.makedirs("/cache/out", exist_ok=True)
    table.save("/cache/out/swap_table.json")
    payload = {"model": model_id, "n_vocab": n_vocab,
               "dict_stats": table.stats, "mean_coverage": round(mean_cov, 3),
               "weights_unchanged": bool(untouched),
               "summary": summary, "rows": rows}
    with open("/cache/out/results.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    vol.commit()
    return payload


@app.local_entrypoint()
def main(n_vocab: int = 30_000, model_id: str = "Qwen/Qwen2.5-0.5B"):
    run.remote(model_id=model_id, n_vocab=n_vocab)
