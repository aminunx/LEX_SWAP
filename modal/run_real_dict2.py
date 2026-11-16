"""LEX_SWAP v7 — a REAL dictionary, every token, in batches.

Correction from the project owner: the goal was never to grow the NUMBER of
lexicon entries. It is to translate **every token with a real dictionary into
its actual Dutch word**, fixing in batches until the whole vocabulary is done.

That is a different target, and the previous runs were measuring the wrong
thing. They reported how many tokens were *attempted* (N = 300 … 60,000) while
the quality of each mapping came from `opus-mt` fed a bare context-free word -
which returns whichever sense is most frequent and collapses many English words
onto one Dutch word. Measured cost of that: 9,368 of 30,000 ids lost to
collisions, and output purity saturating at 67% while the lexicon grew 2.5x for
one single point.

So the lexicon source changes from machine translation to **MUSE bilingual
dictionaries** - real word-pair lists, the standard resource in cross-lingual
work.

HARD RULE: if the dictionary cannot be fetched, this run STOPS and says so. It
does not fall back to machine translation silently. A silent fallback would
reproduce exactly the failure this run exists to remove, while appearing to
have fixed it.

The hand-made seed stays as an override: hand-verified beats dictionary.

Batching, as directed: the vocabulary is processed in slices, each slice
reporting matched / unmatched and the reason for every gap, so the lexicon is
built up with its failures visible rather than as one opaque number.

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

# MUSE en-nl, in order of preference. The full file first, then the train/test
# splits which together cover the same ground.
MUSE_URLS = [
    "https://dl.fbaipublicfiles.com/arrival/dictionaries/en-nl.txt",
    "https://dl.fbaipublicfiles.com/arrival/dictionaries/en-nl.0-5000.txt",
    "https://dl.fbaipublicfiles.com/arrival/dictionaries/en-nl.5000-6500.txt",
]

BATCH = 10_000


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

    # ------------------------------------------------- the real dictionary
    print("=" * 112)
    print("STEP 1 - fetch a REAL bilingual dictionary (no machine translation)")
    print("=" * 112)
    pairs_raw, sources = {}, []
    for url in MUSE_URLS:
        try:
            r = requests.get(url, timeout=120)
            if r.status_code != 200:
                print(f"  {url.split('/')[-1]:<26} HTTP {r.status_code}")
                continue
            n_before = len(pairs_raw)
            for line in r.text.splitlines():
                parts = line.strip().split()
                if len(parts) != 2:
                    continue
                en, nl = parts[0].lower(), parts[1]
                # first translation wins: MUSE lists them best-first
                pairs_raw.setdefault(en, nl)
            got = len(pairs_raw) - n_before
            sources.append({"url": url, "new_pairs": got})
            print(f"  {url.split('/')[-1]:<26} +{got} pairs")
        except Exception as e:
            print(f"  {url.split('/')[-1]:<26} FAILED: {type(e).__name__}")

    print(f"\n  real dictionary: {len(pairs_raw)} English headwords")
    if len(pairs_raw) < 1000:
        print("\n  *** STOPPING. The real dictionary could not be fetched.")
        print("  *** This run does NOT fall back to machine translation: that")
        print("  *** would reproduce the exact failure it exists to remove,")
        print("  *** while appearing to have fixed it.")
        return {"stopped": "dictionary_unavailable", "sources": sources,
                "headwords": len(pairs_raw)}

    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id).to(dev).eval()
    sig = {k: v.detach().clone() for k, v in list(model.state_dict().items())[:3]}

    # ------------------------------------------- STEP 2: batch over the vocab
    print("\n" + "=" * 112)
    print(f"STEP 2 - walk the whole vocabulary in batches of {BATCH}")
    print("=" * 112)
    print(f"{'batch':>14}{'words':>9}{'matched':>9}{'no entry':>10}"
          f"{'multiword':>11}{'cumulative':>12}")

    # Two maps, because a collision constrains INPUT only.
    #   enc_pairs : dutch -> english, first wins. `groot` must pick one id.
    #   dec_pairs : id -> dutch, EVERY match kept. Several ids may all render
    #               as `groot` with no conflict at all.
    # v7 keyed both on the Dutch word and so threw away 10,754 renderings for
    # no reason, which is most of why output purity moved only two points.
    pairs, gaps = dict(SEED_NL), {"no_entry": [], "multiword": []}
    dec_extra = {}          # token id -> dutch word
    V = len(tok)
    batch_log = []
    for start in range(0, V, BATCH):
        words = 0
        matched = no_entry = multiword = 0
        for i in range(start, min(start + BATCH, V)):
            s = tok.decode([i])
            b = s.lstrip(" ")
            if not (s.startswith(" ") and len(b) > 1 and all(c in AL for c in b)):
                continue
            words += 1
            hit = pairs_raw.get(b.lower())
            if hit is None:
                no_entry += 1
                if len(gaps["no_entry"]) < 400:
                    gaps["no_entry"].append(b)
                continue
            if " " in hit or not all(c in AL for c in hit):
                multiword += 1
                if len(gaps["multiword"]) < 200:
                    gaps["multiword"].append((b, hit))
                continue
            pairs.setdefault(hit, b)      # input side: first wins
            dec_extra[i] = hit            # output side: keep every one
            matched += 1
        batch_log.append({"start": start, "words": words, "matched": matched,
                          "no_entry": no_entry, "multiword": multiword,
                          "cumulative_pairs": len(pairs)})
        if words:
            print(f"{start:>8}-{min(start+BATCH, V):<5}{words:>9}{matched:>9}"
                  f"{no_entry:>10}{multiword:>11}{len(pairs):>12}")

    tw = sum(b["words"] for b in batch_log)
    tm = sum(b["matched"] for b in batch_log)
    print(f"\n  whole-word tokens in vocabulary : {tw}")
    print(f"  translated by the real dictionary: {tm}  ({tm/max(tw,1):.1%})")
    print(f"  no dictionary entry              : "
          f"{sum(b['no_entry'] for b in batch_log)}")
    print(f"  entry was multi-word             : "
          f"{sum(b['multiword'] for b in batch_log)}")
    print(f"  final Dutch->English pairs       : {len(pairs)}")
    print(f"\n  sample of words with NO entry: {gaps['no_entry'][:18]}")
    print(f"  sample of multi-word entries : {gaps['multiword'][:8]}")

    # --------------------------------------------------------- tables + codec
    def one(s):
        ids = tok.encode(s, add_special_tokens=False)
        return ids[0] if len(ids) == 1 else None

    def tables(p):
        id2, init, mid = {}, {}, {}
        for tgt, src in p.items():
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

    class Codec:
        def __init__(self, id2, init, mid):
            self.id2, self.init, self.mid = id2, init, mid
            self.cov = {}

        def encode(self, text):
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
                    ids.append(got); hit += 1
                else:
                    ids.extend(tok.encode(w if k == 0 else " " + w,
                                          add_special_tokens=False))
                    miss += 1; missed.append(w)
            n = hit + miss
            self.cov = {"coverage": round(hit / n, 3) if n else 0.0,
                        "missed": missed}
            return ids

        def decode(self, ids):
            return "".join(self.id2.get(int(i), tok.decode([int(i)]))
                           for i in ids)

        def purity(self, ids):
            real = [int(i) for i in ids
                    if any(c in AL for c in tok.decode([int(i)]))]
            return (round(sum(int(i) in self.id2 for i in real) / len(real), 3)
                    if real else None)

    @torch.no_grad()
    def gen(ids):
        x = torch.tensor([ids], device=dev)
        o = model.generate(x, max_new_tokens=max_new, do_sample=False,
                           pad_token_id=tok.eos_token_id)
        return o[0, len(ids):].tolist()

    def evaluate(codec, verbose=False):
        hits = match = 0
        covs, purs, rows = [], [], []
        for p in SEED_PROMPTS:
            src_ids = tok.encode(p["en"], add_special_tokens=False)
            ids = codec.encode(p["nl"])
            cov = dict(codec.cov)
            same = ids == src_ids
            oid = gen(ids)
            out = codec.decode(oid)
            pur = codec.purity(oid)
            hit = p["exp_nl"].lower() in out.lower()
            hits += hit; match += same
            covs.append(cov["coverage"])
            if pur is not None:
                purs.append(pur)
            rows.append({"id": p["id"], "nl": p["nl"], "out": out.strip(),
                         "expected": p["exp_nl"], "hit": bool(hit),
                         "ids_match": bool(same), "purity": pur,
                         "coverage": cov["coverage"], "missed": cov["missed"]})
            if verbose:
                print(f"{p['id']:>3} {p['nl'][:32]:<33}{cov['coverage']:>6.2f}"
                      f"{('Y' if same else '.'):>5}"
                      f"{(pur if pur is not None else 0):>8.2f}  "
                      f"{out.strip()[:36]:<37}{'Y' if hit else '.'}")
        n = len(SEED_PROMPTS)
        return {"coverage": round(sum(covs) / n, 3), "ids_match": match,
                "accuracy": round(hits / n, 3), "rows": rows,
                "output_purity": round(sum(purs) / len(purs), 3) if purs else None}

    print("\n" + "=" * 112)
    print("STEP 3 - evaluate with the real-dictionary lexicon")
    print("=" * 112)
    print(f"{'#':>3} {'prompt (nl)':<33}{'cov':>6}{'id':>5}{'purity':>8}  "
          f"{'output':<37}hit")
    print("-" * 112)
    i2, ini, mi = tables(pairs)
    before = len(i2)
    for tid, nl_word in dec_extra.items():          # the recovered renderings
        i2.setdefault(tid, " " + nl_word)
    print(f"  decode map: {before} -> {len(i2)} ids "
          f"(+{len(i2)-before} recovered from collisions)")
    res = evaluate(Codec(i2, ini, mi), verbose=True)
    print("-" * 112)
    ceiling = sum(p["exp_en"].lower() in tok.decode(
        gen(tok.encode(p["en"], add_special_tokens=False))).lower()
        for p in SEED_PROMPTS) / len(SEED_PROMPTS)

    print(f"\n  lexicon ids          {len(i2)}")
    print(f"  input coverage       {res['coverage']:.1%}")
    print(f"  ids identical        {res['ids_match']}/{len(SEED_PROMPTS)}")
    print(f"  accuracy             {res['accuracy']:.0%}")
    print(f"  ceiling (source)     {ceiling:.0%}")
    print(f"  OUTPUT PURITY        {res['output_purity']}"
          f"   <- the number that was stuck at 0.67 with machine translation")

    # ------------------------------------------------------------ DIAGNOSTIC
    # "How much is left?" answered by decomposition rather than estimate.
    # Every generated token the lexicon cannot render is put in one of three
    # buckets, and only one of them is reachable by more dictionary work.
    print("
" + "=" * 112)
    print("WHAT IS LEFT - decomposing every un-renderable generated token")
    print("=" * 112)
    buckets = {"subword_fragment": 0, "whole_word_no_entry": 0,
               "whole_word_entry_exists": 0, "other": 0}
    examples = {k: [] for k in buckets}
    total_real = 0
    for p in SEED_PROMPTS:
        for t in gen(Codec(i2, ini, mi).encode(p["nl"])):
            d = tok.decode([int(t)])
            if not any(c in AL for c in d):
                continue
            total_real += 1
            if int(t) in i2:
                continue
            b = d.lstrip(" ")
            if not d.startswith(" ") or not all(c in AL for c in b):
                k = "subword_fragment"
            elif b.lower() in pairs_raw:
                k = "whole_word_entry_exists"
            else:
                k = "whole_word_no_entry"
            buckets[k] += 1
            if len(examples[k]) < 14:
                examples[k].append(d)
    bad = sum(buckets.values())
    print(f"  generated word-like tokens : {total_real}")
    print(f"  rendered in Dutch          : {total_real - bad} "
          f"({(total_real-bad)/max(total_real,1):.1%})")
    print(f"  NOT rendered               : {bad} "
          f"({bad/max(total_real,1):.1%})
")
    for k in ("subword_fragment", "whole_word_no_entry",
              "whole_word_entry_exists", "other"):
        if buckets[k]:
            print(f"    {k:<26}{buckets[k]:>5} "
                  f"({buckets[k]/max(bad,1):.0%} of the gap)  {examples[k][:10]}")
    print("
  Only `whole_word_no_entry` is reachable by a bigger dictionary.")
    print("  `subword_fragment` is NOT: a BPE piece has no word-level")
    print("  translation, so it is a hard ceiling on this method.")

    after = model.state_dict()
    unchanged = all(torch.equal(sig[k], after[k]) for k in sig)
    print(f"  weights unchanged    {unchanged}")

    os.makedirs("/cache/out", exist_ok=True)
    payload = {"model": model_id, "dictionary": "MUSE en-nl",
               "dict_sources": sources, "dict_headwords": len(pairs_raw),
               "vocab_whole_words": tw, "translated_by_dict": tm,
               "final_pairs": len(pairs), "lexicon_ids": len(i2),
               "batches": batch_log, "ceiling": round(ceiling, 3),
               "weights_unchanged": bool(unchanged),
               "result": {k: res[k] for k in
                          ("coverage", "ids_match", "accuracy", "output_purity")},
               "rows": res["rows"],
               "impurity_buckets": buckets, "impurity_examples": examples,
               "generated_wordlike": total_real, "not_rendered": bad,
               "gaps_sample": {"no_entry": gaps["no_entry"][:400],
                               "multiword": gaps["multiword"][:200]}}
    with open("/cache/out/realdict2.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    vol.commit()
    return payload


@app.local_entrypoint()
def main():
    run.remote()
