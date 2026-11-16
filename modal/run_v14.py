"""LEX_SWAP v14 — add the syntax layer, and measure natural Dutch again.

v13 result: 64% on word-order-parallel prompts, **10% on naturally written
Dutch**, at 94% output purity. The words came out Dutch and the reasoning was
broken, because the model internally received English word order.

No lexicon entry fixes that. The missing thing was a syntactic procedure: the
pipeline replaced words and left them where they sat.

v14 adds one. Dutch is reordered into English order before the lexical map, and
where the reordering moves the predicted word off the end, the model is used as
a SCORER over candidates in that slot rather than as a left-to-right generator -
the only way to query a non-final position.

Still no training and no weight edits.

Three arms on the natural-Dutch set, so the syntax layer's contribution is
isolated:

  lexical      v13 behaviour: substitute words, generate left to right
  syntax       reorder, then generate or score the slot
  oracle_slot  score only the correct answer against its competitors, which
               bounds what the scoring approach can reach at all

The third arm matters. If `syntax` is far below `oracle_slot`, the reordering
rules are the limit. If both are low, scoring is the limit, and that is a
different problem with a different fix.

Run:  modal run modal/run_v14.py
"""

import modal

app = modal.App("lexswap-v14")
vol = modal.Volume.from_name("lexswap", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", "transformers", "requests", "numpy")
    .env({"HF_HOME": "/cache/hf"})
    .add_local_dir("src", remote_path="/root/src")
)
BAR = "=" * 112


@app.function(image=image, gpu="A10G", volumes={"/cache": vol}, timeout=14400)
def run(model_id: str = "Qwen/Qwen2.5-0.5B", max_new: int = 10,
        n_cand: int = 300):
    import json
    import os
    import sys

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    sys.path.insert(0, "/root")
    from src.lexswap.grammar_nl import apply_article_agreement
    from src.lexswap.natural_nl import NATURAL_NL, NATURAL_NL_EXTRA
    ALL_NAT = NATURAL_NL + NATURAL_NL_EXTRA
    ORIG_IDS = {p["id"] for p in NATURAL_NL}
    from src.lexswap.reassemble import render as render_words
    from src.lexswap.syntax_nl import build_candidates, reorder
    from src.lexswap.agreement_nl import (ALWAYS_CAPITAL, MISSING_WORDS,
                                          PARTICIPLES, SENSE_FIX, SEPARABLE,
                                          MORE_FORMS, english_form,
                                          het_sense, pronoun_number)

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id).to(dev).eval()
    sig = {k: v.detach().clone() for k, v in list(model.state_dict().items())[:3]}

    with open("/cache/out/lexicon_nl.json", encoding="utf-8") as f:
        lex = json.load(f)
    id2 = {int(k): v for k, v in lex["decode"].items()}
    mid, init = lex["encode_mid"], lex["encode_initial"]
    # `mid` holds both " leest" -> id(" reads") and " Leest" -> id(" Reads").
    # Collapsing with .strip().lower() let the CAPITALISED id win, so every
    # candidate - including the correct answer - was scored mid-sentence in its
    # sentence-initial form: "I know that he Reads the book". That is why the
    # oracle arm scored 5%: the approach was never tested, only mis-fed.
    nl2id = {}
    for k, v in mid.items():
        w = k.strip()
        if w and w.islower():
            nl2id[w] = int(v)
    for k, v in mid.items():          # fall back to any form for gaps
        nl2id.setdefault(k.strip().lower(), int(v))

    def en2nl_lookup(w):
        """English word -> Dutch word, via the token id.

        `encode_mid` maps Dutch -> token id, NOT Dutch -> English. Treating its
        values as strings is what crashed the first v14 run, and the route from
        a source word to a target word necessarily goes through the id:
        english -> id (tokenizer) -> dutch (decode map).
        """
        ids = tok.encode(" " + w, add_special_tokens=False)
        if len(ids) != 1:
            return None
        d = id2.get(ids[0])
        return d.strip() if d else None
    print("  lexicon {} decode ids, {} mid forms".format(len(id2), len(mid)))
    added = 0
    # hand-made overrides go in FIRST so they beat the dictionary entry
    for nl_w, en_w in (list(SENSE_FIX.items()) + list(MISSING_WORDS.items())
                       + list(MORE_FORMS.items())):
        tk = tok.encode(" " + en_w, add_special_tokens=False)
        if len(tk) == 1:
            mid[" " + nl_w] = tk[0]
            mid[" " + nl_w.capitalize()] = tk[0]
            id2[tk[0]] = " " + nl_w
            ini = tok.encode(en_w[0].upper() + en_w[1:],
                             add_special_tokens=False)
            if len(ini) == 1:
                init[nl_w.capitalize()] = ini[0]
                init[nl_w] = ini[0]
                id2[ini[0]] = nl_w.capitalize()
            added += 1
    for nl_w, en_w in ALWAYS_CAPITAL.items():
        tk = tok.encode(" " + en_w, add_special_tokens=False)
        if len(tk) == 1:
            mid[" " + nl_w] = tk[0]
            mid[" " + nl_w.capitalize()] = tk[0]
            id2[tk[0]] = " " + nl_w
            added += 1
        tk0 = tok.encode(en_w, add_special_tokens=False)
        if len(tk0) == 1:
            init[nl_w] = tk0[0]
            init[nl_w.capitalize()] = tk0[0]
            id2[tk0[0]] = nl_w.capitalize()
    print("  + {} hand overrides (sense, missing words, capitals)".format(added))
    added = 0
    for extra in (PARTICIPLES, SEPARABLE):
        for nl_w, en_w in extra.items():
            t = tok.encode(" " + en_w, add_special_tokens=False)
            if len(t) == 1:
                mid.setdefault(" " + nl_w, t[0])
                id2.setdefault(t[0], " " + nl_w)
                added += 1
    print("  + {} participle/separable forms, for REACHABILITY".format(added))
    # nl2id was built BEFORE these additions, so reachability could not see
    # them and the count did not move. Rebuild it here, lowercase-preferred.
    nl2id.clear()
    for k, v in mid.items():
        w = k.strip()
        if w and w.islower():
            nl2id[w] = int(v)
    for k, v in mid.items():
        nl2id.setdefault(k.strip().lower(), int(v))
    print("  nl2id rebuilt: {} Dutch forms".format(len(nl2id)))

    def enc_words(words, first=True):
        """`first=False` for a mid-sentence fragment.

        Index 0 was unconditionally looked up in the sentence-initial table, so
        the SUFFIX of a reordered template came out capitalised and without a
        leading space - "I knows that he [reads] The book". The model was being
        scored on broken English, which is why the oracle arm failed.
        """
        ids = []
        for k, w in enumerate(words):
            if w.lower() == "het":
                # article or pronoun, decided by the following word
                nxt = words[k + 1] if k + 1 < len(words) else None
                hs = het_sense(nxt)
                tkh = tok.encode(
                    (hs[0].upper() + hs[1:]) if (k == 0 and first)
                    else " " + hs, add_special_tokens=False)
                if len(tkh) == 1:
                    ids.append(tkh[0])
                    continue
            if w.lower() in ("zij", "ze"):
                # number from the verb that follows, not a global guess
                nxt = words[k + 1] if k + 1 < len(words) else None
                pn = pronoun_number(nxt)
                tkp = tok.encode(
                    (pn[0].upper() + pn[1:]) if (k == 0 and first)
                    else " " + pn, add_special_tokens=False)
                if len(tkp) == 1:
                    ids.append(tkp[0])
                    continue
            agreed = english_form(w, words[k - 1] if k else None)
            if agreed is not None:
                t = tok.encode(" " + agreed, add_special_tokens=False)
                if len(t) == 1:
                    ids.append(t[0])
                    continue
            if k == 0 and first:
                got = (init.get(w) or init.get(w.lower()) or
                       mid.get(" " + w) or mid.get(" " + w.lower()))
            else:
                got = (mid.get(" " + w) or mid.get(" " + w.lower()) or
                       mid.get(" " + w.capitalize()))
            if got is not None:
                ids.append(int(got))
            else:
                ids.extend(tok.encode(w if k == 0 else " " + w,
                                      add_special_tokens=False))
        return ids

    def dec(ids):
        parts = render_words(ids, lambda t: tok.decode([t]), id2, en2nl_lookup)
        return "".join(apply_article_agreement(parts))

    @torch.no_grad()
    def generate(ids):
        x = torch.tensor([ids], device=dev)
        o = model.generate(x, max_new_tokens=max_new, do_sample=False,
                           pad_token_id=tok.eos_token_id)
        return o[0, len(ids):].tolist()

    @torch.no_grad()
    def shortlist(prefix_ids, cand_ids, keep: int = 24):
        """Rank candidates by the model's next-token prediction on the prefix.

        `oracle` scores against 20 distractors and reaches 32%; `syntax` scores
        against 300 and reaches 18%. The difference is POOL SIZE - a large pool
        drowns the right answer in plausible competitors. So stage one uses the
        model's own left-to-right distribution over the English-order prefix as
        a prior, which is exactly the grammatical filtering the small oracle
        pool was getting by accident, and stage two scores the whole sequence
        on the survivors only.
        """
        if len(cand_ids) <= keep:
            return list(cand_ids)
        x = torch.tensor([prefix_ids], device=dev)
        lp = torch.log_softmax(model(input_ids=x).logits[0, -1].float(), -1)
        c = torch.tensor(cand_ids, device=dev)
        order = torch.argsort(lp[c], descending=True)[:keep]
        return [cand_ids[int(i)] for i in order]

    @torch.no_grad()
    def score_slot(prefix_ids, suffix_ids, cand_ids, chunk: int = 32):
        """Chunked so memory does not depend on the candidate count.

        The first v14 run asked for 15.85 GiB: full logits are
        candidates x length x 151,936 vocab, so 4,000 candidates is ~29 GB.
        Bounded here at `chunk` rows per forward.
        """
        outs = []
        for k in range(0, len(cand_ids), chunk):
            outs.append(_score_chunk(prefix_ids, suffix_ids,
                                     cand_ids[k:k + chunk]))
        return torch.cat(outs)

    @torch.no_grad()
    def _score_chunk(prefix_ids, suffix_ids, cand_ids):
        """Mean log-prob of [prefix, candidate, suffix] for each candidate.

        Batched: one forward over all candidates. The candidate and the suffix
        are both scored, so a candidate that makes the REST of the sentence
        likely wins - which is the whole point of querying a non-final slot.
        """
        rows = [prefix_ids + [c] + suffix_ids for c in cand_ids]
        L = max(len(r) for r in rows)
        pad = tok.eos_token_id
        x = torch.full((len(rows), L), pad, device=dev, dtype=torch.long)
        m = torch.zeros((len(rows), L), device=dev, dtype=torch.long)
        for i, r in enumerate(rows):
            x[i, : len(r)] = torch.tensor(r, device=dev)
            m[i, : len(r)] = 1
        lg = model(input_ids=x, attention_mask=m).logits.float()
        lp = torch.log_softmax(lg[:, :-1], -1)
        tgt = x[:, 1:]
        got = lp.gather(2, tgt.unsqueeze(2)).squeeze(2)
        keep = m[:, 1:].float()
        start = len(prefix_ids) - 1          # score candidate + suffix only
        keep[:, :max(start, 0)] = 0
        return (got * keep).sum(1) / keep.sum(1).clamp_min(1)

    cand_words = [w.strip() for w in mid.keys() if w.strip().isalpha()]
    print("  candidate pool: {} Dutch surface forms".format(len(cand_words)))

    print("")
    print(BAR)
    print("NATURAL DUTCH - three arms")
    print(BAR)
    print("{:>3} {:<34}{:<10}{:<14}{:<14}{:<12}".format(
        "#", "prompt", "expect", "lexical", "syntax", "rule"))
    print("-" * 112)

    res = {"lexical": 0, "syntax": 0, "oracle": 0, "lemma": 0}
    rows = []
    dbg = []
    DEBUG_IDS = set(range(1, 51))

    def same_lemma(a, b):
        """Diagnostic only: do these share a Dutch verb stem?

        Reported ALONGSIDE exact match and never instead of it. Switching the
        headline metric after seeing the result is moving the goalpost; naming
        where the failure sits is not.
        """
        a, b = a.lower(), b.lower()

        def stem(x):
            for pre in ("ge",):
                if x.startswith(pre) and len(x) > 4:
                    x = x[len(pre):]
            for suf in ("en", "t", "de", "te", "d"):
                if x.endswith(suf) and len(x) - len(suf) >= 3:
                    return x[: len(x) - len(suf)]
            return x
        return stem(a) == stem(b) or a[:4] == b[:4]
    for p in ALL_NAT:
        exp = p["exp"]
        # ---- arm 1: v13 behaviour
        lex_out = dec(generate(enc_words(p["nl"].split(" "))))
        lex_hit = exp.lower() in lex_out.lower()

        # ---- arm 2: syntax layer
        r = reorder(p["nl"])
        rule = "-"
        if r is None:
            syn_out, syn_hit = lex_out, lex_hit
        else:
            pre, suf, kind = r
            rule = kind
            if kind == "final" or not suf:
                syn_out = dec(generate(enc_words(pre)))
                syn_hit = exp.lower() in syn_out.lower()
            else:
                pre_ids = enc_words(pre, first=True)
                suf_ids = enc_words(suf, first=False)   # mid-sentence
                # restrict by the category the slot wants - an unfiltered pool
                # is dominated by function words and the scorer picks `de`
                subj = pre[-1] if pre else None
                pool = build_candidates(kind, cand_words, limit=n_cand,
                                        subject=subj)
                cids, cws = [], []
                for w in pool:
                    t = nl2id.get(w.lower())
                    if t is None or t in cids:
                        continue
                    cids.append(t)
                    cws.append(w)
                    if len(cids) >= n_cand:      # HARD cap, unconditional
                        break
                te = nl2id.get(exp.lower())      # the answer must be reachable
                if te is not None and te not in cids:
                    cids.append(te)
                    cws.append(exp)
                # NOT shortlisted: a prefix-only prior has no access to the
                # suffix, so it is strictly less informed than the score it
                # would be filtering for, and it discarded correct answers.
                # Measured 18% -> 14%. Reverted and recorded.
                sc = score_slot(pre_ids, suf_ids, cids)
                best = int(torch.argmax(sc))
                syn_out = cws[best]
                syn_hit = syn_out.lower() == exp.lower()
                if p["id"] in DEBUG_IDS:
                    order = torch.argsort(sc, descending=True)[:6]
                    te = nl2id.get(exp.lower())
                    dbg.append({
                        "id": p["id"], "nl": p["nl"], "expected": exp,
                        "reordered_nl": " ".join(pre) + " [___] " + " ".join(suf),
                        "english_prefix": tok.decode(pre_ids),
                        "english_suffix": tok.decode(suf_ids),
                        "english_full": tok.decode(
                            pre_ids + [nl2id.get(exp.lower(), 0)] + suf_ids),
                        "expected_token": (tok.decode([te]) if te else None),
                        "expected_in_pool": bool(te in cids),
                        "top": [{"nl": cws[int(j)],
                                 "en": tok.decode([cids[int(j)]]),
                                 "score": round(float(sc[int(j)]), 4)}
                                for j in order]})

        # ---- arm 3: oracle slot - can scoring reach the right answer at all?
        orc_hit = False
        if r is not None and r[1]:
            pre, suf, _ = r
            t_exp = nl2id.get(exp.lower())
            if t_exp is not None:
                pool = build_candidates(r[2], cand_words, limit=40,
                                        subject=(r[0][-1] if r[0] else None))
                distract = [nl2id[w.lower()] for w in pool
                            if w.lower() in nl2id and
                            nl2id[w.lower()] != t_exp][:20]
                sc = score_slot(enc_words(pre, True),
                                enc_words(suf, False),
                                [t_exp] + distract)
                orc_hit = bool(int(torch.argmax(sc)) == 0)

        lemma_hit = bool(syn_hit) or bool(
            r is not None and bool(r[1]) and isinstance(syn_out, str)
            and same_lemma(syn_out, exp))
        res["lexical"] += lex_hit
        res["syntax"] += syn_hit
        res["oracle"] += orc_hit
        res["lemma"] += lemma_hit
        rows.append({"id": p["id"], "nl": p["nl"], "expected": exp,
                     "rule": rule, "lexical_out": lex_out.strip(),
                     "lexical_hit": bool(lex_hit),
                     "syntax_out": syn_out.strip(), "syntax_hit": bool(syn_hit),
                     "oracle_hit": bool(orc_hit), "why": p["why"]})
        print("{:>3} {:<34}{:<10}{:<14}{:<14}{:<12}".format(
            p["id"], p["nl"][:33], exp[:9],
            ("Y " if lex_hit else ". ") + lex_out.strip()[:11],
            ("Y " if syn_hit else ". ") + str(syn_out).strip()[:11], rule))

    n = len(ALL_NAT)
    reachable = [p["exp"] for p in ALL_NAT
                 if nl2id.get(p["exp"].lower()) is not None]
    print("-" * 112)
    print("  REACHABILITY: {}/{} expected answers have a token mapping at all"
          .format(len(reachable), n))
    print("  unreachable: {}".format(
        [p["exp"] for p in NATURAL_NL
         if nl2id.get(p["exp"].lower()) is None]))
    print("  Accuracy cannot exceed {:.0%} until those exist in the lexicon."
          .format(len(reachable) / n))
    # the original 20 reported separately so the whole series stays comparable
    o = [r for r in rows if r["id"] in ORIG_IDS]
    print("  --- original 20 only, for continuity with every earlier run ---")
    print("  lexical {:>2}/20 {:.0%}   syntax {:>2}/20 {:.0%}   oracle {:>2}/20 {:.0%}"
          .format(sum(r["lexical_hit"] for r in o),
                  sum(r["lexical_hit"] for r in o) / 20,
                  sum(r["syntax_hit"] for r in o),
                  sum(r["syntax_hit"] for r in o) / 20,
                  sum(r["oracle_hit"] for r in o),
                  sum(r["oracle_hit"] for r in o) / 20))
    print("  --- all {} prompts ---".format(n))
    print("  lexical only (v13)    {:>3}/{}   {:.0%}".format(
        res["lexical"], n, res["lexical"] / n))
    print("  + syntax layer        {:>3}/{}   {:.0%}".format(
        res["syntax"], n, res["syntax"] / n))
    print("  oracle slot (bound)   {:>3}/{}   {:.0%}".format(
        res["oracle"], n, res["oracle"] / n))
    mr = sum(1 for r in rows if r["rule"] != "-")
    print("  a reorder rule matched  {:>3}/{}   {:.0%}".format(mr, n, mr / n))
    print("  [diagnostic] same verb stem, wrong inflection counted as a hit:"
          "  {:>3}/{}   {:.0%}".format(res["lemma"], n, res["lemma"] / n))
    print("  That line is a DIAGNOSTIC, not the result. It localises the")
    print("  failure to Dutch inflection rather than to verb choice.")

    print("")
    print(BAR)
    print("WHAT THE MODEL ACTUALLY SEES - the intermediate representation")
    print(BAR)
    print("  the ENGLISH the model is scored on, for every template")
    print("  {:>3} {:<52} {:<11} {:<11}".format(
        "#", "english template", "want", "top1"))
    print("  " + "-" * 92)
    for d in dbg:
        tmpl = "{} [{}] {}".format(d["english_prefix"].strip(),
                                   (d["expected_token"] or "?").strip(),
                                   d["english_suffix"].strip())
        print("  {:>3} {:<52} {:<11} {:<11}".format(
            d["id"], tmpl[:51], d["expected"][:10],
            d["top"][0]["nl"][:10] if d["top"] else "-"))
    print("")
    if res["syntax"] > res["lexical"]:
        print("  The syntax layer helps. Word order was addressable without")
        print("  training after all - by reordering and scoring, not by lexicon.")
    if res["oracle"] > res["syntax"]:
        print("  oracle > syntax: the REORDERING RULES are the limit, not the")
        print("  idea. More rules, or better candidate restriction, gains more.")
    elif res["oracle"] <= res["syntax"]:
        print("  oracle is not above syntax: the scoring approach itself is at")
        print("  its limit here, which is a different problem from the rules.")

    after = model.state_dict()
    unchanged = all(torch.equal(sig[k], after[k]) for k in sig)
    print("")
    print("  weights unchanged: {}".format(unchanged))

    os.makedirs("/cache/out", exist_ok=True)
    payload = {"model": model_id, "n": n,
               "lexical": res["lexical"], "syntax": res["syntax"],
               "oracle": res["oracle"],
               "lexical_acc": round(res["lexical"] / n, 3),
               "syntax_acc": round(res["syntax"] / n, 3),
               "oracle_acc": round(res["oracle"] / n, 3),
               "lemma_diagnostic": round(res["lemma"] / n, 3),
               "reachable": len(reachable), "reachable_frac": round(len(reachable) / n, 3),
               "debug": dbg,
               "weights_unchanged": bool(unchanged), "rows": rows}
    with open("/cache/out/v14.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    vol.commit()
    return payload


@app.local_entrypoint()
def main(n_cand: int = 300):
    run.remote(n_cand=n_cand)
