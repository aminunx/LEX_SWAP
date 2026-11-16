"""Natural Dutch — written as Dutch, not as English in Dutch words.

Everything measured so far used prompts constructed to be word-for-word
parallel with English. That was deliberate: it is the only way the identity
gate works, and it isolated the lexicon from word order so each could be fixed
separately. On that set the finished system reaches 100% input coverage, 99.6%
output purity and 64% accuracy against a 61% English ceiling.

But those prompts are English in Dutch clothing, and a system that only handles
them is not a Dutch model. This set is the honest test.

Every prompt below uses a construction that English does NOT share, so
word-for-word substitution produces broken English inside the model:

  verb-final subordinate clause   `dat hij het boek leest`  -> `that he the book reads`
  perfect tense with participle   `heb ... gelezen`         -> `have ... read` (split)
  inversion after a fronted item  `Gisteren ging ik`        -> `Yesterday went I`
  separable verb                  `wil je opbellen`         -> `want you call-up`

Expected answers are the correct Dutch continuation. A low score here is the
measured cost of keeping English syntax, and it is the number that must be
quoted alongside the parallel-set result - never instead of it.
"""

NATURAL_NL = [
    dict(id=1, nl="Ik weet dat hij het boek", exp="leest",
         why="verb-final subordinate clause"),
    dict(id=2, nl="Zij zei dat het huis groot", exp="is",
         why="verb-final subordinate clause"),
    dict(id=3, nl="Omdat het regende bleven wij", exp="thuis",
         why="inversion after a subordinate clause"),
    dict(id=4, nl="Als je morgen komt zal ik je", exp="helpen",
         why="inversion plus final infinitive"),
    dict(id=5, nl="Gisteren ging ik naar de", exp="stad",
         why="inversion after a fronted adverb"),
    dict(id=6, nl="De man die daar woont is", exp="oud",
         why="relative clause with verb final"),
    dict(id=7, nl="Ik heb de brief nog niet", exp="gelezen",
         why="perfect tense, participle last"),
    dict(id=8, nl="Hij wil je morgen", exp="opbellen",
         why="separable verb at the end"),
    dict(id=9, nl="Wij hebben gisteren een film", exp="gezien",
         why="perfect tense, participle last"),
    dict(id=10, nl="Het kind dat daar speelt is", exp="klein",
         why="relative clause with verb final"),
    dict(id=11, nl="Nadat hij was gekomen gingen wij", exp="weg",
         why="subordinate clause then inversion"),
    dict(id=12, nl="Zij heeft het boek al", exp="gelezen",
         why="perfect tense, participle last"),
    dict(id=13, nl="Morgen ga ik naar school omdat ik het", exp="moet",
         why="inversion plus verb-final clause"),
    dict(id=14, nl="Hoewel het koud was gingen wij", exp="zwemmen",
         why="concessive clause then inversion"),
    dict(id=15, nl="De vrouw aan wie ik het boek", exp="gaf",
         why="prepositional relative, verb final"),
    dict(id=16, nl="Ik denk dat zij morgen niet", exp="komt",
         why="verb-final with negation"),
    dict(id=17, nl="Toen wij aankwamen was het al", exp="donker",
         why="temporal clause then inversion"),
    dict(id=18, nl="Hij heeft mij gisteren niets", exp="gezegd",
         why="perfect tense, participle last"),
    dict(id=19, nl="Wat hij zei kon ik niet", exp="horen",
         why="fronted object clause then inversion"),
    dict(id=20, nl="Zij wonen in een huis dat heel", exp="oud",
         why="relative clause, adjective final"),
]


# ---------------------------------------------------------------------------
# Expansion: 20 prompts made one prompt worth 5%, which is wider than any
# effect the fixes produce. 30 more, same construction families, so a change of
# one or two items can no longer look like a trend.
#
# The original 20 are kept intact and scored separately, so the series stays
# comparable across every earlier run.
NATURAL_NL_EXTRA = [
    dict(id=21, nl="Ik hoop dat hij de deur", exp="opent",
         why="verb-final subordinate clause"),
    dict(id=22, nl="Hij zegt dat zij het lied", exp="zingt",
         why="verb-final subordinate clause"),
    dict(id=23, nl="Wij weten dat de man het geld", exp="heeft",
         why="verb-final subordinate clause"),
    dict(id=24, nl="Zij denkt dat het kind de bal", exp="gooit",
         why="verb-final subordinate clause"),
    dict(id=25, nl="Ik zie dat de vrouw de brief", exp="schrijft",
         why="verb-final subordinate clause"),
    dict(id=26, nl="Wij hebben vandaag het boek", exp="gelezen",
         why="perfect with object between"),
    dict(id=27, nl="Hij heeft gisteren de auto", exp="gekocht",
         why="perfect with object between"),
    dict(id=28, nl="Zij hebben vorige week het huis", exp="verkocht",
         why="perfect with object between"),
    dict(id=29, nl="Ik heb vanmorgen de krant", exp="gelezen",
         why="perfect with object between"),
    dict(id=30, nl="Wij hebben de film al", exp="gezien",
         why="perfect tense, participle last"),
    dict(id=31, nl="De vrouw die daar werkt is", exp="aardig",
         why="relative clause with verb final"),
    dict(id=32, nl="Het boek dat daar ligt is", exp="oud",
         why="relative clause with verb final"),
    dict(id=33, nl="De hond die daar loopt is", exp="groot",
         why="relative clause with verb final"),
    dict(id=34, nl="Het huis dat daar staat is", exp="nieuw",
         why="relative clause with verb final"),
    dict(id=35, nl="Morgen ga ik naar het", exp="werk",
         why="inversion after a fronted adverb"),
    dict(id=36, nl="Vandaag kocht zij een nieuwe", exp="auto",
         why="inversion after a fronted adverb"),
    dict(id=37, nl="Gisteren zag ik een grote", exp="hond",
         why="inversion after a fronted adverb"),
    dict(id=38, nl="Straks komt hij naar de", exp="stad",
         why="inversion after a fronted adverb"),
    dict(id=39, nl="Hij wil morgen de brief", exp="schrijven",
         why="modal with final infinitive"),
    dict(id=40, nl="Zij kan vandaag het lied", exp="zingen",
         why="modal with final infinitive"),
    dict(id=41, nl="Wij moeten straks het huis", exp="verkopen",
         why="modal with final infinitive"),
    dict(id=42, nl="Ik zal morgen de auto", exp="kopen",
         why="modal with final infinitive"),
    dict(id=43, nl="Hij mag nu het boek", exp="lezen",
         why="modal with final infinitive"),
    dict(id=44, nl="Omdat het regent blijft hij", exp="thuis",
         why="subordinate clause then inversion"),
    dict(id=45, nl="Hoewel zij ziek was ging zij naar het", exp="werk",
         why="concessive then inversion"),
    dict(id=46, nl="Toen hij kwam was ik al", exp="weg",
         why="temporal clause then inversion"),
    dict(id=47, nl="Als het regent nemen wij de", exp="trein",
         why="conditional then inversion"),
    dict(id=48, nl="Nadat zij at ging zij naar", exp="bed",
         why="temporal clause then inversion"),
    dict(id=49, nl="Ik denk dat de deur niet", exp="opent",
         why="verb-final with negation"),
    dict(id=50, nl="Wij hopen dat het weer niet", exp="verandert",
         why="verb-final with negation"),
]
