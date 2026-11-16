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


# ----------------------------------------------------------------------
# From dumping all 50 templates.
#
# PRONOUN_FIX: `zij` is she or they. The verb agreement already treats it as
# third singular, but the pronoun itself still rendered as `they`, so the
# templates read "They has read the book" and "He says that they sings" -
# ungrammatical English produced by my own half-applied fix. Resolving both
# halves the same way is the point: a consistent wrong guess beats an
# inconsistent one, because the model can at least parse it.
PRONOUN_FIX = {"zij": "she", "ze": "she"}

# MISSING: words that appeared untranslated in the templates, plus two whose
# dictionary sense was wrong for the context.
MISSING_WORDS = {
    "toen": "then",
    "vorige": "previous",
    "week": "week",
    "vanmorgen": "morning",
    "vanmiddag": "afternoon",
    "vanavond": "evening",
    "straks": "soon",
    "lied": "song",
    "bal": "ball",
    "krant": "newspaper",
    "deur": "door",
    "weg": "away",        # the dictionary gave `road`; here it is `away`
    "morgen": "tomorrow",  # the dictionary gave `morning`
    "gisteren": "yesterday",
    "vandaag": "today",
    "nu": "now",
    "al": "already",
    "nog": "yet",
    "niets": "nothing",
    "iets": "something",
    "geld": "money",
    "huis": "house",
    "auto": "car",
    "film": "film",
    "trein": "train",
    "bed": "bed",
    "werk": "work",
    "ziek": "ill",
    "aardig": "kind",
    "donker": "dark",
    "thuis": "home",
}


# ----------------------------------------------------------------------
# PRONOUN_FIX was applied unconditionally and broke what it had just fixed:
# "Zij hebben vorige week het huis" rendered as "She have sold ...". Dutch
# `zij` is she or they, and the giveaway is the NUMBER OF THE VERB that
# follows - heeft/is/was are singular, hebben/zijn/waren are plural.
#
# This is the mirror of the verb agreement: there the subject decided the verb
# form, here the verb decides the pronoun. Same information, read the other
# way, and it has to be read both ways or the two halves contradict.
PLURAL_VERBS = {"hebben", "zijn", "waren", "worden", "gaan", "komen",
                "doen", "weten", "kunnen", "willen", "moeten", "zullen",
                "lezen", "zien", "maken", "nemen", "geven", "wonen",
                "spelen", "werken", "denken", "zeggen", "vinden", "hopen",
                "blijven", "staan", "zitten", "nemen", "kopen"}
SINGULAR_VERBS = {"heeft", "is", "was", "wordt", "gaat", "komt", "doet",
                  "weet", "kan", "wil", "moet", "zal", "leest", "ziet",
                  "maakt", "neemt", "geeft", "woont", "speelt", "werkt",
                  "denkt", "zegt", "vindt", "hoopt", "blijft", "staat",
                  "zit", "koopt", "at", "ging", "kwam", "zei", "had"}


def pronoun_number(next_word):
    """`she` or `they` for an ambiguous `zij`, decided by the verb after it."""
    w = (next_word or "").lower()
    if w in PLURAL_VERBS:
        return "they"
    if w in SINGULAR_VERBS:
        return "she"
    return "she"      # singular is the commoner sentence-initial reading


# These must never get a lowercase form: English `I` is always capitalised,
# and the templates were reading "i" mid-sentence, which is not English.
ALWAYS_CAPITAL = {"ik": "I"}

# Senses the dictionary got wrong in context.
#   je   -> you   (the dictionary gave `your`; `jouw` is your)
#   nog  -> yet, but `nog niet` is the unit "not yet" - handled by order below
SENSE_FIX = {"je": "you", "jij": "you", "jullie": "you", "u": "you",
             "mij": "me", "hem": "him", "haar": "her", "ons": "us",
             "hen": "them", "wie": "whom", "aankwamen": "arrived",
             "aankwam": "arrived", "kwamen": "came", "zaten": "sat"}


# ----------------------------------------------------------------------
# `het` is the definite article AND the pronoun `it`. Template #17 rendered
# "Toen wij aankwamen was het al" as "... was the already", where English needs
# "it was already dark".
#
# This is the third word with one Dutch form and two English ones - after
# `de/het` for gender and `zij` for number - and the shape is identical every
# time: the choice lives in a NEIGHBOURING word, so no per-token table can
# hold it. A verb after it means the pronoun; a noun after it means the
# article.
ARTICLE_NEXT_IS_VERB = SINGULAR_VERBS | PLURAL_VERBS | {
    "al", "niet", "nog", "ook", "er", "was", "is", "wordt", "werd"}


def het_sense(next_word):
    """`it` or `the` for Dutch `het`, decided by what follows."""
    w = (next_word or "").lower()
    if not w:
        return "it"
    if w in ARTICLE_NEXT_IS_VERB:
        return "it"
    return "the"


# forms still missing from the lexicon, seen as [?] in the template dump
MORE_FORMS = {
    "gooit": "throws", "gooien": "throw", "gegooid": "thrown",
    "zingen": "sing", "zingt": "sings", "gezongen": "sung",
    "opent": "opens", "openen": "open", "geopend": "opened",
    "verandert": "changes", "veranderen": "change",
    "verkopen": "sell", "verkoopt": "sells",
    "schrijven": "write", "schrijft": "writes",
    "zwemmen": "swim", "zwemt": "swims", "gezwommen": "swum",
    "horen": "hear", "hoort": "hears", "gehoord": "heard",
    "helpen": "help", "helpt": "helps", "geholpen": "helped",
    "kopen": "buy", "koopt": "buys",
    "lezen": "read", "leest": "reads",
    "nemen": "take", "neemt": "takes",
    "blijft": "stays", "blijven": "stay",
    "ziek": "ill", "aardig": "kind", "stad": "city", "tuin": "garden",
}


# `te` is inserted by the modal rule and had no mapping at all, so it appeared
# verbatim in the English templates: "He wants te call you tomorrow". I had
# assumed the dictionary covered a word my own code inserts.
INSERTED_WORDS = {"te": "to"}
