"""Grammar that a word-level map cannot express, and the smallest fix for it.

v10 reached output purity 0.956 with both fixable buckets at zero, so the
lexicon is complete by the word criterion. What is left is visible in the text
rather than in the metric:

    Het boek is op de  ->  tafel. De boek is op de tafel
                                  ^^ should be `Het boek`

CAUSE. Dutch has two definite articles chosen by noun gender - `de` for
common-gender nouns, `het` for neuter. English has one word, `the`. A
token-by-token map therefore CANNOT choose: the information needed is in the
NEXT word, not in the token being rendered.

This is a different kind of failure from everything fixed so far. Collisions,
missing entries, fragments and casing were all properties of the mapping
tables. This one is a property of the *decoding procedure*: rendering one token
at a time is structurally unable to express it, no matter how good the lexicon
gets.

FIX. Make the article context-aware. When a token renders as `de` and the next
token renders as a neuter noun, render `het` instead. That turns decode from a
per-token lookup into a one-token-lookahead pass - a small change in kind, and
the smallest one that can express the rule at all.

LIMIT. `HET_NOUNS` below is hand-built from the project's own vocabulary and
common Dutch neuters. It is not exhaustive: Dutch gender is not predictable
from form, and a complete list needs a real Dutch lexical database. So this
fixes the article where the noun is known and leaves `de` as the fallback,
which is the more common article and therefore the better default.
"""

# Dutch neuter nouns: these take `het`. Hand-built, not exhaustive.
HET_NOUNS = {
    # from this project's own seed
    "boek", "huis", "water", "kind", "jaar", "uur", "woord", "getal",
    "papier", "vuur", "goud", "zilver", "ijzer", "hout", "brood", "zout",
    "vlees", "ei", "raam", "bed", "paard", "schaap", "licht", "gras",
    "geld", "werk", "land", "leven", "hoofd", "oog", "oor", "been",
    "hart", "lichaam", "bos", "veld", "dorp", "eiland", "meer", "strand",
    "weer", "seizoen", "begin", "einde", "midden", "deel", "stuk",
    "ding", "punt", "doel", "plan", "idee", "antwoord", "verhaal",
    "lied", "spel", "feest", "cadeau", "pakket", "bericht", "nieuws",
    "verschil", "voorbeeld", "probleem", "resultaat", "bedrijf",
    "kantoor", "gebouw", "station", "ziekenhuis", "museum", "theater",
    "restaurant", "hotel", "zwembad", "park", "plein", "kasteel",
    "dier", "varken", "konijn", "insect", "blad", "zaad", "fruit",
    "graan", "meel", "deeg", "koekje", "snoep", "glas", "bord", "mes",
    "bad", "toilet", "dak", "plafond", "trapje", "hek", "slot",
    "oog", "gezicht", "haar", "bloed", "vel", "bot", "brein",
    "gevoel", "geluk", "geduld", "vertrouwen", "respect", "gevaar",
    "systeem", "model", "proces", "project", "niveau", "aantal",
    "percentage", "gemiddelde", "totaal", "bedrag", "tarief",
    "contract", "document", "rapport", "artikel", "boekje", "blaadje",
}

# Words where MUSE returned an inflected form rather than the lemma.
# `De kleur van melk is gele` - predicative adjectives are uninflected in
# Dutch, so the dictionary form was wrong in context. Hand entries take
# priority over the dictionary, which is the existing order and is why this
# works as a plain override.
LEMMA_FIX = {
    "geel": "yellow",
    "groot": "big",
    "klein": "small",
    "oud": "old",
    "nieuw": "new",
    "lang": "long",
    "kort": "short",
    "hoog": "high",
    "laag": "low",
    "warm": "warm",
    "koud": "cold",
    "snel": "fast",
    "sterk": "strong",
    "zwak": "weak",
    "mooi": "beautiful",
    "goed": "good",
    "slecht": "bad",
    "duur": "expensive",
    "zwaar": "heavy",
    "licht": "light",
    "vol": "full",
    "leeg": "empty",
    "nat": "wet",
    "droog": "dry",
    "jong": "young",
    "rond": "round",
    "recht": "straight",
    "zacht": "soft",
    "hard": "hard",
    "diep": "deep",
    "breed": "wide",
    "dun": "thin",
    "dik": "thick",
    "vies": "dirty",
    "schoon": "clean",
    "stil": "quiet",
    "druk": "busy",
    "vrij": "free",
    "waar": "true",
    "vals": "false",
}


def apply_article_agreement(parts):
    """One-token lookahead: fix `de` to `het` before a neuter noun.

    `parts` is the list of rendered strings, in order. Returns a new list.
    Only the article is touched, and only when the following noun is known to
    be neuter - otherwise `de` stays, being the more common article.
    """
    out = list(parts)
    for i in range(len(out) - 1):
        cur = out[i]
        nxt = out[i + 1].strip().lower()
        if nxt not in HET_NOUNS:
            continue
        if cur == " de":
            out[i] = " het"
        elif cur == " De":
            out[i] = " Het"
        elif cur == "De":
            out[i] = "Het"
        elif cur == "de":
            out[i] = "het"
    return out
