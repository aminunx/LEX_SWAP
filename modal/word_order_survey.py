"""Which languages actually match English word order? Measured, not asserted.

The Dutch result split cleanly: 64% on prompts whose order parallels English
against 26% on naturally written Dutch, with the lexicon at 99.6% purity in
both. So the method's ceiling is set by word order, and the next question is
which languages have English's.

That question gets answered by measurement here rather than from memory. For
each candidate language:

  1. take real parallel sentences from `Helsinki-NLP/opus-100`
  2. map every source word to English through a real MUSE dictionary
  3. compare the ORDER of the result against the actual English sentence

The metric is Kendall tau over the words that appear in both: +1 means
word-for-word substitution already produces English order, 0 means the orders
are unrelated, negative means reversed.

ANCHORS, so the scale means something. Every claimed limit in this project that
turned out to be a measurement artefact was caught by a condition whose value
was known in advance, so:

  nl  Dutch      - the known baseline. It must land low; we measured it failing.
  tr  Turkish    - SOV, verb last. Must land lowest.
  fa  Persian    - SOV. Must land low.
  hi  Hindi      - SOV. Must land low.

If Turkish does not come out below Spanish, the instrument is broken and no
reading of the other rows is admissible.

EXCLUDED: zh, ja, th, ko - not space-separated, so word-level mapping needs a
segmenter first. That is a different problem and pretending otherwise would put
a meaningless number next to the real ones.

Run:  modal run modal/word_order_survey.py
"""

import modal

app = modal.App("word-order-survey")
vol = modal.Volume.from_name("lexswap", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("datasets", "requests", "numpy", "pyarrow")
    .env({"HF_HOME": "/cache/hf"})
)

# code -> (name, family, expected position)
LANGS = {
    # Romance
    "es": ("Spanish", "Romance", "candidate"),
    "fr": ("French", "Romance", "candidate"),
    "it": ("Italian", "Romance", "candidate"),
    "pt": ("Portuguese", "Romance", "candidate"),
    "ro": ("Romanian", "Romance", "candidate"),
    # Austronesian
    "id": ("Indonesian", "Austronesian", "candidate"),
    "ms": ("Malay", "Austronesian", "candidate"),
    # Vietic, analytic and space-separated
    "vi": ("Vietnamese", "Vietic", "candidate"),
    # Germanic - Dutch is the known-failing anchor
    "nl": ("Dutch", "Germanic", "ANCHOR low"),
    "af": ("Afrikaans", "Germanic", "candidate"),
    "de": ("German", "Germanic", "candidate"),
    "no": ("Norwegian", "Germanic", "candidate"),
    "sv": ("Swedish", "Germanic", "candidate"),
    "da": ("Danish", "Germanic", "candidate"),
    # Slavic
    "ru": ("Russian", "Slavic", "candidate"),
    "pl": ("Polish", "Slavic", "candidate"),
    "bg": ("Bulgarian", "Slavic", "candidate"),
    # SOV negative controls - these MUST land lowest
    "tr": ("Turkish", "Turkic", "ANCHOR lowest"),
    "fa": ("Persian", "Iranian", "ANCHOR low"),
    "hi": ("Hindi", "Indic", "ANCHOR low"),
}

MUSE = "https://dl.fbaipublicfiles.com/arrival/dictionaries/{}-en.txt"
BAR = "=" * 104


@app.function(image=image, volumes={"/cache": vol}, timeout=10800,
              cpu=4.0, memory=8192)
def run(n_sent: int = 600, min_overlap: int = 4):
    import json
    import os
    import re

    import requests
    from datasets import load_dataset

    WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

    def kendall_tau(order):
        """Concordant minus discordant pairs, normalised. +1 = same order."""
        n = len(order)
        if n < 2:
            return None
        con = dis = 0
        for i in range(n):
            for j in range(i + 1, n):
                if order[i] == order[j]:
                    continue
                if order[i] < order[j]:
                    con += 1
                else:
                    dis += 1
        tot = con + dis
        return None if tot == 0 else (con - dis) / tot

    print(BAR)
    print("WORD-ORDER SURVEY - does word-for-word substitution give English order?")
    print(BAR)
    print("  {} sentences per language, Kendall tau over shared words".format(n_sent))
    print("  anchors: Dutch must be low, Turkish lowest. If not, the metric is")
    print("  broken and no other row may be read.")
    print("")
    print("  {:<4}{:<12}{:<14}{:>8}{:>9}{:>9}{:>8}  {}".format(
        "code", "language", "family", "tau", "exact%", "cover%", "n", "role"))
    print("-" * 104)

    results = {}
    for code, (name, family, role) in LANGS.items():
        # ---- dictionary
        try:
            r = requests.get(MUSE.format(code), timeout=180)
            if r.status_code != 200:
                print("  {:<4}{:<12}{:<14}  no MUSE dictionary (HTTP {})".format(
                    code, name, family, r.status_code))
                continue
            d = {}
            for line in r.text.splitlines():
                parts = line.strip().split()
                if len(parts) == 2:
                    d.setdefault(parts[0].lower(), parts[1].lower())
        except Exception as e:
            print("  {:<4}{:<12}{:<14}  dictionary failed: {}".format(
                code, name, family, type(e).__name__))
            continue
        if len(d) < 500:
            print("  {:<4}{:<12}{:<14}  dictionary too small ({})".format(
                code, name, family, len(d)))
            continue

        # ---- parallel sentences
        try:
            ds = load_dataset("Helsinki-NLP/opus-100", "en-" + code,
                              split="test")
        except Exception:
            try:
                ds = load_dataset("Helsinki-NLP/opus-100", code + "-en",
                                  split="test")
            except Exception as e:
                print("  {:<4}{:<12}{:<14}  no corpus: {}".format(
                    code, name, family, type(e).__name__))
                continue

        taus, exact, used, covs = [], 0, 0, []
        for row in ds:
            tr = row["translation"]
            en_s, sr_s = tr.get("en"), tr.get(code)
            if not en_s or not sr_s:
                continue
            en_w = [w.lower() for w in WORD.findall(en_s)]
            sr_w = [w.lower() for w in WORD.findall(sr_s)]
            if not (4 <= len(en_w) <= 25) or not (4 <= len(sr_w) <= 25):
                continue
            mapped = [(d.get(w), i) for i, w in enumerate(sr_w)]
            hit = [(m, i) for m, i in mapped if m]
            covs.append(len(hit) / max(len(sr_w), 1))
            # position of each mapped word in the real English sentence
            pos, seen = [], set()
            for m, _ in hit:
                for j, e in enumerate(en_w):
                    if e == m and j not in seen:
                        pos.append(j)
                        seen.add(j)
                        break
            if len(pos) < min_overlap:
                continue
            t = kendall_tau(pos)
            if t is None:
                continue
            taus.append(t)
            if pos == sorted(pos):
                exact += 1
            used += 1
            if used >= n_sent:
                break

        if not taus:
            print("  {:<4}{:<12}{:<14}  too few usable sentences".format(
                code, name, family))
            continue
        tau = sum(taus) / len(taus)
        ex = exact / used
        cv = sum(covs) / len(covs)
        results[code] = {"name": name, "family": family, "role": role,
                         "tau": round(tau, 3), "exact": round(ex, 3),
                         "coverage": round(cv, 3), "n": used,
                         "dict_size": len(d)}
        print("  {:<4}{:<12}{:<14}{:>8.3f}{:>9.0%}{:>9.0%}{:>8}  {}".format(
            code, name, family, tau, ex, cv, used, role))

    # -------------------------------------------------- validity of the scale
    print("")
    print(BAR)
    print("ANCHOR CHECK - is the instrument reading correctly?")
    print(BAR)
    tr_t = results.get("tr", {}).get("tau")
    nl_t = results.get("nl", {}).get("tau")
    es_t = results.get("es", {}).get("tau")
    ok = True
    if tr_t is not None and es_t is not None:
        good = tr_t < es_t
        ok &= good
        print("  Turkish ({:.3f}) below Spanish ({:.3f}): {}".format(
            tr_t, es_t, "YES" if good else "NO - metric is broken"))
    if nl_t is not None and es_t is not None:
        good = nl_t < es_t
        print("  Dutch ({:.3f}) below Spanish ({:.3f}): {}".format(
            nl_t, es_t, "YES" if good else "NO"))
    print("  -> {}".format("scale is usable" if ok else
                           "DO NOT read the other rows"))

    print("")
    print(BAR)
    print("RANKED BY ORDER COMPATIBILITY WITH ENGLISH")
    print(BAR)
    for code, v in sorted(results.items(), key=lambda kv: -kv[1]["tau"]):
        print("  {:>7.3f}  {:<12}{:<14}{}".format(
            v["tau"], v["name"], v["family"], v["role"]))
    print("")
    print("  tau is the rank correlation between word-for-word order and real")
    print("  English order. Higher means the swap already produces English")
    print("  order, which is exactly the condition the Dutch result showed to")
    print("  be decisive: 64% when it holds, 26% when it does not.")

    os.makedirs("/cache/out", exist_ok=True)
    with open("/cache/out/word_order_survey.json", "w", encoding="utf-8") as f:
        json.dump({"n_sent": n_sent, "anchors_ok": bool(ok),
                   "results": results}, f, ensure_ascii=False, indent=2)
    vol.commit()
    return results


@app.local_entrypoint()
def main(n_sent: int = 600):
    run.remote(n_sent=n_sent)
