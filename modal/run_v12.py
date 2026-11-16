"""LEX_SWAP v10 — two fixes traced to v9's residual, and the lexicon exported.

v9 reached output purity 0.943 with 7 un-rendered tokens out of 158:

    true_fragment        4  ['innamon', 'fl', 'key', 'oul']
    whole_word_no_entry  3  [' It', ' riding', ' It']

FIX 1 - ` It` was a collision inside my own supplement.
  SEED_NL holds `het -> the`. SUPPLEMENT_NL added `het -> it`, which
  `setdefault` silently dropped, so ` It` had no rendering. Dutch `het` really
  does carry both senses.
  Same lesson as the dictionary collisions: a collision constrains INPUT only.
  On output `id(" it")` can render as `" het"` while `id(" the")` also renders
  as `" het"`, with no conflict. So DEC_ONLY entries are mapped in the decode
  direction alone.

FIX 2 - ` riding` ends in a suffix the map knows, but it entered the whole-word
  branch and the suffix map was only applied to fragments.
  Added: for a space-prefixed word with no dictionary entry, strip a known
  suffix, translate the STEM, re-attach the Dutch suffix. `riding` -> `rid`,
  `ride` -> `rijden` -> `rijdend`. Real morphology rather than a fallback.

NOT FIXED, deliberately. `key` in `monkey` is a continuation piece that happens
to be spelled like a word. MUSE has key -> sleutel, and rendering it inside
`monkey` would be WRONG. A token with no leading space is a piece, not a word,
whatever its shape - so leaving these is correct, not a shortfall.

This run also EXPORTS the finished lexicon to the volume so the translated
model is a usable artefact and not only a measurement.

Run:  modal run modal/run_v12.py
"""

import modal

app = modal.App("lexswap-v12")
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
    from src.lexswap.supplement_nl import (SUFFIX_NL, SUPPLEMENT_NL,
                                           is_language_neutral)
    from src.lexswap.supplement2_nl import DEC_ONLY, ENC_DEC
    from src.lexswap.grammar_nl import (HET_NOUNS, LEMMA_FIX,
                                        apply_article_agreement)
    from src.lexswap.reassemble import render as render_words

    torch.manual_seed(seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    AL = set(string.ascii_letters)

    muse = {}
    for url in MUSE_URLS:
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    p = line.strip().split()
                    if len(p) == 2:
                        muse.setdefault(p[0].lower(), p[1])
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

    enc_pairs = dict(SEED_NL)
    for src_map in (LEMMA_FIX, SUPPLEMENT_NL, ENC_DEC):
        for k, v in src_map.items():
            enc_pairs.setdefault(k, v)
    print("  hand-made: {} seed + {} lemma-fix + {} supp + {} supp2 = {} pairs"
          .format(len(SEED_NL), len(LEMMA_FIX), len(SUPPLEMENT_NL),
                  len(ENC_DEC), len(enc_pairs)))
    print("  neuter nouns for article agreement: {}".format(len(HET_NOUNS)))

    def one(s):
        ids = tok.encode(s, add_special_tokens=False)
        return ids[0] if len(ids) == 1 else None

    # ------------------------------------------- walk the whole vocabulary
    dec_extra, frag_map, stem_map = {}, {}, {}
    gaps = []
    words = matched = no_entry = multiword = stemmed = 0
    SUF = sorted(SUFFIX_NL, key=len, reverse=True)
    for i in range(V):
        s = tok.decode([i])
        b = s.lstrip(" ")
        if not b or not all(c in AL for c in b):
            continue
        if s.startswith(" ") and len(b) > 1:
            words += 1
            hit = muse.get(b.lower())
            if hit is not None and " " not in hit and all(c in AL for c in hit):
                enc_pairs.setdefault(hit, b)
                dec_extra[i] = hit
                matched += 1
                continue
            if hit is not None:
                multiword += 1
                continue
            # FIX 2: no entry - strip a known suffix, translate the stem
            done = False
            for suf in SUF:
                if len(b) > len(suf) + 2 and b.lower().endswith(suf):
                    stem = b[: len(b) - len(suf)]
                    for cand in (stem.lower(), stem.lower() + "e"):
                        st = muse.get(cand)
                        if st and " " not in st and all(c in AL for c in st):
                            stem_map[i] = st + SUFFIX_NL[suf]
                            stemmed += 1
                            done = True
                            break
                if done:
                    break
            if not done:
                no_entry += 1
                if len(gaps) < 600:
                    gaps.append([i, b])
        elif len(b) > 1:
            for suf in SUF:
                if b.lower().endswith(suf):
                    frag_map[i] = b[: len(b) - len(suf)] + SUFFIX_NL[suf]
                    break

    print("  vocab whole words {}   dict-matched {} ({:.1%})   stem+suffix {}"
          "   no entry {}   multiword {}".format(
              words, matched, matched / max(words, 1), stemmed, no_entry,
              multiword))

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
    n1 = len(id2)

    # FIX 1: decode-direction-only entries, where the Dutch form is taken
    for en_word, nl_word in DEC_ONLY.items():
        for form, out in ((" " + en_word, " " + nl_word),
                          (" " + en_word.capitalize(), " " + nl_word.capitalize()),
                          (en_word.capitalize(), nl_word.capitalize())):
            t = one(form)
            if t is not None:
                id2[t] = out
    n2 = len(id2)
    for tid, nl_word in dec_extra.items():
        id2.setdefault(tid, " " + nl_word)
    n3 = len(id2)
    for tid, w in stem_map.items():
        id2.setdefault(tid, " " + w)
    n4 = len(id2)
    for tid, f in frag_map.items():
        id2.setdefault(tid, f)
    print("  decode map: {} hand -> {} +dec_only -> {} +dict -> {} +stems"
          " -> {} +fragments".format(n1, n2, n3, n4, len(id2)))

    en2nl = {v.lower(): k for k, v in enc_pairs.items()}

    def word_lookup(w):
        """Source word -> target word. Hand-made first, then the dictionary."""
        hit = en2nl.get(w)
        if hit:
            return hit
        hit = muse.get(w)
        if hit and " " not in hit and all(c in AL for c in hit):
            return hit
        return None

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
            parts = render_words(ids, lambda t: tok.decode([t]), id2, word_lookup)
            return "".join(apply_article_agreement(parts))

        def rendered_mask(self, ids):
            """Which tokens ended up rendered, counting reassembled words.

            A multi-token word translated as a whole leaves every one of its
            tokens rendered, so purity must be computed from the grouping and
            not from `id in id2`.
            """
            from src.lexswap.reassemble import group_words
            pieces = [(int(i), tok.decode([int(i)])) for i in ids]
            done = {}
            for grp in group_words(pieces):
                if len(grp) > 1:
                    w = "".join(t for _, t in grp).lstrip(" ")
                    ok = bool(w.isalpha() and word_lookup(w.lower()))
                    for tid, _ in grp:
                        done[tid] = ok or tid in id2
                else:
                    tid = grp[0][0]
                    done[tid] = tid in id2
            return done

        def purity(self, ids):
            mask = self.rendered_mask(ids)
            real = [int(i) for i in ids
                    if any(c in AL for c in tok.decode([int(i)]))
                    and not is_language_neutral(tok.decode([int(i)]))]
            if not real:
                return None
            return round(sum(mask.get(i, False) for i in real) / len(real), 3)

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
    print("  OUTPUT PURITY {}   (0.67 MT, 0.701 v8, 0.943 v9, 0.956 v10-v11)".format(purity))

    print("")
    print(BAR)
    print("WHAT IS LEFT")
    print(BAR)
    buckets = {"continuation_piece": 0, "whole_word_no_entry": 0,
               "whole_word_entry_exists": 0}
    examples = {k: [] for k in buckets}
    total = 0
    for oid in cache:
        mask = codec.rendered_mask(oid)
        for t in oid:
            d = tok.decode([int(t)])
            if not any(c in AL for c in d) or is_language_neutral(d):
                continue
            total += 1
            if mask.get(int(t), False):
                continue
            b = d.lstrip(" ")
            if not d.startswith(" ") or not all(c in AL for c in b):
                k = "continuation_piece"
            elif b.lower() in muse:
                k = "whole_word_entry_exists"
            else:
                k = "whole_word_no_entry"
            buckets[k] += 1
            if len(examples[k]) < 12:
                examples[k].append(d)
    bad = sum(buckets.values())
    print("  generated tokens  {}   rendered {} ({:.1%})   not rendered {}"
          " ({:.1%})".format(total, total - bad, (total - bad) / max(total, 1),
                             bad, bad / max(total, 1)))
    for k in buckets:
        print("    {:<26}{:>4}  {}".format(k, buckets[k], examples[k][:8]))
    print("  continuation_piece is CORRECT to leave: a token with no leading")
    print("  space is a piece, not a word. `key` inside `monkey` must not")
    print("  become `sleutel`.")
    print("")
    print("  remaining gaps by frequency: {}".format([g[1] for g in gaps[:30]]))

    after = model.state_dict()
    unchanged = all(torch.equal(sig[k], after[k]) for k in sig)
    print("")
    print("  weights unchanged: {}".format(unchanged))

    # ------------------------------------------------- export the artefact
    os.makedirs("/cache/out", exist_ok=True)
    with open("/cache/out/lexicon_nl.json", "w", encoding="utf-8") as f:
        json.dump({"model": model_id, "vocab_size": V,
                   "decode": {str(k): v for k, v in id2.items()},
                   "encode_mid": mid, "encode_initial": init},
                  f, ensure_ascii=False)
    print("  exported /out/lexicon_nl.json  ({} decode entries)".format(len(id2)))

    payload = {"model": model_id, "dict_headwords": len(muse),
               "lexicon_ids": len(id2), "vocab_whole_words": words,
               "dict_matched": matched, "stem_suffix": stemmed,
               "no_entry": no_entry, "coverage": round(sum(covs) / n, 3),
               "ids_match": match, "accuracy": round(hits / n, 3),
               "ceiling": round(ceiling, 3), "output_purity": purity,
               "buckets": buckets, "examples": examples,
               "generated_tokens": total, "not_rendered": bad,
               "weights_unchanged": bool(unchanged), "rows": rows,
               "top_gaps": gaps[:600]}
    with open("/cache/out/v12.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    vol.commit()
    return payload


@app.local_entrypoint()
def main():
    run.remote()
