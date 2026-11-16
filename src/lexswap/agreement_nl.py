"""Subject-verb agreement in the ENCODE direction, and the forms that were missing.

The instrumented run showed the dominant blocker:

    #1  'I knows that he' [___] ' the book'
         ^^^^^^^ broken English, so every prediction after it is unreliable

        lezen  ' read'   -3.1668   <- wins
        leest  ' reads'  -4.2272   <- correct

One Dutch form maps to two English forms depending on the subject:

    weet -> know    after ik / wij / zij(plural) / jullie
    weet -> knows   after hij / zij(singular) / het

That is AGREEMENT, and the per-token encoder is blind to the subject - the same
shape of problem as `de` vs `het`, which needed a lookahead in decode. This one
needs a lookBACK in encode.

Third application of the rule this project keeps arriving at:

> when a residual error cannot be removed by any entry in the table, the table
> is not what is wrong - ask what the procedure cannot express.

`REACHABILITY` also showed four expected answers with no token mapping at all -
`gelezen`, `opbellen`, `gezegd` - so those prompts were unanswerable rather
than answered wrongly. PARTICIPLES and INFINITIVES below close that, added as
whole paradigms of common verbs rather than as the specific test answers, which
would be fitting the test rather than the language.
"""

# subjects that take the English -s form
THIRD_SINGULAR = {"hij", "ze", "het", "men", "wie", "iemand", "niemand",
                  "alles", "iets", "dit", "dat", "die", "deze"}
# `zij` is ambiguous in Dutch - she (3sg) or they (3pl). Singular is the more
# frequent reading sentence-initially, and the wrong choice is recorded as a
# known limitation rather than silently preferred.
AMBIGUOUS_SUBJ = {"zij"}
NON_THIRD = {"ik", "wij", "we", "jij", "je", "jullie", "u", "ze"}

# Dutch finite form -> (base English, third-singular English)
VERB_AGREEMENT = {
    "weet": ("know", "knows"),
    "leest": ("read", "reads"),
    "ziet": ("see", "sees"),
    "eet": ("eat", "eats"),
    "loopt": ("walk", "walks"),
    "komt": ("come", "comes"),
    "gaat": ("go", "goes"),
    "zegt": ("say", "says"),
    "denkt": ("think", "thinks"),
    "vindt": ("find", "finds"),
    "maakt": ("make", "makes"),
    "neemt": ("take", "takes"),
    "geeft": ("give", "gives"),
    "doet": ("do", "does"),
    "heeft": ("have", "has"),
    "krijgt": ("get", "gets"),
    "houdt": ("keep", "keeps"),
    "speelt": ("play", "plays"),
    "werkt": ("work", "works"),
    "woont": ("live", "lives"),
    "wil": ("want", "wants"),
    "kan": ("can", "can"),
    "moet": ("must", "must"),
    "zal": ("will", "will"),
    "mag": ("may", "may"),
    "schrijft": ("write", "writes"),
    "koopt": ("buy", "buys"),
    "betaalt": ("pay", "pays"),
    "vraagt": ("ask", "asks"),
    "helpt": ("help", "helps"),
    "brengt": ("bring", "brings"),
    "draagt": ("carry", "carries"),
    "zoekt": ("search", "searches"),
    "volgt": ("follow", "follows"),
    "hoort": ("hear", "hears"),
    "voelt": ("feel", "feels"),
    "slaapt": ("sleep", "sleeps"),
    "staat": ("stand", "stands"),
    "zit": ("sit", "sits"),
    "valt": ("fall", "falls"),
    "wacht": ("wait", "waits"),
}

# Whole paradigms, not the test's answers. Dutch past participle -> English.
PARTICIPLES = {
    "gelezen": "read", "gezien": "seen", "gegeten": "eaten",
    "gelopen": "walked", "gekomen": "come", "gegaan": "gone",
    "gezegd": "said", "gedacht": "thought", "gevonden": "found",
    "gemaakt": "made", "genomen": "taken", "gegeven": "given",
    "gedaan": "done", "gehad": "had", "gekregen": "got",
    "gehouden": "kept", "gespeeld": "played", "gewerkt": "worked",
    "gewoond": "lived", "geschreven": "written", "gekocht": "bought",
    "betaald": "paid", "gevraagd": "asked", "geholpen": "helped",
    "gebracht": "brought", "gedragen": "carried", "gezocht": "searched",
    "gevolgd": "followed", "gehoord": "heard", "gevoeld": "felt",
    "geslapen": "slept", "gestaan": "stood", "gezeten": "sat",
    "gevallen": "fallen", "gewacht": "waited", "geweest": "been",
    "geworden": "become", "gebleven": "stayed", "gestuurd": "sent",
    "geleerd": "learned", "gebouwd": "built", "geopend": "opened",
}

# Separable verbs: Dutch writes them as one infinitive, English as two words.
# Only the first part can be a single token, so the second is lost - recorded
# as a limitation rather than papered over.
SEPARABLE = {
    "opbellen": "call", "opstaan": "rise", "uitgaan": "leave",
    "aankomen": "arrive", "meenemen": "take", "afmaken": "finish",
    "aanzetten": "start", "uitzetten": "stop", "opschrijven": "write",
    "terugkomen": "return", "binnenkomen": "enter", "weggaan": "depart",
}


def english_form(dutch_verb, prev_word):
    """Pick the English verb form that agrees with the Dutch subject.

    Returns None when the word is not an agreeing verb, so the caller falls
    back to the ordinary lexicon path and nothing can regress.
    """
    pair = VERB_AGREEMENT.get(dutch_verb.lower())
    if pair is None:
        return None
    base, third = pair
    p = (prev_word or "").lower()
    if p in THIRD_SINGULAR or p in AMBIGUOUS_SUBJ:
        return third
    if p in NON_THIRD:
        return base
    return third      # a bare noun subject is third person singular
