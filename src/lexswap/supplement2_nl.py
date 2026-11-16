"""Supplement 2 — targeted from the v9 frequency-ranked gap list.

v9 printed the remaining dictionary gaps ordered by token id, which is a
frequency proxy, and the head of that list was:

    th in to re of st is be on de wh if it as al an or tr ex se le at ch pr by
    sh he we us pl un do el en Th ab cont up bo go

Most of those are ordinary English function words, and **MUSE does not contain
them**. The 82,167-headword file is built by word alignment and curated for
bilingual lexicon induction, so the closed-class core of the language is partly
missing. No wider scan finds them; they have to be supplied.

TWO DIRECTIONS, and the distinction matters.

`ENC_DEC` pairs go into both tables as usual.

`DEC_ONLY` exists because of a collision inside my own supplement. Dutch `het`
means both *the* and *it*, and `SEED_NL` had already claimed `het -> the`, so
`het -> it` was silently dropped by `setdefault` and ` It` stayed untranslated
in v9's output.

The fix is the same lesson the dictionary collisions taught: a collision
constrains **input only**. On output, `id(" it")` can render as `" het"` while
`id(" the")` also renders as `" het"`, with no conflict whatsoever. So words
whose Dutch form is already taken are mapped in the decode direction alone.
"""

# both directions - no conflict with anything already claimed
ENC_DEC = {
    "in": "in", "naar": "to", "van": "of", "op": "on", "bij": "at",
    "door": "by", "om": "for", "met": "with", "aan": "to",
    "hij": "he", "wij": "we", "ons": "us", "zij": "they", "u": "you",
    "doen": "do", "omhoog": "up", "omlaag": "down", "gaan": "go",
    "komen": "come", "zien": "see", "krijgen": "get", "zetten": "put",
    "houden": "keep", "laten": "let", "vragen": "ask", "proberen": "try",
    "beginnen": "begin", "eindigen": "end", "stoppen": "stop",
    "openen": "open", "sluiten": "close", "brengen": "bring",
    "sturen": "send", "kopen": "buy", "verkopen": "sell",
    "betalen": "pay", "leren": "learn", "onderwijzen": "teach",
    "helpen": "help", "bouwen": "build", "schrijven": "write",
    "lezen": "read", "tellen": "count", "meten": "measure",
    "veranderen": "change", "bewegen": "move", "dragen": "carry",
    "wachten": "wait", "zoeken": "search", "volgen": "follow",
    "tonen": "show", "vertellen": "tell", "antwoorden": "answer",
    "noemen": "call", "voelen": "feel", "horen": "hear", "ruiken": "smell",
    "eten": "eat", "drinken": "drink", "slapen": "sleep",
    "staan": "stand", "zitten": "sit", "vallen": "fall", "stijgen": "rise",
    "duwen": "push", "trekken": "pull", "snijden": "cut", "breken": "break",
    "vullen": "fill", "legen": "empty", "wassen": "wash", "drogen": "dry",
    "koken": "cook", "bakken": "bake", "groeien": "grow",
}

# decode direction only: the Dutch form is already claimed by another sense
DEC_ONLY = {
    "it": "het",          # SEED_NL already holds het -> the
    "is": "is",
    "be": "zijn",
    "are": "zijn",
    "as": "als",          # SUPPLEMENT_NL already holds als -> if
    "an": "een",          # SEED_NL already holds een -> a
    "or": "of",           # Dutch `of` means or; SEED_NL holds van -> of
    "and": "en",
    "not": "niet",
    "that": "dat",
    "this": "dit",
    "the": "de",
    "a": "een",
    "to": "naar",
    "of": "van",
    "all": "alle",
    "no": "nee",
    "yes": "ja",
    "very": "zeer",
    "also": "ook",
    "only": "alleen",
    "just": "net",
    "even": "zelfs",
    "much": "veel",
    "many": "veel",
    "both": "beide",
    "other": "ander",
    "same": "zelfde",
    "own": "eigen",
    "such": "zulk",
    "then": "dan",
    "than": "dan",
    "when": "wanneer",
    "where": "waar",
    "how": "hoe",
    "why": "waarom",
    "who": "wie",
    "what": "wat",
    "which": "welke",
}
