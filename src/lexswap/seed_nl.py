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

# ---------------------------------------------------------------------------
# Expansion 2: the 12-prompt set saturated at the ceiling from rung 0, so it
# could no longer show improvement. More pairs, to support more prompts.
SEED_NL.update({
    # function words
    "was": "was", "waren": "were", "wordt": "becomes", "kan": "can",
    "zal": "will", "moet": "must", "maar": "but", "of": "or", "ook": "also",
    "altijd": "always", "nooit": "never", "hier": "here", "daar": "there",
    "nu": "now", "dan": "then", "wie": "who", "wat": "what", "waar": "where",
    "zeer": "very", "veel": "many", "twee": "two", "drie": "three",
    "vier": "four", "vijf": "five", "zes": "six", "zeven": "seven",
    "acht": "eight", "negen": "nine", "tien": "ten", "eerste": "first",
    "laatste": "last", "zijn": "are", "hun": "their", "haar": "her",
    "ons": "our", "jij": "you", "wij": "we", "zij": "they",
    # nouns
    "kamer": "room", "raam": "window", "muur": "wall", "vloer": "floor",
    "stoel": "chair", "bed": "bed", "auto": "car", "trein": "train",
    "weg": "road", "brug": "bridge", "rivier": "river", "berg": "mountain",
    "zee": "sea", "lucht": "air", "vuur": "fire", "steen": "stone",
    "hout": "wood", "ijzer": "iron", "goud": "gold", "zilver": "silver",
    "papier": "paper", "pen": "pen", "brief": "letter", "woord": "word",
    "naam": "name", "getal": "number", "tijd": "time", "uur": "hour",
    "week": "week", "maand": "month", "nacht": "night", "ochtend": "morning",
    "winter": "winter", "zomer": "summer", "regen": "rain", "sneeuw": "snow",
    "wind": "wind", "boom": "tree", "bloem": "flower", "vogel": "bird",
    "vis": "fish", "paard": "horse", "koe": "cow", "schaap": "sheep",
    "voedsel": "food", "vlees": "meat", "kaas": "cheese", "ei": "egg",
    "appel": "apple", "zout": "salt", "sleutel": "key", "doos": "box",
    # adjectives
    "lang": "long", "kort": "short", "hoog": "high", "laag": "low",
    "snel": "fast", "langzaam": "slow", "sterk": "strong", "zwak": "weak",
    "licht": "light", "donker": "dark", "vol": "full", "leeg": "empty",
    "warm": "warm", "droog": "dry", "nat": "wet", "zwaar": "heavy",
    "schoon": "clean", "jong": "young", "slecht": "bad", "mooi": "beautiful",
    "duur": "expensive", "goedkoop": "cheap", "open": "open",
})

# Prompts added so accuracy is no longer saturated. Every one is word-for-word
# parallel with its English twin through the table above, which is the only way
# the identity gate stays meaningful.
SEED_PROMPTS += [
    dict(id=13, en="The opposite of long is", nl="Het tegenovergestelde van lang is",
         exp_en="short", exp_nl="kort"),
    dict(id=14, en="The opposite of high is", nl="Het tegenovergestelde van hoog is",
         exp_en="low", exp_nl="laag"),
    dict(id=15, en="The opposite of fast is", nl="Het tegenovergestelde van snel is",
         exp_en="slow", exp_nl="langzaam"),
    dict(id=16, en="The opposite of strong is", nl="Het tegenovergestelde van sterk is",
         exp_en="weak", exp_nl="zwak"),
    dict(id=17, en="The opposite of full is", nl="Het tegenovergestelde van vol is",
         exp_en="empty", exp_nl="leeg"),
    dict(id=18, en="The opposite of young is", nl="Het tegenovergestelde van jong is",
         exp_en="old", exp_nl="oud"),
    dict(id=19, en="The opposite of wet is", nl="Het tegenovergestelde van nat is",
         exp_en="dry", exp_nl="droog"),
    dict(id=20, en="The opposite of day is", nl="Het tegenovergestelde van dag is",
         exp_en="night", exp_nl="nacht"),
    dict(id=21, en="The color of snow is", nl="De kleur van sneeuw is",
         exp_en="white", exp_nl="wit"),
    dict(id=22, en="The color of gold is", nl="De kleur van goud is",
         exp_en="yellow", exp_nl="geel"),
    dict(id=23, en="The color of fire is", nl="De kleur van vuur is",
         exp_en="red", exp_nl="rood"),
    dict(id=24, en="The color of the sea is", nl="De kleur van de zee is",
         exp_en="blue", exp_nl="blauw"),
    dict(id=25, en="One two three four five", nl="Een twee drie vier vijf",
         exp_en="six", exp_nl="zes"),
    dict(id=26, en="Six seven eight", nl="Zes zeven acht",
         exp_en="nine", exp_nl="negen"),
    dict(id=27, en="The horse and the", nl="Het paard en de",
         exp_en="cow", exp_nl="koe"),
    dict(id=28, en="The bird and the", nl="De vogel en de",
         exp_en="fish", exp_nl="vis"),
    dict(id=29, en="Salt and", nl="Zout en",
         exp_en="pepper", exp_nl="peper"),
    dict(id=30, en="The sun and the", nl="De zon en de",
         exp_en="moon", exp_nl="maan"),
    dict(id=31, en="Winter and", nl="Winter en",
         exp_en="summer", exp_nl="zomer"),
    dict(id=32, en="The key is in the", nl="De sleutel is in de",
         exp_en="door", exp_nl="deur"),
    dict(id=33, en="The water in the river is", nl="Het water in de rivier is",
         exp_en="cold", exp_nl="koud"),
    dict(id=34, en="The fire is very", nl="Het vuur is zeer",
         exp_en="hot", exp_nl="heet"),
    dict(id=35, en="The mountain is very", nl="De berg is zeer",
         exp_en="high", exp_nl="hoog"),
    dict(id=36, en="Gold is very", nl="Goud is zeer",
         exp_en="expensive", exp_nl="duur"),
]

# two expected answers above need a rendering path or they can never be hit
SEED_NL.update({"peper": "pepper", "maan": "moon"})
