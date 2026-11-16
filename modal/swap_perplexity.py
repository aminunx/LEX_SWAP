"""Measure the thing itself: how intelligible is swapped text to the model?

The word-order survey was a PROXY and it failed its own validity check. Kendall
tau could not separate Dutch from Spanish - 0.801 against 0.821 - when this
project measured Dutch at 26% and English-order text at 64%.

The reason is that tau averages over every word pair, and Dutch's problem is a
handful of positions: the finite verb at the end of a subordinate clause, V2
inversion, a separable prefix. Nouns, adjectives, prepositions and determiners
all sit in English-compatible places, so the average drowns the signal.

A proxy that cannot separate the one case whose answer is known does not get
recalibrated. It gets replaced by the quantity the method actually depends on:

    real target sentence -> word-for-word swap -> English token ids
                         -> how surprised is the model?

If the swapped text reads as ordinary English, the method works. If it reads as
broken English, it does not - which is exactly what the Dutch run showed, with
the lexicon at 99.6% purity in both halves.

No authored prompts, real corpus sentences, and the same anchors:

  en  real English  - the floor. Nothing swapped can beat it.
  tr  Turkish, SOV  - must be the worst.
  nl  Dutch         - must be clearly worse than Spanish. This is the check
                      that the previous metric failed, and the one that decides
                      whether any other row may be read.

Reported as perplexity per token, and as the ratio to real English so the
languages are comparable on one scale.

Run:  modal run modal/swap_perplexity.py
"""

import modal

app = modal.App("swap-perplexity")
vol = modal.Volume.from_name("lexswap", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", "transformers", "datasets", "requests", "numpy")
    .env({"HF_HOME": "/cache/hf"})
)

LANGS = {
    "es": ("Spanish", "Romance", "candidate"),
    "fr": ("French", "Romance", "candidate"),
    "it": ("Italian", "Romance", "candidate"),
    "pt": ("Portuguese", "Romance", "candidate"),
    "ro": ("Romanian", "Romance", "candidate"),
    "id": ("Indonesian", "Austronesian", "candidate"),
    "ms": ("Malay", "Austronesian", "candidate"),
    "vi": ("Vietnamese", "Vietic", "candidate"),
    "nl": ("Dutch", "Germanic", "ANCHOR - must beat Spanish"),
    "af": ("Afrikaans", "Germanic", "candidate"),
    "de": ("German", "Germanic", "candidate"),
    "no": ("Norwegian", "Germanic", "candidate"),
    "sv": ("Swedish", "Germanic", "candidate"),
    "da": ("Danish", "Germanic", "candidate"),
    "pl": ("Polish", "Slavic", "candidate"),
    "bg": ("Bulgarian", "Slavic", "candidate"),
    "ru": ("Russian", "Slavic", "candidate"),
    "tr": ("Turkish", "Turkic", "ANCHOR - must be worst"),
    "fa": ("Persian", "Iranian", "ANCHOR low"),
    "hi": ("Hindi", "Indic", "ANCHOR low"),
}

MUSE = "https://dl.fbaipublicfiles.com/arrival/dictionaries/{}-en.txt"
BAR = "=" * 104


@app.function(image=image, gpu="A10G", volumes={"/cache": vol}, timeout=14400)
def run(model_id: str = "Qwen/Qwen2.5-0.5B", n_sent: int = 400,
        min_cover: float = 0.6):
    import json
    import math
    import os
    import re

    import requests
    import torch
    from datasets import load_dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer

    WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id).to(dev).eval()

    @torch.no_grad()
    def nll(ids):
        """Mean negative log-likelihood per token."""
        if len(ids) < 3:
            return None
        x = torch.tensor([ids], device=dev)
        out = model(input_ids=x, labels=x)
        return float(out.loss)

    def swap_ids(words, d):
        """Word-for-word swap into English token ids. Returns ids, coverage."""
        ids, hit = [], 0
        for k, w in enumerate(words):
            e = d.get(w.lower())
            if e:
                hit += 1
                piece = (e if k == 0 else " " + e)
            else:
                piece = (w if k == 0 else " " + w)
            ids.extend(tok.encode(piece, add_special_tokens=False))
        return ids, hit / max(len(words), 1)

    print(BAR)
    print("SWAP PERPLEXITY - how English does word-for-word swapped text look?")
    print(BAR)
    print("  {:<4}{:<12}{:<14}{:>9}{:>9}{:>9}{:>7}  {}".format(
        "code", "language", "family", "ppl", "x English", "cover%", "n",
        "role"))
    print("-" * 104)

    # ---- the floor: real English, nothing swapped
    en_ds = load_dataset("Helsinki-NLP/opus-100", "en-es", split="test")
    en_losses = []
    for row in en_ds:
        s = row["translation"].get("en")
        if not s:
            continue
        w = WORD.findall(s)
        if not (5 <= len(w) <= 30):
            continue
        v = nll(tok.encode(s, add_special_tokens=False))
        if v is not None:
            en_losses.append(v)
        if len(en_losses) >= n_sent:
            break
    en_ppl = math.exp(sum(en_losses) / len(en_losses))
    print("  {:<4}{:<12}{:<14}{:>9.1f}{:>9.2f}{:>9}{:>7}  {}".format(
        "en", "English", "-", en_ppl, 1.0, "100%", len(en_losses),
        "FLOOR - real English, nothing swapped"))

    results = {}
    for code, (name, family, role) in LANGS.items():
        try:
            r = requests.get(MUSE.format(code), timeout=180)
            if r.status_code != 200:
                print("  {:<4}{:<12}  no dictionary".format(code, name))
                continue
            d = {}
            for line in r.text.splitlines():
                parts = line.strip().split()
                if len(parts) == 2:
                    d.setdefault(parts[0].lower(), parts[1].lower())
        except Exception:
            print("  {:<4}{:<12}  dictionary failed".format(code, name))
            continue
        if len(d) < 500:
            print("  {:<4}{:<12}  dictionary too small".format(code, name))
            continue
        try:
            ds = load_dataset("Helsinki-NLP/opus-100", "en-" + code,
                              split="test")
        except Exception:
            try:
                ds = load_dataset("Helsinki-NLP/opus-100", code + "-en",
                                  split="test")
            except Exception:
                print("  {:<4}{:<12}  no corpus".format(code, name))
                continue

        losses, covs = [], []
        for row in ds:
            s = row["translation"].get(code)
            if not s:
                continue
            w = WORD.findall(s)
            if not (5 <= len(w) <= 30):
                continue
            ids, cov = swap_ids(w, d)
            # a sentence mostly left untranslated measures the lexicon, not
            # the word order, so it is excluded rather than averaged in
            if cov < min_cover:
                continue
            v = nll(ids)
            if v is None:
                continue
            losses.append(v)
            covs.append(cov)
            if len(losses) >= n_sent:
                break
        if len(losses) < 30:
            print("  {:<4}{:<12}{:<14}  only {} usable sentences".format(
                code, name, family, len(losses)))
            continue
        ppl = math.exp(sum(losses) / len(losses))
        cv = sum(covs) / len(covs)
        results[code] = {"name": name, "family": family, "role": role,
                         "ppl": round(ppl, 2),
                         "ratio": round(ppl / en_ppl, 3),
                         "coverage": round(cv, 3), "n": len(losses),
                         "dict_size": len(d)}
        print("  {:<4}{:<12}{:<14}{:>9.1f}{:>9.2f}{:>9.0%}{:>7}  {}".format(
            code, name, family, ppl, ppl / en_ppl, cv, len(losses), role))

    # --------------------------------------------------------- anchor check
    print("")
    print(BAR)
    print("ANCHOR CHECK")
    print(BAR)
    es = results.get("es", {}).get("ppl")
    ok = True
    nl = results.get("nl", {}).get("ppl")
    if nl and es:
        good = nl > es * 1.05
        ok &= good
        print("  Dutch {:.1f} clearly worse than Spanish {:.1f}: {}".format(
            nl, es, "YES" if good else
            "NO - the metric still cannot separate the one case we know"))
    worst = max(results.items(), key=lambda kv: kv[1]["ppl"])[0] if results else None
    if worst:
        good = worst in ("tr", "fa", "hi")
        ok &= good
        print("  worst language is an SOV anchor ({}): {}".format(
            results[worst]["name"], "YES" if good else "NO"))
    print("  -> {}".format(
        "anchors hold; the ranking below is readable" if ok else
        "ANCHORS FAILED - do not read the ranking as a result"))

    print("")
    print(BAR)
    print("RANKED - lower is more English-like after the swap")
    print(BAR)
    for code, v in sorted(results.items(), key=lambda kv: kv[1]["ppl"]):
        print("  {:>8.1f}  {:>5.2f}x  {:<12}{:<14}{}".format(
            v["ppl"], v["ratio"], v["name"], v["family"], v["role"]))

    os.makedirs("/cache/out", exist_ok=True)
    with open("/cache/out/swap_perplexity.json", "w", encoding="utf-8") as f:
        json.dump({"model": model_id, "english_ppl": round(en_ppl, 2),
                   "anchors_ok": bool(ok), "results": results},
                  f, ensure_ascii=False, indent=2)
    vol.commit()
    return results


@app.local_entrypoint()
def main(n_sent: int = 400):
    run.remote(n_sent=n_sent)
