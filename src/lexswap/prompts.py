"""The evaluation set: 24 prompts in English and Dutch.

Three groups carry different jobs.

`easy`        - main-clause sentences whose word order matches English. These
                should work if the lexicon is any good at all.
`arithmetic`  - numbers pass through the swap UNCHANGED, so these must match
                the English baseline exactly. They are the internal control: if
                arithmetic survives while facts fail, the failure is in the
                lexicon and not in the pipeline.
`word_order`  - Dutch subordinate clauses put the verb last, and separable
                verbs split. Word-for-word substitution turns these into broken
                English. Pre-registered as the expected failure group; a
                failure here is a confirmation, not a surprise.
"""

PROMPTS = [
    # ---------------------------------------------------------------- easy
    dict(id=1, group="easy", en="The capital of France is",
         nl="De hoofdstad van Frankrijk is", exp_en="Paris", exp_nl="Parijs"),
    dict(id=2, group="easy", en="The capital of Germany is",
         nl="De hoofdstad van Duitsland is", exp_en="Berlin", exp_nl="Berlijn"),
    dict(id=3, group="easy", en="The largest planet is",
         nl="De grootste planeet is", exp_en="Jupiter", exp_nl="Jupiter"),
    dict(id=4, group="easy", en="The color of grass is",
         nl="De kleur van gras is", exp_en="green", exp_nl="groen"),
    dict(id=5, group="easy", en="The opposite of hot is",
         nl="Het tegenovergestelde van heet is", exp_en="cold", exp_nl="koud"),
    dict(id=6, group="easy", en="A dog has four",
         nl="Een hond heeft vier", exp_en="legs", exp_nl="benen"),
    dict(id=7, group="easy", en="The sun rises in the",
         nl="De zon komt op in het", exp_en="east", exp_nl="oosten"),
    dict(id=8, group="easy", en="Water freezes at zero",
         nl="Water bevriest bij nul", exp_en="degrees", exp_nl="graden"),
    dict(id=9, group="easy", en="The cat sat on the",
         nl="De kat zat op de", exp_en="floor", exp_nl="vloer"),
    dict(id=10, group="easy", en="The book is on the",
         nl="Het boek is op de", exp_en="table", exp_nl="tafel"),
    dict(id=11, group="easy", en="One two three four",
         nl="Een twee drie vier", exp_en="five", exp_nl="vijf"),
    dict(id=12, group="easy", en="Red green blue and",
         nl="Rood groen blauw en", exp_en="yellow", exp_nl="geel"),

    # ---------------------------------------------------------- arithmetic
    # numbers are never substituted, so these must match English exactly
    dict(id=13, group="arithmetic", en="2 + 2 =", nl="2 + 2 =",
         exp_en="4", exp_nl="4"),
    dict(id=14, group="arithmetic", en="10 - 3 =", nl="10 - 3 =",
         exp_en="7", exp_nl="7"),
    dict(id=15, group="arithmetic", en="6 * 4 =", nl="6 * 4 =",
         exp_en="24", exp_nl="24"),
    dict(id=16, group="arithmetic", en="100 / 4 =", nl="100 / 4 =",
         exp_en="25", exp_nl="25"),

    # ---------------------------------------------------------- word_order
    # Dutch puts the verb last in subordinate clauses; separable verbs split
    dict(id=17, group="word_order", en="I know that he reads the",
         nl="Ik weet dat hij het boek", exp_en="book", exp_nl="leest"),
    dict(id=18, group="word_order", en="She said that the house is",
         nl="Zij zei dat het huis groot", exp_en="big", exp_nl="is"),
    dict(id=19, group="word_order", en="Because it was raining we",
         nl="Omdat het regende bleven", exp_en="stayed", exp_nl="wij"),
    dict(id=20, group="word_order", en="If you come tomorrow I will",
         nl="Als je morgen komt zal ik", exp_en="help", exp_nl="helpen"),
    dict(id=21, group="word_order", en="He wants to call you",
         nl="Hij wil je", exp_en="up", exp_nl="opbellen"),
    dict(id=22, group="word_order", en="The man who lives there is",
         nl="De man die daar woont is", exp_en="old", exp_nl="oud"),
    dict(id=23, group="word_order", en="I have the letter not yet",
         nl="Ik heb de brief nog niet", exp_en="read", exp_nl="gelezen"),
    dict(id=24, group="word_order", en="Yesterday went I to the",
         nl="Gisteren ging ik naar de", exp_en="city", exp_nl="stad"),
]

GROUPS = ["easy", "arithmetic", "word_order"]
