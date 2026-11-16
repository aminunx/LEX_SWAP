"""Hand-made supplement: what MUSE does not carry, and what it cannot carry.

The v8 diagnostic found two distinct gaps that the real dictionary left, and
they need different kinds of fix.

GAP 1 - common function words absent from MUSE. ` If`, ` It`, ` at` came back
as `whole_word_no_entry`, meaning they are genuinely not in the 82,167-headword
file. MUSE dictionaries are built by word alignment and curated for bilingual
lexicon induction, so some high-frequency function words simply are not in
them. These are few, closed-class, and safe to supply by hand.

GAP 2 - subword fragments. `innamon` from `cinnamon` has no word-level entry in
MUSE or in any human dictionary, because it is not a word. What it does have is
a MORPHOLOGICAL correspondence, and English-Dutch suffixes map regularly enough
to be worth rendering.

IMPORTANT: fragment mappings are applied to the DECODE direction only. Input is
whole words, so adding fragments to the encode tables would change the token ids
a prompt produces and break the identity gate for no benefit.
"""

# ---------------------------------------------------------------- GAP 1
# dutch -> english, same direction as SEED_NL. Closed-class, hand-checked.
SUPPLEMENT_NL = {
    "als": "if", "het": "it", "bij": "at", "door": "by", "uit": "out",
    "over": "about", "onder": "under", "tussen": "between", "tegen": "against",
    "zonder": "without", "binnen": "within", "sinds": "since",
    "tijdens": "during", "behalve": "except", "ondanks": "despite",
    "omdat": "because", "terwijl": "while", "hoewel": "although",
    "wanneer": "when", "welke": "which", "wiens": "whose", "deze": "these",
    "die": "those", "zulke": "such", "elke": "each", "ieder": "every",
    "beide": "both", "enkele": "some", "geen": "none", "alles": "all",
    "niets": "nothing", "iets": "something", "iemand": "someone",
    "niemand": "nobody", "overal": "everywhere", "ergens": "somewhere",
    "misschien": "maybe", "zeker": "certainly", "echter": "however",
    "daarom": "therefore", "dus": "so", "toch": "yet", "weer": "again",
    "nog": "still", "al": "already", "bijna": "almost", "genoeg": "enough",
    "minder": "less", "meer": "more", "meest": "most", "minst": "least",
    "zowel": "both", "noch": "nor", "indien": "provided",
    "moeten": "should", "kunnen": "could", "zouden": "would",
    "mag": "may", "zij": "they", "hen": "them", "jullie": "you",
    "mij": "me", "hem": "him", "zich": "himself", "zelf": "self",
    "wordt": "becomes", "werd": "became", "geweest": "been",
    "hebben": "have", "had": "had", "doen": "do", "deed": "did",
    "gedaan": "done", "maken": "make", "maakte": "made",
    "nemen": "take", "nam": "took", "geven": "give", "gaf": "gave",
    "zeggen": "say", "zei": "said", "weten": "know", "wist": "knew",
    "denken": "think", "dacht": "thought", "willen": "want",
    "vinden": "find", "vond": "found", "gebruiken": "use",
    "werken": "work", "spelen": "play", "lopen": "run", "rijden": "ride",
    "staan": "stand", "zitten": "sit", "liggen": "lie", "blijven": "stay",
}

# ---------------------------------------------------------------- GAP 2
# English suffix fragment -> Dutch suffix. DECODE DIRECTION ONLY.
# Regular correspondences; crude where English and Dutch morphology diverge,
# but a crude Dutch suffix beats an untranslated English one, and the effect on
# accuracy is measured rather than assumed.
SUFFIX_NL = {
    "ing": "end",      # running -> rennend
    "ed": "de",        # walked  -> liep/gelopen; `de` is the weak ending
    "tion": "tie",     # nation  -> natie
    "sion": "sie",     # version -> versie
    "ly": "lijk",      # quickly -> snel/lijk
    "ness": "heid",    # kindness -> vriendelijkheid
    "ment": "ment",    # identical in both
    "able": "baar",    # readable -> leesbaar
    "ible": "baar",
    "ful": "vol",      # helpful -> behulpzaam; `vol` for -ful as in hopeful
    "less": "loos",    # hopeless -> hopeloos
    "ity": "iteit",    # quality -> kwaliteit
    "ism": "isme",
    "ist": "ist",
    "ous": "eus",
    "ive": "ief",      # active -> actief
    "al": "aal",       # national -> nationaal
    "ic": "isch",      # historic -> historisch
    "er": "er",        # identical
    "est": "ste",      # biggest -> grootste
    "en": "en",
    "s": "s",
}


def is_language_neutral(decoded: str) -> bool:
    """True for tokens that are the same in both languages.

    A single letter used as a list marker - `A.`, `B.` - is as
    language-neutral as a digit. v8's purity metric counted them as
    untranslated fragments, which produced 83% of a measured 'gap' and a
    reported hard ceiling of 84.8% that was an artefact of this
    classification, not a property of the method.
    """
    b = decoded.strip()
    return len(b) <= 1
