"""LEX_SWAP v8 — recover the renderings v7 threw away, and decompose what is left.

FIX. v7 keyed both directions on the Dutch word, so when big, large and great
all map to groot, only one survived and the other two ids were left with no
Dutch rendering at all. 27,955 dictionary matches collapsed to 17,201 pairs:
10,754 renderings discarded for no reason, which is most of why output purity
moved only two points.

A collision constrains INPUT only. Dutch `groot` must choose one id to encode
to. On OUTPUT several ids can all render as `groot` with no conflict. So the
decode map is now built from every match; only the encode map keeps first-wins.

DIAGNOSTIC. "How much is left" answered by decomposition, not estimate. Every
generated token the lexicon cannot render goes into one of three buckets:

  subword_fragment         a BPE piece like `ing`. NO word-level translation
                           exists, in MUSE or in any human dictionary. This
                           share is a HARD CEILING on the method.
  whole_word_no_entry      reachable by a larger dictionary.
  whole_word_entry_exists  the entry exists and was not mapped - a code bug,
                           free to fix.

The first bucket is the honest answer to the question, and producing that number
is why this run exists.

Run:  modal run modal/run_real_dict2.py
"""

import modal

app = modal.App("lexswap-realdict2")
vol = modal.Volume.from_name("lexswap", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", "transformers", "requests", "numpy")
    .env({"HF_HOME": "/cache/hf"})
    .add_local_dir("src", remote_path="/root/src")
)

MUSE_URLS = [
    "https://dl.fbaipublicfiles.com/arrival/dictionaries/en-nl.txt",
    "https://dl.fbaipublicfiles.com/arrival/dictionaries/en-nl.0-5000.txt",
    "https://dl.fbaipublicfiles.com/arrival/dictionaries/en-nl.5000-6500.txt",
]
BATCH = 10_000
BAR = "=" * 112


@app.function(image=image, gpu="A10G", volumes={"/cache": vol}, timeout=14400)
def run(model_id: str = "Qwen/Qwen2.5-0.5B", max_new: int = 8, seed: int = 0):
    import json
    import os
    import string
    import sys

    import requests
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    sys.path.insert(0, "/root")
    from src.lexswap.seed_nl import SEED_NL, SEED_PROMPTS

    torch.manual_seed(seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    AL = set(string.ascii_letters)

    print(BAR)
    print("STEP 1 - a REAL bilingual dictionary; no machine translation")
    print(BAR)
    muse, sources = {}, []
    for url in MUSE_URLS:
        name = url.split("/")[-1]
        try:
            r = requests.get(url, timeout=120)
            if r.status_code != 200:
                print("  {:<26} HTTP {}".format(name, r.status_code))
                continue
            n0 = len(muse)
            for line in r.text.splitlines():
                parts = line.strip().split()
                if len(parts) == 2:
                    muse.setdefault(parts[0].lower(), parts[1])
            sources.append({"url": url, "new_pairs": len(muse) - n0})
            print("  {:<26} +{} pairs".format(name, len(muse) - n0))
        except Exception as e:
            print("  {:<26} FAILED {}".format(name, type(e).__name__))

    print("")
    print("  real dictionary: {} English headwords".format(len(muse)))
    if len(muse) < 1000:
        print("  *** STOPPING - dictionary unavailable, and this run does not")
        print("  *** fall back to machine translation.")
        return {"stopped": "dictionary_unavailable", "headwords": len(muse)}

    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id).to(dev).eval()
    sig = {k: v.detach().clone() for k, v in list(model.state_dict().items())[:3]}

    print("")
    print(BAR)
    print("STEP 2 - the whole vocabulary, in batches of {}".format(BATCH))
    print(BAR)
    print("{:>14}{:>9}{:>9}{:>10}{:>11}{:>12}".format(
        "batch", "words", "matched", "no entry", "multiword", "enc pairs"))

    enc_pairs = dict(SEED_NL)
    dec_extra = {}
    gaps = {"no_entry": [], "multiword": []}
    V = len(tok)
    log = []
    for start in range(0, V, BATCH):
        words = matched = no_entry = multiword = 0
        for i in range(start, min(start + BATCH, V)):
            s = tok.decode([i])
            b = s.lstrip(" ")
            if not (s.startswith(" ") and len(b) > 1 and all(c in AL for c in b)):
                continue
            words += 1
            hit = muse.get(b.lower())
            if hit is None:
                no_entry += 1
                if len(gaps["no_entry"]) < 400:
                    gaps["no_entry"].append(b)
                continue
            if " " in hit or not all(c in AL for c in hit):
                multiword += 1
                if len(gaps["multiword"]) < 200:
                    gaps["multiword"].append([b, hit])
                continue
            enc_pairs.setdefault(hit, b)
            dec_extra[i] = hit
            matched += 1
        log.append({"start": start, "words": words, "matched": matched,
                    "no_entry": no_entry, "multiword": multiword,
                    "enc_pairs": len(enc_pairs)})
        if words:
            print("{:>8}-{:<5}{:>9}{:>9}{:>10}{:>11}{:>12}".format(
                start, min(start + BATCH, V), words, matched, no_entry,
                multiword, len(enc_pairs)))

    tw = sum(x["words"] for x in log)
    tm = sum(x["matched"] for x in log)
    print("")
    print("  whole-word tokens in vocabulary : {}".format(tw))
    print("  matched by the real dictionary  : {}  ({:.1%})".format(tm, tm / max(tw, 1)))
    print("  no dictionary entry             : {}".format(
        sum(x["no_entry"] for x in log)))
    print("  entry was multi-word            : {}".format(
        sum(x["multiword"] for x in log)))
    print("  encode pairs (collisions bite)  : {}".format(len(enc_pairs)))
    print("  decode renderings (no collision): {}".format(len(dec_extra)))
    print("  no-entry sample  : {}".format(gaps["no_entry"][:16]))
    print("  multiword sample : {}".format(gaps["multiword"][:6]))

    def one(s):
        ids = tok.encode(s, add_special_tokens=False)
        return ids[0] if len(ids) == 1 else None

    def tables(pairs):
        id2, init, mid = {}, {}, {}
        for tgt, src in pairs.items():
            marker = len(src) == 1 and src.lower() != "i"
            lo = one(" " + src.lower())
            cap = None if marker else one(" " + src[0].upper() + src[1:])
            ini = None if marker else one(src[0].upper() + src[1:])
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
        return id2, init, mid

    id2, init, mid = tables(enc_pairs)
    before = len(id2)
    for tid, nl_word in dec_extra.items():
        id2.setdefault(tid, " " + nl_word)
    print("  decode map {} -> {} ids  (+{} recovered from collisions)".format(
        before, len(id2), len(id2) - before))

    class Codec:
        def __init__(self):
            self.cov = {}

        def encode(self, text):
            ids, hit, miss, missed = [], 0, 0, []
            for k, w in enumerate(text.strip().split(" ")):
                if not w:
                    continue
                if k == 0:
                    got = (init.get(w) or init.get(w.lower()) or
                           mid.get(" " + w) or mid.get(" " + w.lower()))
                else:
                    got = (mid.get(" " + w) or mid.get(" " + w.lower()) or
                           mid.get(" " + w.capitalize()))
                if got is not None:
                    ids.append(got)
                    hit += 1
                else:
                    ids.extend(tok.encode(w if k == 0 else " " + w,
                                          add_special_tokens=False))
                    miss += 1
                    missed.append(w)
            n = hit + miss
            self.cov = {"coverage": round(hit / n, 3) if n else 0.0,
                        "missed": missed}
            return ids

        def decode(self, ids):
            return "".join(id2.get(int(i), tok.decode([int(i)])) for i in ids)

        def purity(self, ids):
            real = [int(i) for i in ids
                    if any(c in AL for c in tok.decode([int(i)]))]
            if not real:
                return None
            return round(sum(int(i) in id2 for i in real) / len(real), 3)

    codec = Codec()

    @torch.no_grad()
    def gen(ids):
        x = torch.tensor([ids], device=dev)
        o = model.generate(x, max_new_tokens=max_new, do_sample=False,
                           pad_token_id=tok.eos_token_id)
        return o[0, len(ids):].tolist()

    print("")
    print(BAR)
    print("STEP 3 - evaluate")
    print(BAR)
    print("{:>3} {:<33}{:>6}{:>5}{:>8}  {:<37}hit".format(
        "#", "prompt (nl)", "cov", "id", "purity", "output"))
    print("-" * 112)
    hits = match = 0
    covs, purs, rows, gen_cache = [], [], [], []
    for p in SEED_PROMPTS:
        src_ids = tok.encode(p["en"], add_special_tokens=False)
        ids = codec.encode(p["nl"])
        cov = dict(codec.cov)
        same = ids == src_ids
        oid = gen(ids)
        gen_cache.append(oid)
        out = codec.decode(oid)
        pur = codec.purity(oid)
        hit = p["exp_nl"].lower() in out.lower()
        hits += hit
        match += same
        covs.append(cov["coverage"])
        if pur is not None:
            purs.append(pur)
        rows.append({"id": p["id"], "nl": p["nl"], "out": out.strip(),
                     "expected": p["exp_nl"], "hit": bool(hit),
                     "ids_match": bool(same), "purity": pur,
                     "coverage": cov["coverage"], "missed": cov["missed"]})
        print("{:>3} {:<33}{:>6.2f}{:>5}{:>8.2f}  {:<37}{}".format(
            p["id"], p["nl"][:32], cov["coverage"], "Y" if same else ".",
            pur if pur is not None else 0.0, out.strip()[:36],
            "Y" if hit else "."))
    print("-" * 112)

    n = len(SEED_PROMPTS)
    ceiling = sum(p["exp_en"].lower() in tok.decode(
        gen(tok.encode(p["en"], add_special_tokens=False))).lower()
        for p in SEED_PROMPTS) / n
    purity = round(sum(purs) / len(purs), 3) if purs else None
    print("  lexicon ids      {}".format(len(id2)))
    print("  input coverage   {:.1%}".format(sum(covs) / n))
    print("  ids identical    {}/{}".format(match, n))
    print("  accuracy         {:.0%}".format(hits / n))
    print("  ceiling (source) {:.0%}".format(ceiling))
    print("  OUTPUT PURITY    {}   (0.67 with MT, 0.689 before this fix)".format(purity))

    print("")
    print(BAR)
    print("WHAT IS LEFT - every un-renderable generated token, decomposed")
    print(BAR)
    buckets = {"subword_fragment": 0, "whole_word_no_entry": 0,
               "whole_word_entry_exists": 0}
    examples = {k: [] for k in buckets}
    total = 0
    for oid in gen_cache:
        for t in oid:
            d = tok.decode([int(t)])
            if not any(c in AL for c in d):
                continue
            total += 1
            if int(t) in id2:
                continue
            b = d.lstrip(" ")
            if not d.startswith(" ") or not all(c in AL for c in b):
                k = "subword_fragment"
            elif b.lower() in muse:
                k = "whole_word_entry_exists"
            else:
                k = "whole_word_no_entry"
            buckets[k] += 1
            if len(examples[k]) < 12:
                examples[k].append(d)
    bad = sum(buckets.values())
    print("  generated word-like tokens : {}".format(total))
    print("  rendered in Dutch          : {}  ({:.1%})".format(
        total - bad, (total - bad) / max(total, 1)))
    print("  NOT rendered               : {}  ({:.1%})".format(
        bad, bad / max(total, 1)))
    print("")
    for k in ("subword_fragment", "whole_word_no_entry",
              "whole_word_entry_exists"):
        print("    {:<26}{:>5}  ({:>3.0%} of the gap)  {}".format(
            k, buckets[k], buckets[k] / max(bad, 1), examples[k][:9]))
    hard = buckets["subword_fragment"] / max(total, 1)
    print("")
    print("  HARD CEILING: subword fragments are {:.1%} of all generated".format(hard))
    print("  word-like tokens. A BPE piece has no word-level translation in MUSE")
    print("  or in any human dictionary, so dictionary work alone cannot take")
    print("  purity above {:.1%}.".format(1 - hard))
    print("  REACHABLE: whole_word_no_entry, {} tokens, {:.0%} of the gap.".format(
        buckets["whole_word_no_entry"],
        buckets["whole_word_no_entry"] / max(bad, 1)))

    after = model.state_dict()
    unchanged = all(torch.equal(sig[k], after[k]) for k in sig)
    print("")
    print("  weights unchanged: {}".format(unchanged))

    os.makedirs("/cache/out", exist_ok=True)
    payload = {"model": model_id, "dictionary": "MUSE en-nl",
               "dict_sources": sources, "dict_headwords": len(muse),
               "vocab_whole_words": tw, "matched_by_dict": tm,
               "encode_pairs": len(enc_pairs),
               "decode_renderings": len(dec_extra),
               "lexicon_ids": len(id2), "batches": log,
               "coverage": round(sum(covs) / n, 3), "ids_match": match,
               "accuracy": round(hits / n, 3), "ceiling": round(ceiling, 3),
               "output_purity": purity, "impurity_buckets": buckets,
               "impurity_examples": examples, "generated_wordlike": total,
               "not_rendered": bad, "hard_ceiling_purity": round(1 - hard, 3),
               "weights_unchanged": bool(unchanged), "rows": rows,
               "gaps_sample": gaps}
    with open("/cache/out/realdict2.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    vol.commit()
    return payload


@app.local_entrypoint()
def main():
    run.remote()
