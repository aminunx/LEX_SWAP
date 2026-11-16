"""The evaluation set in three languages: English, Dutch, Indonesian.

Dutch and Indonesian are the two arms of the controlled comparison, and they
differ in exactly the thing the first run identified as the wall.

  Dutch       Germanic. Verb second in main clauses, verb LAST in subordinate
              clauses, separable verbs split. Four forms of every verb.
  Indonesian  Austronesian, no relation to English or Germanic. SVO in every
              clause type, no verb conjugation at all - one form per verb.
              One systematic mismatch: adjectives follow the noun.

Four groups, each with a job.

`easy`        main clauses whose order matches English. Should work if the
              lexicon is any good.
`arithmetic`  numbers pass through the swap UNCHANGED, so these must match the
              English baseline exactly. The internal control: arithmetic
              surviving while facts fail puts the failure in the lexicon rather
              than the pipeline.
`word_order`  subordinate clauses. Dutch puts the verb last here and scored 0%
              in the first run. Indonesian keeps SVO. THIS GROUP IS THE WHOLE
              COMPARISON - if it rises for Indonesian, word order was the wall.
`adj_order`   Indonesian noun-adjective order, the one mismatch it does have.
              Isolates that cost instead of letting it blur into the rest.
"""

PROMPTS = [
    # ---------------------------------------------------------------- easy
    dict(id=1, group="easy",
         en="The capital of France is", exp_en="Paris",
         nl="De hoofdstad van Frankrijk is", exp_nl="Parijs",
         idn="Ibu kota Prancis adalah", exp_idn="Paris"),
    dict(id=2, group="easy",
         en="The capital of Germany is", exp_en="Berlin",
         nl="De hoofdstad van Duitsland is", exp_nl="Berlijn",
         idn="Ibu kota Jerman adalah", exp_idn="Berlin"),
    dict(id=3, group="easy",
         en="The largest planet is", exp_en="Jupiter",
         nl="De grootste planeet is", exp_nl="Jupiter",
         idn="Planet terbesar adalah", exp_idn="Jupiter"),
    dict(id=4, group="easy",
         en="The color of grass is", exp_en="green",
         nl="De kleur van gras is", exp_nl="groen",
         idn="Warna rumput adalah", exp_idn="hijau"),
    dict(id=5, group="easy",
         en="The opposite of hot is", exp_en="cold",
         nl="Het tegenovergestelde van heet is", exp_nl="koud",
         idn="Kebalikan dari panas adalah", exp_idn="dingin"),
    dict(id=6, group="easy",
         en="A dog has four", exp_en="legs",
         nl="Een hond heeft vier", exp_nl="poten",
         idn="Anjing memiliki empat", exp_idn="kaki"),
    dict(id=7, group="easy",
         en="The sun rises in the", exp_en="east",
         nl="De zon komt op in het", exp_nl="oosten",
         idn="Matahari terbit di", exp_idn="timur"),
    dict(id=8, group="easy",
         en="Water freezes at zero", exp_en="degrees",
         nl="Water bevriest bij nul", exp_nl="graden",
         idn="Air membeku pada nol", exp_idn="derajat"),
    dict(id=9, group="easy",
         en="The cat sat on the", exp_en="mat",
         nl="De kat zat op de", exp_nl="mat",
         idn="Kucing itu duduk di", exp_idn="lantai"),
    dict(id=10, group="easy",
         en="The book is on the", exp_en="table",
         nl="Het boek is op de", exp_nl="tafel",
         idn="Buku itu ada di", exp_idn="meja"),
    dict(id=11, group="easy",
         en="One two three four", exp_en="five",
         nl="Een twee drie vier", exp_nl="vijf",
         idn="Satu dua tiga empat", exp_idn="lima"),
    dict(id=12, group="easy",
         en="Red green blue and", exp_en="yellow",
         nl="Rood groen blauw en", exp_nl="geel",
         idn="Merah hijau biru dan", exp_idn="kuning"),

    # ---------------------------------------------------------- arithmetic
    # numbers are never substituted, so all three languages are identical
    dict(id=13, group="arithmetic", en="2 + 2 =", exp_en="4",
         nl="2 + 2 =", exp_nl="4", idn="2 + 2 =", exp_idn="4"),
    dict(id=14, group="arithmetic", en="10 - 3 =", exp_en="7",
         nl="10 - 3 =", exp_nl="7", idn="10 - 3 =", exp_idn="7"),
    dict(id=15, group="arithmetic", en="6 * 4 =", exp_en="24",
         nl="6 * 4 =", exp_nl="24", idn="6 * 4 =", exp_idn="24"),
    dict(id=16, group="arithmetic", en="100 / 4 =", exp_en="25",
         nl="100 / 4 =", exp_nl="25", idn="100 / 4 =", exp_idn="25"),

    # ---------------------------------------------------------- word_order
    # Dutch: verb last in the subordinate clause.  Indonesian: SVO throughout.
    # This group is the comparison. Dutch scored 0% here in the first run.
    dict(id=17, group="word_order",
         en="I know that he reads the", exp_en="book",
         nl="Ik weet dat hij het boek", exp_nl="leest",
         idn="Saya tahu bahwa dia membaca", exp_idn="buku"),
    dict(id=18, group="word_order",
         en="She said that the house is", exp_en="big",
         nl="Zij zei dat het huis groot", exp_nl="is",
         idn="Dia berkata bahwa rumah itu", exp_idn="besar"),
    dict(id=19, group="word_order",
         en="Because it was raining we stayed at", exp_en="home",
         nl="Omdat het regende bleven wij", exp_nl="thuis",
         idn="Karena hujan kami tinggal di", exp_idn="rumah"),
    dict(id=20, group="word_order",
         en="If you come tomorrow I will", exp_en="help",
         nl="Als je morgen komt zal ik", exp_nl="helpen",
         idn="Jika kamu datang besok saya akan", exp_idn="membantu"),
    dict(id=21, group="word_order",
         en="He wants to call", exp_en="you",
         nl="Hij wil je", exp_nl="opbellen",
         idn="Dia ingin menelepon", exp_idn="kamu"),
    dict(id=22, group="word_order",
         en="The man who lives there is", exp_en="old",
         nl="De man die daar woont is", exp_nl="oud",
         idn="Orang yang tinggal di sana adalah", exp_idn="tua"),
    dict(id=23, group="word_order",
         en="I have not yet read the", exp_en="letter",
         nl="Ik heb de brief nog niet", exp_nl="gelezen",
         idn="Saya belum membaca", exp_idn="surat"),
    dict(id=24, group="word_order",
         en="Yesterday I went to the", exp_en="city",
         nl="Gisteren ging ik naar de", exp_nl="stad",
         idn="Kemarin saya pergi ke", exp_idn="kota"),

    # ------------------------------------------------------------ adj_order
    # Indonesian puts the adjective AFTER the noun: `rumah besar` = house big.
    # English and Dutch both put it before. This group prices that one
    # mismatch on its own.
    dict(id=25, group="adj_order",
         en="A big house and a small", exp_en="house",
         nl="Een groot huis en een klein", exp_nl="huis",
         idn="Rumah besar dan rumah", exp_idn="kecil"),
    dict(id=26, group="adj_order",
         en="A red car and a blue", exp_en="car",
         nl="Een rode auto en een blauwe", exp_nl="auto",
         idn="Mobil merah dan mobil", exp_idn="biru"),
    dict(id=27, group="adj_order",
         en="A new book and an old", exp_en="book",
         nl="Een nieuw boek en een oud", exp_nl="boek",
         idn="Buku baru dan buku", exp_idn="lama"),
    dict(id=28, group="adj_order",
         en="Hot water and cold", exp_en="water",
         nl="Heet water en koud", exp_nl="water",
         idn="Air panas dan air", exp_idn="dingin"),
]

GROUPS = ["easy", "arithmetic", "word_order", "adj_order"]

LANGS = {
    "nl": dict(name="Dutch", family="Germanic", prompt="nl", expect="exp_nl",
               mt="Helsinki-NLP/opus-mt-en-nl", back="Helsinki-NLP/opus-mt-nl-en",
               note="verb last in subordinate clauses; four forms per verb"),
    "idn": dict(name="Indonesian", family="Austronesian", prompt="idn",
                expect="exp_idn",
                mt="Helsinki-NLP/opus-mt-en-id", back="Helsinki-NLP/opus-mt-id-en",
                note="SVO in every clause; no verb conjugation; adjective follows noun"),
}
