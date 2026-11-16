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
