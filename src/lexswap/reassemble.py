"""Word-level reassembly: translate words, not tokens.

v11 output:

    Brood en  ->  Cinnamon        purity 0.00

The word is there and correct. It is un-rendered because the model spells it as
TWO tokens, `" C"` + `"innamon"`, and a per-token renderer sees a
language-neutral single letter followed by a fragment with no word-level entry.
The same explains `fl`, `oul` and `key` in the earlier residuals: they are
pieces of multi-token words.

CAUSE. The procedure renders one token at a time, but the unit that has a
translation is the WORD. Whenever a word costs more than one token - which is
most of the long tail of any BPE vocabulary - per-token rendering cannot reach
it, however complete the lexicon is.

This is the same class of problem as the article agreement in `grammar_nl`, and
it answers to the rule that came out of it:

> when a residual error cannot be removed by any entry in the table, the table
> is not what is wrong - ask what the procedure cannot express.

FIX. Group the token stream into words before rendering. A word starts at a
token carrying a leading space (or at the start of the sequence) and continues
through every following token that carries none. Look the assembled word up as
a whole; render it as one target word if found; otherwise fall back to the
per-token path, which is what v11 already did.

The fallback matters: reassembly can only ever add renderings, never remove
one, so this cannot regress purity.
"""


def group_words(pieces):
    """Group (id, decoded) pairs into words.

    Returns a list of lists. A new group starts on a token with a leading
    space, on a token that is not alphabetic, or at the sequence start.
    """
    groups = []
    for tid, text in pieces:
        bare = text.lstrip(" ")
        alpha = bare.isalpha()
        starts = text.startswith(" ") or not alpha or not groups
        if starts or not groups[-1][-1][1].lstrip(" ").isalpha():
            groups.append([(tid, text)])
        else:
            groups[-1].append((tid, text))
    return groups


def render(ids, decode_tok, id2, lookup):
    """Render a token sequence, translating whole words where possible.

    decode_tok(id) -> the source string for one token
    id2            -> the per-token rendering map, used as the fallback
    lookup(word)   -> the target word for an assembled source word, or None
    """
    pieces = [(int(i), decode_tok(int(i))) for i in ids]
    out = []
    for grp in group_words(pieces):
        if len(grp) == 1:
            tid, text = grp[0]
            out.append(id2.get(tid, text))
            continue
        joined = "".join(t for _, t in grp)
        lead = " " if joined.startswith(" ") else ""
        word = joined.lstrip(" ")
        if word.isalpha():
            tgt = lookup(word.lower())
            if tgt:
                if word[0].isupper():
                    tgt = tgt[0].upper() + tgt[1:]
                out.append(lead + tgt)
                continue
        # not found: the per-token path, exactly as before. Reassembly can
        # only add renderings, so purity cannot regress.
        for tid, text in grp:
            out.append(id2.get(tid, text))
    return out
