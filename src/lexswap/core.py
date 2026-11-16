"""Vocabulary swap: relabel a model's token table into another language.

The model's weights are never touched. Only the ID <-> string table changes,
so token 567 that used to render as " the" renders as " de" instead.

Nothing here edits the BPE merges file. The merges were learned on English and
would not segment Dutch correctly, so substitution happens at the WORD level,
before tokenisation, which is mathematically the same thing and far simpler.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

WORD_RE = re.compile(r"^[A-Za-z]+$")
TOKEN_SPLIT = re.compile(r"(\s+)")


@dataclass
class SwapTable:
    """The relabelled vocabulary.

    id2tgt  : token id -> target-language string (or the original string)
    tgt2id  : target string -> token id, first occurrence wins
    """

    id2tgt: dict[int, str] = field(default_factory=dict)
    tgt2id: dict[str, int] = field(default_factory=dict)
    kept: list[int] = field(default_factory=list)          # left unchanged
    fragments: list[int] = field(default_factory=list)     # sub-word pieces
    collisions: dict[str, list[int]] = field(default_factory=dict)

    @property
    def stats(self) -> dict:
        n_coll_ids = sum(len(v) - 1 for v in self.collisions.values())
        return {
            "translated": len(self.id2tgt) - len(self.kept),
            "kept_unchanged": len(self.kept),
            "subword_fragments": len(self.fragments),
            "colliding_strings": len(self.collisions),
            "ids_lost_to_collision": n_coll_ids,
            "vocab_covered": len(self.id2tgt),
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"id2tgt": {str(k): v for k, v in self.id2tgt.items()},
                       "kept": self.kept, "fragments": self.fragments,
                       "collisions": {k: v for k, v in self.collisions.items()},
                       "stats": self.stats}, f, ensure_ascii=False, indent=2)


def classify(s: str) -> str:
    """whole_word | fragment | keep

    A leading space marks a word start in byte-level BPE, so " book" is a whole
    word and "ing" is a fragment. Digits, punctuation, code and special tokens
    are kept unchanged - the spec requires it, and it also gives arithmetic as
    an internal control, since numbers pass through untouched.
    """
    if not s:
        return "keep"
    body = s.lstrip(" ")
    if not WORD_RE.match(body):
        return "keep"
    return "whole_word" if s.startswith(" ") or s[0].isupper() else "fragment"


def build_table(tokenizer, translate, n: int = 30_000,
                batch: int = 64) -> SwapTable:
    """Build the swap table over the first `n` ids.

    `translate` takes a list of English words and returns the same number of
    target-language words. It is injected rather than imported so the same code
    can run against a machine-translation model, a bilingual lexicon, or the
    shuffled control.
    """
    t = SwapTable()
    todo: list[tuple[int, str, str]] = []   # (id, original, bare word)

    for i in range(min(n, len(tokenizer))):
        s = tokenizer.decode([i])
        kind = classify(s)
        if kind == "whole_word":
            todo.append((i, s, s.lstrip(" ")))
        else:
            t.id2tgt[i] = s
            t.kept.append(i)
            if kind == "fragment":
                t.fragments.append(i)

    for k in range(0, len(todo), batch):
        chunk = todo[k:k + batch]
        out = translate([w for _, _, w in chunk])
        for (i, orig, _), tr in zip(chunk, out):
            tr = (tr or "").strip().split()
            # a one-word source must map to a one-word target, or the word-level
            # codec breaks; multi-word output is dropped and the id is kept
            if len(tr) != 1 or not WORD_RE.match(tr[0]):
                t.id2tgt[i] = orig
                t.kept.append(i)
                continue
            t.id2tgt[i] = (" " if orig.startswith(" ") else "") + tr[0]

    for i, s in t.id2tgt.items():
        key = s.lstrip(" ").lower()
        if not key:
            continue
        t.collisions.setdefault(key, []).append(i)
    t.collisions = {k: v for k, v in t.collisions.items() if len(v) > 1}

    # first occurrence wins, matching the spec
    for i in sorted(t.id2tgt):
        key = t.id2tgt[i]
        if key not in t.tgt2id:
            t.tgt2id[key] = i
    return t


class SwapCodec:
    """Word-level encode/decode through the swap table.

    Unknown target words fall back to the original tokenizer. That fallback
    mixes two regimes in one sequence - relabelled English embeddings next to
    the model's own native target-language embeddings - so `last_coverage`
    reports the proportion, and no result should be read without it.
    """

    def __init__(self, tokenizer, table: SwapTable):
        self.tok = tokenizer
        self.table = table
        self.last_coverage: dict = {}

    def encode(self, text: str) -> list[int]:
        ids, hit, miss = [], 0, 0
        first = True
        for word in text.split(" "):
            if not word:
                continue
            key = word if first else " " + word
            first = False
            got = self.table.tgt2id.get(key)
            if got is None:
                got = self.table.tgt2id.get(key.lower())
            if got is None:
                got = self.table.tgt2id.get(key[0].upper() + key[1:]
                                            if len(key) > 1 else key)
            if got is not None:
                ids.append(got)
                hit += 1
            else:
                ids.extend(self.tok.encode(key, add_special_tokens=False))
                miss += 1
        total = hit + miss
        self.last_coverage = {
            "words": total, "swapped": hit, "fallback": miss,
            "coverage": round(hit / total, 3) if total else 0.0}
        return ids

    def decode(self, ids: list[int]) -> str:
        return "".join(self.table.id2tgt.get(int(i), self.tok.decode([int(i)]))
                       for i in ids)
