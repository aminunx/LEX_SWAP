"""LEX_SWAP v9 — three fixes, each traced to a cause the diagnostic named.

v8's decomposition reported 18.3% of generated tokens un-renderable, 83% of
that being `subword_fragment`, and concluded a hard ceiling of 84.8%. The
examples were `['A','B','A','B','A','B','A','B','innamon']`.

So the conclusion was wrong, and for three separate reasons that had been
collapsed into one bucket.

FIX 1 - a METRIC bug, not a lexicon gap.
  `A` and `B` are multiple-choice list markers, not subword fragments. They
  classified as fragments only because they carry no leading space. A single
  letter is as language-neutral as a digit - `A.` is `A.` in Dutch too - and
  the purity metric already excludes digits and punctuation for exactly that
  reason. It should have excluded single letters.
  The reported 84.8% ceiling was an artefact of this misclassification.

FIX 2 - MUSE genuinely lacks common function words.
  ` If`, ` It`, ` at` came back as `whole_word_no_entry`, and the
  `whole_word_entry_exists` bucket was zero, so they are absent from the
  82,167-headword file rather than mishandled. MUSE is built by word alignment
  and curated for bilingual lexicon induction, so some closed-class words are
  simply not in it. Supplied by hand - few, closed-class, checkable.

FIX 3 - real fragments get a morphological mapping.
  `innamon` from `cinnamon` has no word-level entry anywhere, because it is not
  a word. English-Dutch suffixes do correspond regularly, so fragments are
  rendered through a suffix map.
  DECODE ONLY: input is whole words, so adding fragments to the encode tables
  would change a prompt's token ids and break the identity gate for nothing.

Also reports the remaining gaps ranked by token id, which is a frequency proxy,
so the next supplement is targeted rather than guessed.

Run:  modal run modal/run_v9.py
"""

import modal

app = modal.App("lexswap-v9")
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
BAR = "=" * 112


@app.function(image=image, gpu="A10G", volumes={"/cache": vol}, timeout=14400)
def run(model_id: str = "Qwen/Qwen2.5-0.5B", max_new: int = 8, seed: int = 0,
        use_suffix: bool = True):
    import json
    import os
    import string
    import sys

    import requests
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    sys.path.insert(0, "/root")
    from src.lexswap.seed_nl import SEED_NL, SEED_PROMPTS
    from src.lexswap.supplement_nl import (SUFFIX_NL, SUPPLEMENT_NL,
                                           is_language_neutral)

    torch.manual_seed(seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    AL = set(string.ascii_letters)

    muse, sources = {}, []
    for url in MUSE_URLS:
        name = url.split("/")[-1]
        try:
            r = requests.get(url, timeout=120)
            if r.status_code != 200:
                continue
            n0 = len(muse)
            for line in r.text.splitlines():
                p = line.strip().split()
                if len(p) == 2:
                    muse.setdefault(p[0].lower(), p[1])
            sources.append({"url": url, "new_pairs": len(muse) - n0})
        except Exception:
            pass
    print("  real dictionary: {} headwords".format(len(muse)))
    if len(muse) < 1000:
        print("  *** STOPPING - dictionary unavailable; no MT fallback.")
        return {"stopped": "dictionary_unavailable"}

    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id).to(dev).eval()
    sig = {k: v.detach().clone() for k, v in list(model.state_dict().items())[:3]}
    V = len(tok)

    # hand-made first: seed, then supplement, then the dictionary
    enc_pairs = dict(SEED_NL)
    for k, v in SUPPLEMENT_NL.items():
        enc_pairs.setdefault(k, v)
    print("  hand-made pairs: {} seed + {} supplement".format(
        len(SEED_NL), len(SUPPLEMENT_NL)))

    dec_extra, frag_map = {}, {}
    gaps = []
    words = matched = no_entry = multiword = 0
    for i in range(V):
        s = tok.decode([i])
        b = s.lstrip(" ")
        if not b or not all(c in AL for c in b):
            continue
        if s.startswith(" ") and len(b) > 1:
            words += 1
            hit = muse.get(b.lower())
            if hit is None:
                no_entry += 1
                if len(gaps) < 600:
                    gaps.append([i, b])
                continue
            if " " in hit or not all(c in AL for c in hit):
                multiword += 1
                continue
            enc_pairs.setdefault(hit, b)
            dec_extra[i] = hit
            matched += 1
        elif use_suffix and not s.startswith(" ") and len(b) > 1:
            # FIX 3: a true fragment. Longest matching suffix wins.
            for suf in sorted(SUFFIX_NL, key=len, reverse=True):
                if b.lower().endswith(suf):
                    frag_map[i] = b[: len(b) - len(suf)] + SUFFIX_NL[suf]
                    break

    print("  vocabulary whole words {}   matched {} ({:.1%})   no entry {}"
          " multiword {}".format(words, matched, matched / max(words, 1),
                                 no_entry, multiword))
    print("  fragment renderings from the suffix map: {}".format(len(frag_map)))

    def one(s):
        ids = tok.encode(s, add_special_tokens=False)
        return ids[0] if len(ids) == 1 else None

    id2, init, mid = {}, {}, {}
    for tgt, src in enc_pairs.items():
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
    n_hand = len(id2)
    for tid, nl_word in dec_extra.items():
        id2.setdefault(tid, " " + nl_word)
    n_dict = len(id2)
    for tid, frag in frag_map.items():          # decode only, never encode
        id2.setdefault(tid, frag)
    print("  decode map: {} hand -> {} +dictionary -> {} +fragments".format(
        n_hand, n_dict, len(id2)))

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
            # FIX 1: single letters are language-neutral, like digits
            real = [int(i) for i in ids
                    if any(c in AL for c in tok.decode([int(i)]))
                    and not is_language_neutral(tok.decode([int(i)]))]
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
    print("{:>3} {:<32}{:>6}{:>5}{:>8}  {:<38}hit".format(
        "#", "prompt (nl)", "cov", "id", "purity", "output"))
    print("-" * 112)
    hits = match = 0
    covs, purs, rows, cache = [], [], [], []
    for p in SEED_PROMPTS:
        src_ids = tok.encode(p["en"], add_special_tokens=False)
        ids = codec.encode(p["nl"])
        cov = dict(codec.cov)
        same = ids == src_ids
        oid = gen(ids)
        cache.append(oid)
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
        print("{:>3} {:<32}{:>6.2f}{:>5}{:>8.2f}  {:<38}{}".format(
            p["id"], p["nl"][:31], cov["coverage"], "Y" if same else ".",
            pur if pur is not None else 0.0, out.strip()[:37],
            "Y" if hit else "."))
    print("-" * 112)

    n = len(SEED_PROMPTS)
    ceiling = sum(p["exp_en"].lower() in tok.decode(
        gen(tok.encode(p["en"], add_special_tokens=False))).lower()
        for p in SEED_PROMPTS) / n
    purity = round(sum(purs) / len(purs), 3) if purs else None
    print("  lexicon ids {}   coverage {:.1%}   ids {}/{}   accuracy {:.0%}"
          "   ceiling {:.0%}".format(len(id2), sum(covs) / n, match, n,
                                     hits / n, ceiling))
    print("  OUTPUT PURITY {}   (0.67 MT, 0.689 v7, 0.701 v8)".format(purity))

    print("")
    print(BAR)
    print("WHAT IS LEFT - recomputed with the metric fixed")
    print(BAR)
    buckets = {"true_fragment": 0, "whole_word_no_entry": 0,
               "whole_word_entry_exists": 0}
    examples = {k: [] for k in buckets}
    total = 0
    for oid in cache:
        for t in oid:
            d = tok.decode([int(t)])
            if not any(c in AL for c in d) or is_language_neutral(d):
                continue
            total += 1
            if int(t) in id2:
                continue
            b = d.lstrip(" ")
            if not d.startswith(" ") or not all(c in AL for c in b):
                k = "true_fragment"
            elif b.lower() in muse:
                k = "whole_word_entry_exists"
            else:
                k = "whole_word_no_entry"
            buckets[k] += 1
            if len(examples[k]) < 12:
                examples[k].append(d)
    bad = sum(buckets.values())
    print("  generated tokens (letters, not single) : {}".format(total))
    print("  rendered in Dutch                     : {}  ({:.1%})".format(
        total - bad, (total - bad) / max(total, 1)))
    print("  NOT rendered                          : {}  ({:.1%})".format(
        bad, bad / max(total, 1)))
    for k in ("true_fragment", "whole_word_no_entry", "whole_word_entry_exists"):
        print("    {:<26}{:>5}  {}".format(k, buckets[k], examples[k][:9]))

    print("")
    print("  TOP REMAINING DICTIONARY GAPS by token id (frequency proxy):")
    print("  {}".format([g[1] for g in gaps[:40]]))

    after = model.state_dict()
    unchanged = all(torch.equal(sig[k], after[k]) for k in sig)
    print("")
    print("  weights unchanged: {}".format(unchanged))

    os.makedirs("/cache/out", exist_ok=True)
    payload = {"model": model_id, "dict_headwords": len(muse),
               "hand_pairs": len(SEED_NL) + len(SUPPLEMENT_NL),
               "vocab_whole_words": words, "matched_by_dict": matched,
               "fragment_renderings": len(frag_map),
               "lexicon_ids": len(id2), "coverage": round(sum(covs) / n, 3),
               "ids_match": match, "accuracy": round(hits / n, 3),
               "ceiling": round(ceiling, 3), "output_purity": purity,
               "buckets": buckets, "examples": examples,
               "generated_tokens": total, "not_rendered": bad,
               "top_gaps": gaps[:600], "weights_unchanged": bool(unchanged),
               "rows": rows}
    with open("/cache/out/v9.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    vol.commit()
    return payload


@app.local_entrypoint()
def main(use_suffix: bool = True):
    run.remote(use_suffix=use_suffix)
