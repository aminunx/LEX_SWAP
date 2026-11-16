"""The syntax layer — the thing the lexicon could never be.

Natural Dutch scored 10% accuracy at 94% output purity. The words came out
Dutch and the reasoning was broken, because the model internally received
English word order. No dictionary entry can fix that: word order is not
lexical.

So the answer to "what can the procedure not express" is, this time, that there
was no syntactic procedure at all. Substitution replaces words and leaves them
where they sat.

    Dutch (natural) -> REORDER to English order -> lexical map -> ids -> MODEL

Still no training, still no weight edits. A bigger pre-processor, not a
different model.

## The obstacle, and why generation cannot solve it

Reordering an INCOMPLETE sentence moves the predicted word.

    Ik weet dat hij het boek ___        expects `leest`
    I know that he ___ the book         the verb sits BEFORE the object

Left-to-right generation cannot reach a slot that is not at the end. Feeding
`I know that he` and generating gives a verb, but throws away `het boek` -
exactly the evidence that makes `reads` more likely than `is`.

## So: score candidates in a slot, do not generate

Build the English-order template WITH the object in place, put each candidate
into the hole, and score the whole sequence. The highest-scoring candidate is
the answer. This uses the unchanged model as a scorer rather than a generator,
which is the one way to query a non-final position.

Each rule below returns `(prefix, suffix)` in English order, in DUTCH words -
the existing lexical map turns them into source ids afterwards, so the syntax
layer and the lexicon stay independent and separately testable.
"""

SUBORDINATORS = {
    "dat", "die", "wie", "welke", "wat", "omdat", "hoewel", "toen",
    "nadat", "voordat", "terwijl", "als", "of", "zodat", "doordat",
}
PERFECT_AUX = {"heb", "hebt", "heeft", "hebben", "had", "hadden",
               "ben", "bent", "is", "zijn", "was", "waren"}
MODALS = {"wil", "wilt", "willen", "kan", "kunt", "kunnen", "moet",
          "moeten", "zal", "zult", "zullen", "mag", "mogen", "ga", "gaat",
          "gaan", "kon", "wou", "zou", "zouden"}
FRONTED = {"gisteren", "morgen", "vandaag", "toen", "nu", "later", "straks",
           "daarna", "eerst", "soms", "altijd", "nooit", "hier", "daar",
           "nadat", "hoewel", "omdat", "als", "wat", "terwijl"}
PRONOUNS = {"ik", "hij", "zij", "wij", "jij", "je", "u", "het", "ze",
            "we", "men", "men"}
NEGATION = {"niet", "niets", "nooit", "geen", "nog"}
TO_INF = "te"


def _split(text):
    return [w for w in text.strip().split(" ") if w]


def reorder(text):
    """Dutch prompt -> (prefix, suffix, slot_kind) in English order.

    `slot_kind` says what grammatical category belongs in the hole, which the
    caller uses to restrict candidates. Returns None when no rule applies, and
    the caller then falls back to plain left-to-right generation - so this can
    only ever add correct answers, never remove one.
    """
    w = _split(text)
    if len(w) < 3:
        return None
    low = [x.lower() for x in w]

    # R1 - verb-final subordinate clause.
    #   Ik weet dat hij het boek ___   ->  Ik weet dat hij ___ het boek
    # The subordinator is followed by a subject and then an object, with no
    # finite verb between them, so the hole is the verb and in English order it
    # sits immediately after the subject.
    for i, x in enumerate(low):
        if x in SUBORDINATORS and i + 2 < len(w):
            rest = low[i + 1:]
            if not any(r in PERFECT_AUX or r in MODALS for r in rest):
                subj_end = i + 2
                if rest[0] in PRONOUNS or (len(rest) > 1 and rest[0] in
                                           {"de", "het", "een"}):
                    if rest[0] in {"de", "het", "een"}:
                        subj_end = i + 3
                    if subj_end < len(w):
                        return (w[:subj_end], w[subj_end:], "verb")

    # R2b - perfect tense with an object or adverbial between aux and
    # participle, and NO negation.
    #   Wij hebben gisteren een film ___  ->  Wij hebben ___ gisteren een film
    # R2 below required a negation or `al` in the tail, so this whole family
    # fell through untouched - 3 of the 5 unmatched prompts in v14.
    for i, x in enumerate(low):
        if x in PERFECT_AUX and i + 1 < len(w) and i > 0:
            if low[i - 1] in PRONOUNS or i == 1:
                tail = low[i + 1:]
                if not any(t_ in PERFECT_AUX or t_ in MODALS for t_ in tail):
                    return (w[:i + 1], w[i + 1:], "participle")

    # R5 - relative clause with the verb last.
    #   De man die daar woont is ___  ->  De man die woont daar is ___
    # English puts the verb straight after the relative pronoun; Dutch puts it
    # at the end of the clause. The slot itself stays final, so the caller can
    # generate normally - the swap only makes the English grammatical.
    REL = {"die", "dat", "wie", "welke"}
    for i, x in enumerate(low):
        if x in REL and i + 2 < len(w):
            # look for  REL  <adverbial>  <verb>  ...
            for j in range(i + 2, min(i + 4, len(w))):
                if low[j].endswith(("t", "en")) and low[j] not in REL:
                    mid_part = w[i + 1:j]
                    if mid_part and all(m.lower() not in PERFECT_AUX
                                        for m in mid_part):
                        return (w[:i + 1] + [w[j]] + mid_part + w[j + 1:],
                                [], "final")
            break

    # R2 - perfect tense, participle last.
    #   Ik heb de brief nog niet ___   ->  Ik heb ___ de brief nog niet
    for i, x in enumerate(low):
        if x in PERFECT_AUX and i + 1 < len(w):
            tail = low[i + 1:]
            if any(t in NEGATION for t in tail) or low[-1] in NEGATION \
                    or low[-1] in {"al", "even", "ooit"}:
                return (w[:i + 1], w[i + 1:], "participle")

    # R3 - modal with a final infinitive.
    #   Hij wil je morgen ___   ->  Hij wil te ___ je morgen
    for i, x in enumerate(low):
        if x in MODALS and i + 1 < len(w):
            return (w[:i + 1] + [TO_INF], w[i + 1:], "infinitive")

    # R4 - inversion after a fronted element.
    #   Gisteren ging ik naar de ___   ->  Gisteren ik ging naar de ___
    # The hole stays final here, so only the subject and verb swap and the
    # caller can generate normally - but the swap is what makes the English
    # the model sees grammatical.
    if low[0] in FRONTED and len(w) >= 3:
        if low[2] in PRONOUNS and low[1] not in PRONOUNS:
            return ([w[0], w[2], w[1]] + w[3:], [], "final")

    return None


def build_candidates(slot_kind, lexicon_nl_words, limit=400, subject=None):
    """Restrict the candidate set by the category the slot wants.

    Scoring every word in a 24,000-entry lexicon per prompt is wasteful and
    noisy. Dutch verb and participle shapes are regular enough to filter on.
    """
    # `een` ends in -en and would pass the infinitive test; `de`, `het`, `te`
    # and friends pass the verb test. The commonest words in the language beat
    # any real verb on probability, so they must be excluded by name.
    STOP = {"een", "de", "het", "te", "en", "die", "dat", "dit", "deze",
            "van", "in", "op", "aan", "met", "voor", "naar", "om", "bij",
            "als", "of", "ook", "niet", "nog", "maar", "zijn", "er", "ze",
            "we", "je", "ik", "hij", "wij", "men", "u", "me", "mij"}
    # Dutch and English do not divide the verb forms the same way: English
    # `read` covers present and past, so ' read' outscores ' reads' and the
    # Dutch infinitive `lezen` wins a slot Dutch grammar reserves for `leest`.
    # Fixing it in the encoder is not enough - the CANDIDATE SET has to respect
    # the agreement too.
    from .agreement_nl import NON_THIRD
    third = subject is not None and subject.lower() not in NON_THIRD
    out = []
    for word in lexicon_nl_words:
        lw = word.strip().lower()
        if len(lw) < 2 or not lw.isalpha() or lw in STOP:
            continue
        if slot_kind == "verb" and subject is not None:
            # finite verb: third singular ends in -t, plural/first in -en
            if third and not lw.endswith("t"):
                continue
            if not third and lw.endswith("t"):
                continue
        if slot_kind == "participle":
            # Dutch past participles almost all carry the ge- prefix, or end
            # in -d/-t for weak verbs with an inseparable prefix. The old test
            # also admitted every infinitive via -en, which is why `lezen`
            # kept winning slots that belong to `gelezen`.
            if lw.startswith("ge") or (lw.endswith(("d", "t"))
                                       and not lw.endswith("en")):
                out.append(word)
        elif slot_kind == "infinitive":
            # infinitives end in -en and never carry ge-
            if lw.endswith("en") and not lw.startswith("ge"):
                out.append(word)
        elif slot_kind == "verb":
            if lw.endswith(("t", "en", "de", "te")) or lw in {
                    "is", "was", "heeft", "had", "kan", "wil", "moet", "zal"}:
                out.append(word)
        else:
            out.append(word)
        if len(out) >= limit * 8:
            break
    return out[: limit * 8]
