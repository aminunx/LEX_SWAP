"""Rung 1 of the ladder: a hand-made Dutch lexicon, small and exact.

The full-vocabulary run changed five things at once - coverage, collisions,
word sense, word order, morphology - so a failure could not be attributed to
any of them. This seed removes four of the five by construction:

  coverage    100% on the prompts below, so nothing falls back to the model's
              own Dutch tokens and the sequence stays in ONE regime
  collisions  zero: every English side is distinct, chosen by hand
  word sense  zero ambiguity: each pair is picked, not machine-translated
  morphology  avoided: only forms that actually appear in the prompts

What is left is word order and the model itself. That is the thing worth
measuring, and it could not be seen through the noise of the big run.

THE PREDICTION, recorded before running. Every prompt below is a word-for-word
parallel of its English twin through this table. So the swap arm must encode to
the SAME token ids as the English arm, and therefore produce an IDENTICAL
continuation. Rung 1 is a correctness test of the codec before it is an
experiment about language: if `swap` and `english` differ at all here, the bug
is in the codec, not a finding about Dutch.
"""

# Dutch -> English. One-to-one on the English side, verified at load time.
# Dutch `de` and `het` both mean "the"; `de` is the one the reverse direction
# will render, so output will sometimes read `de` where `het` is correct. That
# is a known, bounded grammatical cost, recorded rather than hidden.
SEED_NL = {
    # function words
    "de": "the", "het": "the", "een": "a", "is": "is", "zijn": "are",
    "van": "of", "in": "in", "op": "on", "en": "and", "niet": "not",
    "met": "with", "voor": "for", "naar": "to", "dat": "that", "dit": "this",
    "ik": "I", "hij": "he", "zij": "she", "mijn": "my", "heeft": "has",
    "was": "was", "zeer": "very",
    # nouns
    "huis": "house", "boek": "book", "tafel": "table", "hond": "dog",
    "kat": "cat", "man": "man", "vrouw": "woman", "kind": "child",
    "water": "water", "melk": "milk", "brood": "bread", "zon": "sun",
    "stad": "city", "dag": "day", "jaar": "year", "deur": "door",
    "tuin": "garden", "straat": "street", "school": "school",
    "kleur": "color", "gras": "grass", "tegenovergestelde": "opposite",
    # adjectives
    "groot": "big", "klein": "small", "nieuw": "new", "oud": "old",
    "rood": "red", "groen": "green", "blauw": "blue", "wit": "white",
    "zwart": "black", "koud": "cold", "heet": "hot", "goed": "good",
    # verbs
    "leest": "reads", "ziet": "sees", "eet": "eats", "loopt": "walks",
    "komt": "comes", "gaat": "goes", "zie": "see",
}

# Each Dutch prompt is a word-for-word parallel of its English twin through
# SEED_NL, so coverage must come out at 100% and the two arms must agree.
SEED_PROMPTS = [
    dict(id=1, en="The book is on the", nl="Het boek is op de",
         exp_en="table", exp_nl="tafel"),
    dict(id=2, en="The opposite of big is", nl="Het tegenovergestelde van groot is",
         exp_en="small", exp_nl="klein"),
    dict(id=3, en="The opposite of cold is", nl="Het tegenovergestelde van koud is",
         exp_en="hot", exp_nl="heet"),
    dict(id=4, en="The opposite of new is", nl="Het tegenovergestelde van nieuw is",
         exp_en="old", exp_nl="oud"),
    dict(id=5, en="The opposite of black is", nl="Het tegenovergestelde van zwart is",
         exp_en="white", exp_nl="wit"),
    dict(id=6, en="Red green and", nl="Rood groen en",
         exp_en="blue", exp_nl="blauw"),
    dict(id=7, en="The color of grass is", nl="De kleur van gras is",
         exp_en="green", exp_nl="groen"),
    dict(id=8, en="The color of milk is", nl="De kleur van melk is",
         exp_en="white", exp_nl="wit"),
    dict(id=9, en="The man and the", nl="De man en de",
         exp_en="woman", exp_nl="vrouw"),
    dict(id=10, en="The dog and the", nl="De hond en de",
         exp_en="cat", exp_nl="kat"),
    dict(id=11, en="Bread and", nl="Brood en",
         exp_en="milk", exp_nl="melk"),
    dict(id=12, en="The man reads a", nl="De man leest een",
         exp_en="book", exp_nl="boek"),
]


def check(tokenizer):
    """Report which English sides are NOT a single token, and any collisions.

    A multi-token English side breaks the one-id-per-word assumption the whole
    swap rests on, so these are dropped rather than silently mis-encoded.
    """
    multi, seen, coll = [], {}, {}
    for nl, en in SEED_NL.items():
        ids = tokenizer.encode(" " + en, add_special_tokens=False)
        if len(ids) != 1:
            multi.append((nl, en, len(ids)))
            continue
        coll.setdefault(en, []).append(nl)
        seen[nl] = ids[0]
    return {"usable": seen,
            "multi_token": multi,
            "english_side_shared": {k: v for k, v in coll.items() if len(v) > 1}}
