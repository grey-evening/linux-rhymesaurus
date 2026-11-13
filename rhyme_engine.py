#!/usr/bin/env python3

import re
import sqlite3
from collections import defaultdict
from pathlib import Path


DB_PATH = Path(__file__).with_name("rhymesaurus.sqlite3")

FREQUENCY_CATEGORIES = (1, 2, 5, 9, 10)

RHYME_TYPES = (
    "perfect",
    "light",
    "final_syllable",
    "first_syllable",
    "first_syllable_assonance",
    "back",
    "reverse",
    "reverse_first_syllable",
    "homophones",
    "consonance",
    "double_consonance",
    "full_consonance",
    "assonance",
    "full_assonance",
    "full_assonance_end_consonant",
    "sight",
    "half_double",
    "amphisbaenic",
    "elided",
    "begins_with",
    "ends_with",
    "contains",
)


class WordNotFoundError(Exception):
    """The requested word has no entry in the pronunciation database."""


class NoUsablePronunciationError(Exception):
    """The word exists, but no usable rhyme key could be extracted."""


def rhyme_key(reversed_phonemes):
    """Return reversed phonemes through the primary-stressed vowel."""
    tokens = reversed_phonemes.split()
    key = []

    for token in tokens:
        key.append(token)
        if token.endswith("1"):
            return tuple(key)

    return None


def final_rhyme_key(reversed_phonemes):
    """Return the final vowel and following consonants."""
    if not reversed_phonemes:
        return None

    key = []

    for token in reversed_phonemes.split():
        key.append(token.rstrip("012"))

        if token.endswith(("0", "1", "2")):
            return tuple(key)

    return None


def ensure_final_rhyme_keys(db):
    """Create and populate the indexed final-rhyme table if necessary."""

    db.execute("""
        CREATE TABLE IF NOT EXISTS FINAL_RHYME_KEYS (
            WORDID INTEGER PRIMARY KEY,
            WORD TEXT NOT NULL,
            FINAL_RHYME_KEY TEXT NOT NULL,
            FREQUENCY INTEGER,
            PHONEMES TEXT,
            STRESSEDSYLLABLE INTEGER,
            SYLLABLECOUNT INTEGER
        )
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS IDX_FINAL_RHYME_KEY
        ON FINAL_RHYME_KEYS (FINAL_RHYME_KEY)
    """)

    count = db.execute(
        "SELECT COUNT(*) FROM FINAL_RHYME_KEYS"
    ).fetchone()[0]

    if count:
        return

    source_rows = db.execute("""
        SELECT
            WORDID, WORD, REVERSEPHONEMES, FREQUENCY,
            PHONEMES, STRESSEDSYLLABLE, SYLLABLECOUNT
        FROM RHYMES
    """).fetchall()

    entries = []

    for row in source_rows:
        key = final_rhyme_key(row["REVERSEPHONEMES"])

        if key is None:
            continue

        entries.append((
            row["WORDID"],
            row["WORD"],
            " ".join(key),
            row["FREQUENCY"],
            row["PHONEMES"],
            row["STRESSEDSYLLABLE"],
            row["SYLLABLECOUNT"],
        ))

    db.executemany("""
        INSERT INTO FINAL_RHYME_KEYS (
            WORDID, WORD, FINAL_RHYME_KEY, FREQUENCY,
            PHONEMES, STRESSEDSYLLABLE, SYLLABLECOUNT
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, entries)

    db.commit()

    print(
        f"Built FINAL_RHYME_KEYS: {len(entries):,} pronunciation records."
    )


def back_rhyme_key(phonemes, stressed_syllable):
    """Return the sound from the stressed-syllable onset to the final vowel.

    STRESSEDSYLLABLE is counted backward from the end: 1 is the final
    syllable, 2 the penultimate, and so on.
    """
    if not phonemes or stressed_syllable is None:
        return None

    tokens = phonemes.split()
    vowel_indexes = [
        index for index, token in enumerate(tokens)
        if token.endswith(("0", "1", "2"))
    ]

    if not vowel_indexes:
        return None

    if not 1 <= stressed_syllable <= len(vowel_indexes):
        return None

    stressed_index = vowel_indexes[len(vowel_indexes) - stressed_syllable]
    earlier_vowels = [index for index in vowel_indexes if index < stressed_index]
    start = earlier_vowels[-1] + 1 if earlier_vowels else 0
    return tuple(tokens[start:vowel_indexes[-1] + 1]) or None


def ensure_back_rhyme_keys(db):
    """Create and populate the indexed Back-rhyme table if necessary."""

    db.execute("""
        CREATE TABLE IF NOT EXISTS BACK_RHYME_KEYS (
            WORDID INTEGER PRIMARY KEY,
            WORD TEXT NOT NULL,
            BACK_RHYME_KEY TEXT NOT NULL,
            FREQUENCY INTEGER,
            PHONEMES TEXT,
            STRESSEDSYLLABLE INTEGER,
            SYLLABLECOUNT INTEGER
        )
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS IDX_BACK_RHYME_KEY
        ON BACK_RHYME_KEYS (BACK_RHYME_KEY)
    """)

    count = db.execute(
        "SELECT COUNT(*) FROM BACK_RHYME_KEYS"
    ).fetchone()[0]

    if count:
        return

    source_rows = db.execute("""
        SELECT WORDID, WORD, PHONEMES, FREQUENCY,
               STRESSEDSYLLABLE, SYLLABLECOUNT
        FROM RHYMES
        WHERE PHONEMES IS NOT NULL
          AND STRESSEDSYLLABLE IS NOT NULL
          AND SYLLABLECOUNT > 0
    """).fetchall()

    entries = []
    for row in source_rows:
        key = back_rhyme_key(row["PHONEMES"], row["STRESSEDSYLLABLE"])
        if key is None:
            continue
        entries.append((
            row["WORDID"], row["WORD"], " ".join(key),
            row["FREQUENCY"], row["PHONEMES"],
            row["STRESSEDSYLLABLE"], row["SYLLABLECOUNT"],
        ))

    db.executemany("""
        INSERT INTO BACK_RHYME_KEYS (
            WORDID, WORD, BACK_RHYME_KEY, FREQUENCY, PHONEMES,
            STRESSEDSYLLABLE, SYLLABLECOUNT
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, entries)
    db.commit()
    print(f"Built BACK_RHYME_KEYS: {len(entries):,} pronunciation records.")



def ensure_homophone_keys(db):
    """Create and populate an indexed table of complete pronunciations."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS HOMOPHONE_KEYS (
            WORDID INTEGER PRIMARY KEY,
            WORD TEXT NOT NULL,
            PHONEMES TEXT NOT NULL,
            FREQUENCY INTEGER,
            SYLLABLECOUNT INTEGER
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS IDX_HOMOPHONE_PHONEMES
        ON HOMOPHONE_KEYS (PHONEMES)
    """)

    count = db.execute(
        "SELECT COUNT(*) FROM HOMOPHONE_KEYS"
    ).fetchone()[0]
    if count:
        return

    source_rows = db.execute("""
        SELECT WORDID, WORD, PHONEMES, FREQUENCY, SYLLABLECOUNT
        FROM RHYMES
        WHERE PHONEMES IS NOT NULL
          AND SYLLABLECOUNT > 0
    """).fetchall()

    entries = [
        (row["WORDID"], row["WORD"], row["PHONEMES"],
         row["FREQUENCY"], row["SYLLABLECOUNT"])
        for row in source_rows
    ]

    db.executemany("""
        INSERT INTO HOMOPHONE_KEYS
            (WORDID, WORD, PHONEMES, FREQUENCY, SYLLABLECOUNT)
        VALUES (?, ?, ?, ?, ?)
    """, entries)
    db.commit()
    print(f"Built HOMOPHONE_KEYS: {len(entries):,} pronunciation records.")


def fetch_homophone_matches(db, source_keys, word, max_frequency=None):
    """Fetch words with an exactly matching complete pronunciation."""
    if not source_keys:
        return []

    placeholders = ",".join("?" for _ in source_keys)
    sql = f"""
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM HOMOPHONE_KEYS
        WHERE PHONEMES IN ({placeholders})
          AND WORD <> ? COLLATE NOCASE
          AND SYLLABLECOUNT > 0
    """
    parameters = sorted(source_keys) + [word]

    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(max_frequency)

    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, parameters).fetchall()



# ARPAbet vowel phoneme bases. Consonance uses only the final consonant.
VOWEL_PHONEMES = {
    "AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER",
    "EY", "IH", "IY", "OW", "OY", "UH", "UW",
}


def assonance_key(phonemes):
    """Return the final vowel phoneme, retaining its stress digit."""
    if not phonemes:
        return None

    for token in reversed(phonemes.split()):
        match = re.fullmatch(r"([A-Z]+)([012])", token)
        if match and match.group(1) in VOWEL_PHONEMES:
            return token

    return None


def full_assonance_key(phonemes):
    """Return the complete ordered vowel pattern, ignoring stress."""
    if not phonemes:
        return None

    vowels = []
    for token in phonemes.split():
        match = re.fullmatch(r"([A-Z]+)([012])", token)
        if match and match.group(1) in VOWEL_PHONEMES:
            vowels.append(match.group(1))

    return tuple(vowels) if vowels else None


def ensure_full_assonance_keys(db):
    """Create and populate an index of complete vowel patterns."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS FULL_ASSONANCE_KEYS (
            WORDID INTEGER PRIMARY KEY,
            WORD TEXT NOT NULL,
            FULL_ASSONANCE_KEY TEXT NOT NULL,
            FREQUENCY INTEGER,
            PHONEMES TEXT,
            SYLLABLECOUNT INTEGER
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS IDX_FULL_ASSONANCE_KEY
        ON FULL_ASSONANCE_KEYS (FULL_ASSONANCE_KEY)
    """)

    count = db.execute(
        "SELECT COUNT(*) FROM FULL_ASSONANCE_KEYS"
    ).fetchone()[0]
    if count:
        return

    source_rows = db.execute("""
        SELECT WORDID, WORD, PHONEMES, FREQUENCY, SYLLABLECOUNT
        FROM RHYMES
        WHERE PHONEMES IS NOT NULL
          AND SYLLABLECOUNT > 0
    """).fetchall()

    entries = []
    skipped = 0
    for row in source_rows:
        key = full_assonance_key(row["PHONEMES"])
        if key is None:
            skipped += 1
            continue
        entries.append((
            row["WORDID"], row["WORD"], " ".join(key),
            row["FREQUENCY"], row["PHONEMES"], row["SYLLABLECOUNT"],
        ))

    db.executemany("""
        INSERT INTO FULL_ASSONANCE_KEYS (
            WORDID, WORD, FULL_ASSONANCE_KEY, FREQUENCY,
            PHONEMES, SYLLABLECOUNT
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, entries)
    db.commit()
    print(
        f"Built FULL_ASSONANCE_KEYS: {len(entries):,} pronunciation records "
        f"({skipped:,} excluded)."
    )


def fetch_full_assonance_matches(
    db, source_keys, word, max_frequency=None
):
    """Fetch words sharing any complete ordered vowel pattern."""
    if not source_keys:
        return []

    placeholders = ",".join("?" for _ in source_keys)
    sql = f"""
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM FULL_ASSONANCE_KEYS
        WHERE FULL_ASSONANCE_KEY IN ({placeholders})
          AND WORD <> ? COLLATE NOCASE
          AND SYLLABLECOUNT > 0
    """
    parameters = sorted(" ".join(key) for key in source_keys) + [word]

    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(max_frequency)

    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, parameters).fetchall()


def full_assonance_end_consonant_key(phonemes):
    """Return the ordered vowel pattern plus the final consonant phoneme.

    Vowel stress is ignored, as in Full Assonance. Pronunciations that end
    in a vowel have no end-consonant key and are excluded.
    """
    if not phonemes:
        return None

    vowels = []
    final_consonant = None

    for token in phonemes.split():
        match = re.fullmatch(r"([A-Z]+)([012])", token)
        if match and match.group(1) in VOWEL_PHONEMES:
            vowels.append(match.group(1))
        else:
            base = re.sub(r"[012]+$", "", token)
            if not re.fullmatch(r"[A-Z]+", base):
                return None
            final_consonant = base

    if not vowels or final_consonant is None:
        return None

    return tuple(vowels), final_consonant


def ensure_full_assonance_end_consonant_keys(db):
    """Create and populate an index of vowel-pattern/final-consonant keys."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS FULL_ASSONANCE_END_CONSONANT_KEYS (
            WORDID INTEGER PRIMARY KEY,
            WORD TEXT NOT NULL,
            MATCH_KEY TEXT NOT NULL,
            FREQUENCY INTEGER,
            PHONEMES TEXT,
            SYLLABLECOUNT INTEGER
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS IDX_FULL_ASSONANCE_END_CONSONANT_KEY
        ON FULL_ASSONANCE_END_CONSONANT_KEYS (MATCH_KEY)
    """)

    count = db.execute(
        "SELECT COUNT(*) FROM FULL_ASSONANCE_END_CONSONANT_KEYS"
    ).fetchone()[0]
    if count:
        return

    source_rows = db.execute("""
        SELECT WORDID, WORD, PHONEMES, FREQUENCY, SYLLABLECOUNT
        FROM RHYMES
        WHERE PHONEMES IS NOT NULL AND SYLLABLECOUNT > 0
    """).fetchall()

    entries = []
    skipped = 0
    for row in source_rows:
        key = full_assonance_end_consonant_key(row["PHONEMES"])
        if key is None:
            skipped += 1
            continue
        vowels, final_consonant = key
        entries.append((
            row["WORDID"], row["WORD"],
            " ".join(vowels) + " | " + final_consonant,
            row["FREQUENCY"], row["PHONEMES"], row["SYLLABLECOUNT"],
        ))

    db.executemany("""
        INSERT INTO FULL_ASSONANCE_END_CONSONANT_KEYS (
            WORDID, WORD, MATCH_KEY, FREQUENCY, PHONEMES, SYLLABLECOUNT
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, entries)
    db.commit()
    print(
        "Built FULL_ASSONANCE_END_CONSONANT_KEYS: "
        f"{len(entries):,} pronunciation records ({skipped:,} excluded)."
    )


def fetch_full_assonance_end_consonant_matches(
    db, source_keys, word, max_frequency=None
):
    """Fetch matching vowel-pattern/final-consonant pronunciations."""
    if not source_keys:
        return []

    match_keys = sorted(
        " ".join(vowels) + " | " + final_consonant
        for vowels, final_consonant in source_keys
    )
    placeholders = ",".join("?" for _ in match_keys)
    sql = f"""
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM FULL_ASSONANCE_END_CONSONANT_KEYS
        WHERE MATCH_KEY IN ({placeholders})
          AND WORD <> ? COLLATE NOCASE
          AND SYLLABLECOUNT > 0
    """
    parameters = match_keys + [word]

    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(max_frequency)

    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, parameters).fetchall()



def half_double_syllable_key(phonemes, stressed_position):
    """Return the primary-stressed syllable (vowel plus coda).

    stressed_position is counted from the end: 1 = final, 2 = penultimate.
    The stressed vowel's digit is retained; onset consonants are omitted.
    """
    if not phonemes or stressed_position not in (1, 2):
        return None

    tokens = phonemes.split()
    vowel_positions = []
    for index, token in enumerate(tokens):
        match = re.fullmatch(r"([A-Z]+)([012])", token)
        if match and match.group(1) in VOWEL_PHONEMES:
            vowel_positions.append(index)

    if len(vowel_positions) < stressed_position:
        return None

    vowel_index = vowel_positions[-stressed_position]
    vowel_token = tokens[vowel_index]
    if not vowel_token.endswith("1"):
        return None

    syllable = [vowel_token]
    for token in tokens[vowel_index + 1:]:
        match = re.fullmatch(r"([A-Z]+)([012])", token)
        if match and match.group(1) in VOWEL_PHONEMES:
            break
        syllable.append(re.sub(r"[012]+$", "", token))

    return tuple(syllable)


def ensure_half_double_keys(db):
    """Build indexed final/penultimate stressed-syllable keys."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS HALF_DOUBLE_KEYS (
            WORDID INTEGER PRIMARY KEY,
            WORD TEXT NOT NULL,
            SIDE TEXT NOT NULL,
            MATCH_KEY TEXT NOT NULL,
            FREQUENCY INTEGER,
            PHONEMES TEXT,
            SYLLABLECOUNT INTEGER
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS IDX_HALF_DOUBLE_MATCH
        ON HALF_DOUBLE_KEYS (SIDE, MATCH_KEY)
    """)

    count = db.execute("SELECT COUNT(*) FROM HALF_DOUBLE_KEYS").fetchone()[0]
    if count:
        return

    entries = []
    skipped = 0
    for row in db.execute("""
        SELECT WORDID, WORD, PHONEMES, FREQUENCY,
               STRESSEDSYLLABLE, SYLLABLECOUNT
        FROM RHYMES
        WHERE PHONEMES IS NOT NULL AND SYLLABLECOUNT > 0
          AND STRESSEDSYLLABLE IN (1, 2)
    """):
        stress_position = row[4]
        key = half_double_syllable_key(row[2], stress_position)
        if key is None:
            skipped += 1
            continue
        side = "final" if stress_position == 1 else "penultimate"
        entries.append((row[0], row[1], side, " ".join(key),
                        row[3], row[2], row[5]))

    db.executemany("""
        INSERT INTO HALF_DOUBLE_KEYS (
            WORDID, WORD, SIDE, MATCH_KEY, FREQUENCY, PHONEMES, SYLLABLECOUNT
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, entries)
    db.commit()
    print(f"Built HALF_DOUBLE_KEYS: {len(entries):,} pronunciation records ({skipped:,} excluded).")


def fetch_half_double_matches(db, source_rows, word, max_frequency=None):
    """Match final-stressed queries to penultimate-stressed words, and vice versa."""
    match_keys = set()
    for row in source_rows:
        position = row["STRESSEDSYLLABLE"]
        if position not in (1, 2):
            continue
        key = half_double_syllable_key(row["PHONEMES"], position)
        if key is not None:
            opposite_side = "penultimate" if position == 1 else "final"
            match_keys.add((opposite_side, " ".join(key)))

    if not match_keys:
        return []

    clauses = " OR ".join("(SIDE = ? AND MATCH_KEY = ?)" for _ in match_keys)
    parameters = []
    for side, key in sorted(match_keys):
        parameters.extend((side, key))
    parameters.append(word)

    sql = f"""
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM HALF_DOUBLE_KEYS
        WHERE ({clauses})
          AND WORD <> ? COLLATE NOCASE
          AND SYLLABLECOUNT > 0
    """
    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(max_frequency)
    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, parameters).fetchall()


def final_syllable_tokens(phonemes):
    """Return the final syllable as ordered phoneme tokens."""
    if not phonemes:
        return None
    tokens = phonemes.split()
    vowel_positions = [
        i for i, token in enumerate(tokens)
        if re.fullmatch(r"([A-Z]+)[012]", token)
        and re.fullmatch(r"([A-Z]+)[012]", token).group(1) in VOWEL_PHONEMES
    ]
    if not vowel_positions:
        return None
    # The final syllable includes its onset: start immediately after the
    # preceding vowel, or at the beginning for a one-syllable word.
    start = vowel_positions[-2] + 1 if len(vowel_positions) >= 2 else 0
    return tuple(tokens[start:])


def amphisbaenic_key(phonemes):
    """Reverse the phoneme order of the final syllable."""
    syllable = final_syllable_tokens(phonemes)
    return tuple(reversed(syllable)) if syllable else None


def elided_perfect_key(phonemes):
    """Perfect-rhyme key after deleting the final vowel phoneme."""
    if not phonemes:
        return None
    tokens = phonemes.split()
    vowel_positions = [
        i for i, token in enumerate(tokens)
        if re.fullmatch(r"([A-Z]+)[012]", token)
        and re.fullmatch(r"([A-Z]+)[012]", token).group(1) in VOWEL_PHONEMES
    ]
    if not vowel_positions:
        return None
    del tokens[vowel_positions[-1]]
    return rhyme_key(" ".join(reversed(tokens)))


def ensure_amphisbaenic_keys(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS AMPHISBAENIC_KEYS (
            WORDID INTEGER PRIMARY KEY, WORD TEXT NOT NULL,
            MATCH_KEY TEXT NOT NULL, FREQUENCY INTEGER,
            PHONEMES TEXT, SYLLABLECOUNT INTEGER
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS IDX_AMPHISBAENIC_MATCH ON AMPHISBAENIC_KEYS (MATCH_KEY)")
    if db.execute("SELECT COUNT(*) FROM AMPHISBAENIC_KEYS").fetchone()[0]:
        return
    entries = []
    for row in db.execute("""
        SELECT WORDID, WORD, PHONEMES, FREQUENCY, SYLLABLECOUNT
        FROM RHYMES WHERE PHONEMES IS NOT NULL AND SYLLABLECOUNT > 0
    """):
        key = final_syllable_tokens(row[2])
        if key:
            entries.append((row[0], row[1], " ".join(key), row[3], row[2], row[4]))
    db.executemany("INSERT INTO AMPHISBAENIC_KEYS VALUES (?, ?, ?, ?, ?, ?)", entries)
    db.commit()


def fetch_amphisbaenic_matches(db, source_rows, word, max_frequency=None):
    keys = {" ".join(key) for row in source_rows
            if (key := amphisbaenic_key(row["PHONEMES"])) is not None}
    if not keys:
        return []
    marks = ",".join("?" for _ in keys)
    sql = f"""SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
              FROM AMPHISBAENIC_KEYS WHERE MATCH_KEY IN ({marks})
              AND WORD <> ? COLLATE NOCASE AND SYLLABLECOUNT > 0"""
    args = sorted(keys) + [word]
    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        args.append(max_frequency)
    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, args).fetchall()


def ensure_elided_keys(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS ELIDED_KEYS (
            WORDID INTEGER PRIMARY KEY, WORD TEXT NOT NULL,
            PERFECT_KEY TEXT, ELIDED_KEY TEXT, FREQUENCY INTEGER,
            PHONEMES TEXT, SYLLABLECOUNT INTEGER
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS IDX_ELIDED_PERFECT ON ELIDED_KEYS (PERFECT_KEY)")
    db.execute("CREATE INDEX IF NOT EXISTS IDX_ELIDED_ELIDED ON ELIDED_KEYS (ELIDED_KEY)")
    if db.execute("SELECT COUNT(*) FROM ELIDED_KEYS").fetchone()[0]:
        return
    entries = []
    for row in db.execute("""
        SELECT WORDID, WORD, PHONEMES, REVERSEPHONEMES, FREQUENCY, SYLLABLECOUNT
        FROM RHYMES WHERE PHONEMES IS NOT NULL AND REVERSEPHONEMES IS NOT NULL
          AND SYLLABLECOUNT > 0
    """):
        perfect = rhyme_key(row[3])
        elided = elided_perfect_key(row[2])
        if perfect is not None or elided is not None:
            entries.append((row[0], row[1], " ".join(perfect) if perfect else None,
                            " ".join(elided) if elided else None,
                            row[4], row[2], row[5]))
    db.executemany("INSERT INTO ELIDED_KEYS VALUES (?, ?, ?, ?, ?, ?, ?)", entries)
    db.commit()


def fetch_elided_matches(db, source_rows, word, max_frequency=None):
    """Find ordinary perfect rhymes for the source with its final vowel elided.

    Rhymesaurus applies elision to the search word, not to each candidate.
    Therefore candidate pronunciations are compared using their ordinary
    perfect-rhyme keys only; ELIDED_KEY is not used on the candidate side.
    """
    source_elided = set()
    for row in source_rows:
        key = elided_perfect_key(row["PHONEMES"])
        if key:
            source_elided.add(" ".join(key))

    if not source_elided:
        return []

    marks = ",".join("?" for _ in source_elided)
    sql = f"""SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
              FROM ELIDED_KEYS
              WHERE PERFECT_KEY IN ({marks})
              AND WORD <> ? COLLATE NOCASE AND SYLLABLECOUNT > 0"""
    args = sorted(source_elided) + [word]
    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        args.append(max_frequency)
    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, args).fetchall()


def sight_spelling_key(word):
    """Return the final three written characters used by Sight Rhymes."""
    if not word:
        return None
    normalized = word.upper()
    if len(normalized) < 3:
        return None
    return normalized[-3:]


def ensure_sight_rhyme_keys(db):
    """Build an index of written endings paired with phonetic rhyme keys."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS SIGHT_RHYME_KEYS (
            WORDID INTEGER PRIMARY KEY,
            WORD TEXT NOT NULL,
            SPELLING_KEY TEXT NOT NULL,
            RHYME_KEY TEXT,
            FREQUENCY INTEGER,
            PHONEMES TEXT,
            SYLLABLECOUNT INTEGER
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS IDX_SIGHT_SPELLING_KEY
        ON SIGHT_RHYME_KEYS (SPELLING_KEY)
    """)
    # Version the derived table so databases built by the earlier, faulty
    # final-vowel-letter algorithm are rebuilt with the final-three-character
    # spelling key.
    columns = {
        row[1] for row in db.execute("PRAGMA table_info(SIGHT_RHYME_KEYS)")
    }
    if "KEY_VERSION" not in columns:
        db.execute("DROP TABLE SIGHT_RHYME_KEYS")
        db.execute("""
            CREATE TABLE SIGHT_RHYME_KEYS (
                WORDID INTEGER PRIMARY KEY,
                WORD TEXT NOT NULL,
                SPELLING_KEY TEXT NOT NULL,
                RHYME_KEY TEXT,
                FREQUENCY INTEGER,
                PHONEMES TEXT,
                SYLLABLECOUNT INTEGER,
                KEY_VERSION INTEGER NOT NULL DEFAULT 2
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS IDX_SIGHT_SPELLING_KEY
            ON SIGHT_RHYME_KEYS (SPELLING_KEY)
        """)
    count = db.execute("SELECT COUNT(*) FROM SIGHT_RHYME_KEYS").fetchone()[0]
    if count:
        return

    entries = []
    skipped = 0
    for row in db.execute("""
        SELECT WORDID, WORD, REVERSEPHONEMES, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM RHYMES
        WHERE WORD IS NOT NULL AND PHONEMES IS NOT NULL AND SYLLABLECOUNT > 0
    """):
        spelling_key = sight_spelling_key(row[1])
        if spelling_key is None:
            skipped += 1
            continue
        phonetic_key = rhyme_key(row[2]) if row[2] else None
        entries.append((row[0], row[1], spelling_key,
                        " ".join(phonetic_key) if phonetic_key else None,
                        row[3], row[4], row[5]))

    db.executemany("""
        INSERT INTO SIGHT_RHYME_KEYS
        (WORDID, WORD, SPELLING_KEY, RHYME_KEY, FREQUENCY, PHONEMES,
         SYLLABLECOUNT, KEY_VERSION)
        VALUES (?, ?, ?, ?, ?, ?, ?, 2)
    """, entries)
    db.commit()
    print(f"Built SIGHT_RHYME_KEYS: {len(entries):,} pronunciation records ({skipped:,} excluded).")


def fetch_sight_matches(db, spelling_key, source_rhyme_keys, word, max_frequency=None):
    """Find shared written endings, excluding actual perfect-rhyme matches."""
    if not spelling_key:
        return []
    sql = """
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT, RHYME_KEY
        FROM SIGHT_RHYME_KEYS
        WHERE SPELLING_KEY = ?
          AND WORD <> ? COLLATE NOCASE
          AND SYLLABLECOUNT > 0
    """
    parameters = [spelling_key, word]
    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(max_frequency)
    if source_rhyme_keys:
        keys = sorted(" ".join(key) for key in source_rhyme_keys)
        placeholders = ",".join("?" for _ in keys)
        sql += f" AND (RHYME_KEY IS NULL OR RHYME_KEY NOT IN ({placeholders}))"
        parameters.extend(keys)
    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, parameters).fetchall()


def ensure_assonance_keys(db):
    """Create and populate the indexed final-vowel Assonance table."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS ASSONANCE_KEYS (
            WORDID INTEGER PRIMARY KEY,
            WORD TEXT NOT NULL,
            ASSONANCE_KEY TEXT NOT NULL,
            FREQUENCY INTEGER,
            PHONEMES TEXT,
            SYLLABLECOUNT INTEGER
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS IDX_ASSONANCE_KEY
        ON ASSONANCE_KEYS (ASSONANCE_KEY)
    """)

    count = db.execute(
        "SELECT COUNT(*) FROM ASSONANCE_KEYS"
    ).fetchone()[0]
    if count:
        return

    source_rows = db.execute("""
        SELECT WORDID, WORD, PHONEMES, FREQUENCY, SYLLABLECOUNT
        FROM RHYMES
        WHERE PHONEMES IS NOT NULL
          AND SYLLABLECOUNT > 0
    """).fetchall()

    entries = []
    skipped = 0
    for row in source_rows:
        key = assonance_key(row["PHONEMES"])
        if key is None:
            skipped += 1
            continue
        entries.append((
            row["WORDID"], row["WORD"], key, row["FREQUENCY"],
            row["PHONEMES"], row["SYLLABLECOUNT"],
        ))

    db.executemany("""
        INSERT INTO ASSONANCE_KEYS (
            WORDID, WORD, ASSONANCE_KEY, FREQUENCY, PHONEMES, SYLLABLECOUNT
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, entries)
    db.commit()
    print(
        f"Built ASSONANCE_KEYS: {len(entries):,} pronunciation records "
        f"({skipped:,} excluded)."
    )


def fetch_assonance_matches(db, source_keys, word, max_frequency=None):
    """Fetch words with the same final vowel phoneme and stress."""
    if not source_keys:
        return []

    placeholders = ",".join("?" for _ in source_keys)
    sql = f"""
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM ASSONANCE_KEYS
        WHERE ASSONANCE_KEY IN ({placeholders})
          AND WORD <> ? COLLATE NOCASE
          AND SYLLABLECOUNT > 0
    """
    parameters = sorted(source_keys) + [word]
    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(max_frequency)
    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, parameters).fetchall()


def final_consonant_key(phonemes):
    """Return the final consonant phoneme, or None for unusable records."""
    if not phonemes:
        return None
    tokens = phonemes.split()
    if not tokens:
        return None

    final = tokens[-1]
    base = re.sub(r"[012]+$", "", final)
    if base in VOWEL_PHONEMES:
        return None
    if not re.fullmatch(r"[A-Z]+", base):
        return None
    return base


def double_consonance_key(phonemes):
    """Return the final two consonant phonemes, skipping intervening vowels."""
    if not phonemes:
        return None

    consonants = []
    for token in reversed(phonemes.split()):
        base = re.sub(r"[012]+$", "", token)
        if base in VOWEL_PHONEMES:
            continue
        if not re.fullmatch(r"[A-Z]+", base):
            return None
        consonants.append(base)
        if len(consonants) == 2:
            return tuple(consonants)

    return None


def full_consonance_key(phonemes):
    """Return the complete ordered consonant pattern, ignoring vowels."""
    if not phonemes:
        return None

    consonants = []
    for token in phonemes.split():
        base = re.sub(r"[012]+$", "", token)
        if base in VOWEL_PHONEMES:
            continue
        if not re.fullmatch(r"[A-Z]+", base):
            return None
        consonants.append(base)

    return tuple(consonants) if consonants else None


def ensure_full_consonance_keys(db):
    """Create and populate an index of complete consonant patterns."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS FULL_CONSONANCE_KEYS (
            WORDID INTEGER PRIMARY KEY,
            WORD TEXT NOT NULL,
            FULL_CONSONANCE_KEY TEXT NOT NULL,
            FREQUENCY INTEGER,
            PHONEMES TEXT,
            SYLLABLECOUNT INTEGER
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS IDX_FULL_CONSONANCE_KEY
        ON FULL_CONSONANCE_KEYS (FULL_CONSONANCE_KEY)
    """)

    count = db.execute(
        "SELECT COUNT(*) FROM FULL_CONSONANCE_KEYS"
    ).fetchone()[0]
    if count:
        return

    source_rows = db.execute("""
        SELECT WORDID, WORD, PHONEMES, FREQUENCY, SYLLABLECOUNT
        FROM RHYMES
        WHERE PHONEMES IS NOT NULL
          AND SYLLABLECOUNT > 0
    """).fetchall()

    entries = []
    skipped = 0
    for row in source_rows:
        key = full_consonance_key(row["PHONEMES"])
        if key is None:
            skipped += 1
            continue
        entries.append((
            row["WORDID"], row["WORD"], " ".join(key),
            row["FREQUENCY"], row["PHONEMES"], row["SYLLABLECOUNT"],
        ))

    db.executemany("""
        INSERT INTO FULL_CONSONANCE_KEYS (
            WORDID, WORD, FULL_CONSONANCE_KEY, FREQUENCY,
            PHONEMES, SYLLABLECOUNT
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, entries)
    db.commit()
    print(
        f"Built FULL_CONSONANCE_KEYS: {len(entries):,} pronunciation records "
        f"({skipped:,} excluded)."
    )


def fetch_full_consonance_matches(
    db, source_keys, word, max_frequency=None
):
    """Fetch words sharing any complete consonant pattern with the query."""
    if not source_keys:
        return []

    placeholders = ",".join("?" for _ in source_keys)
    sql = f"""
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM FULL_CONSONANCE_KEYS
        WHERE FULL_CONSONANCE_KEY IN ({placeholders})
          AND WORD <> ? COLLATE NOCASE
          AND SYLLABLECOUNT > 0
    """
    parameters = sorted(" ".join(key) for key in source_keys) + [word]

    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(max_frequency)

    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, parameters).fetchall()


def ensure_double_consonance_keys(db):
    """Create and populate an index of the final two consonant phonemes."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS DOUBLE_CONSONANCE_KEYS (
            WORDID INTEGER PRIMARY KEY,
            WORD TEXT NOT NULL,
            DOUBLE_CONSONANCE_KEY TEXT NOT NULL,
            FREQUENCY INTEGER,
            PHONEMES TEXT,
            SYLLABLECOUNT INTEGER
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS IDX_DOUBLE_CONSONANCE_KEY
        ON DOUBLE_CONSONANCE_KEYS (DOUBLE_CONSONANCE_KEY)
    """)

    count = db.execute(
        "SELECT COUNT(*) FROM DOUBLE_CONSONANCE_KEYS"
    ).fetchone()[0]
    if count:
        return

    source_rows = db.execute("""
        SELECT WORDID, WORD, PHONEMES, FREQUENCY, SYLLABLECOUNT
        FROM RHYMES
        WHERE PHONEMES IS NOT NULL
          AND SYLLABLECOUNT > 0
    """).fetchall()

    entries = []
    skipped = 0
    for row in source_rows:
        key = double_consonance_key(row["PHONEMES"])
        if key is None:
            skipped += 1
            continue
        entries.append((
            row["WORDID"], row["WORD"], " ".join(key),
            row["FREQUENCY"], row["PHONEMES"], row["SYLLABLECOUNT"],
        ))

    db.executemany("""
        INSERT INTO DOUBLE_CONSONANCE_KEYS (
            WORDID, WORD, DOUBLE_CONSONANCE_KEY, FREQUENCY,
            PHONEMES, SYLLABLECOUNT
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, entries)
    db.commit()
    print(
        f"Built DOUBLE_CONSONANCE_KEYS: {len(entries):,} pronunciation records "
        f"({skipped:,} excluded)."
    )


def fetch_double_consonance_matches(
    db, source_keys, word, max_frequency=None
):
    """Fetch words sharing either of the query's final consonant pairs."""
    if not source_keys:
        return []

    placeholders = ",".join("?" for _ in source_keys)
    sql = f"""
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM DOUBLE_CONSONANCE_KEYS
        WHERE DOUBLE_CONSONANCE_KEY IN ({placeholders})
          AND WORD <> ? COLLATE NOCASE
          AND SYLLABLECOUNT > 0
    """
    parameters = sorted(" ".join(key) for key in source_keys) + [word]

    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(max_frequency)

    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, parameters).fetchall()


def ensure_consonance_keys(db):
    """Create and populate an index of final consonant phonemes."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS CONSONANCE_KEYS (
            WORDID INTEGER PRIMARY KEY,
            WORD TEXT NOT NULL,
            FINAL_CONSONANT TEXT NOT NULL,
            FREQUENCY INTEGER,
            PHONEMES TEXT,
            SYLLABLECOUNT INTEGER
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS IDX_CONSONANCE_FINAL
        ON CONSONANCE_KEYS (FINAL_CONSONANT)
    """)

    count = db.execute(
        "SELECT COUNT(*) FROM CONSONANCE_KEYS"
    ).fetchone()[0]
    if count:
        return

    source_rows = db.execute("""
        SELECT WORDID, WORD, PHONEMES, FREQUENCY, SYLLABLECOUNT
        FROM RHYMES
        WHERE PHONEMES IS NOT NULL
          AND SYLLABLECOUNT > 0
    """).fetchall()

    entries = []
    skipped = 0
    for row in source_rows:
        key = final_consonant_key(row["PHONEMES"])
        if key is None:
            # This includes vowel-ending pronunciations and malformed tokens.
            skipped += 1
            continue
        entries.append((
            row["WORDID"], row["WORD"], key, row["FREQUENCY"],
            row["PHONEMES"], row["SYLLABLECOUNT"],
        ))

    db.executemany("""
        INSERT INTO CONSONANCE_KEYS (
            WORDID, WORD, FINAL_CONSONANT, FREQUENCY,
            PHONEMES, SYLLABLECOUNT
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, entries)
    db.commit()
    print(
        f"Built CONSONANCE_KEYS: {len(entries):,} pronunciation records "
        f"({skipped:,} excluded)."
    )


def fetch_consonance_matches(db, source_keys, word, max_frequency=None):
    """Fetch words sharing any final consonant phoneme with the query."""
    if not source_keys:
        return []

    placeholders = ",".join("?" for _ in source_keys)
    sql = f"""
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM CONSONANCE_KEYS
        WHERE FINAL_CONSONANT IN ({placeholders})
          AND WORD <> ? COLLATE NOCASE
          AND SYLLABLECOUNT > 0
    """
    parameters = sorted(source_keys) + [word]

    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(max_frequency)

    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, parameters).fetchall()

def reverse_rhyme_key(reversed_phonemes):
    """Return the reversed pronunciation from its primary-stressed vowel onward."""
    if not reversed_phonemes:
        return None
    tokens = reversed_phonemes.split()
    for index, token in enumerate(tokens):
        if token.endswith("1"):
            return tuple(tokens[index:])
    return None


def reverse_first_syllable_key(phonemes):
    """Return the first syllable's reversed rhyme, ignoring lexical stress."""
    if not phonemes:
        return None
    tokens = phonemes.split()
    vowel_indexes = [
        i for i, token in enumerate(tokens)
        if token.endswith(("0", "1", "2"))
    ]
    if not vowel_indexes:
        return None
    end = vowel_indexes[1] if len(vowel_indexes) > 1 else len(tokens)
    first_syllable_reversed = list(reversed(tokens[:end]))
    for index, token in enumerate(first_syllable_reversed):
        if token.endswith(("0", "1", "2")):
            return tuple(t.rstrip("012") for t in first_syllable_reversed[index:])
    return None


def ensure_reverse_rhyme_keys(db):
    """Build indexed keys for Reverse and Reverse First Syllable searches."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS REVERSE_RHYME_KEYS (
            WORDID INTEGER PRIMARY KEY,
            WORD TEXT NOT NULL,
            REVERSE_RHYME_KEY TEXT,
            REVERSE_FIRST_SYLLABLE_KEY TEXT,
            FREQUENCY INTEGER,
            PHONEMES TEXT,
            SYLLABLECOUNT INTEGER
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS IDX_REVERSE_RHYME_KEY ON REVERSE_RHYME_KEYS (REVERSE_RHYME_KEY)")
    db.execute("CREATE INDEX IF NOT EXISTS IDX_REVERSE_FIRST_KEY ON REVERSE_RHYME_KEYS (REVERSE_FIRST_SYLLABLE_KEY)")
    if db.execute("SELECT COUNT(*) FROM REVERSE_RHYME_KEYS").fetchone()[0]:
        return
    source_rows = db.execute("""
        SELECT WORDID, WORD, PHONEMES, REVERSEPHONEMES, FREQUENCY, SYLLABLECOUNT
        FROM RHYMES WHERE PHONEMES IS NOT NULL AND SYLLABLECOUNT > 0
    """).fetchall()
    entries = []
    for row in source_rows:
        reverse_key = reverse_rhyme_key(row["REVERSEPHONEMES"])
        first_key = reverse_first_syllable_key(row["PHONEMES"])
        if reverse_key is None and first_key is None:
            continue
        entries.append((row["WORDID"], row["WORD"],
            " ".join(reverse_key) if reverse_key else None,
            " ".join(first_key) if first_key else None,
            row["FREQUENCY"], row["PHONEMES"], row["SYLLABLECOUNT"]))
    db.executemany("""
        INSERT INTO REVERSE_RHYME_KEYS
        (WORDID, WORD, REVERSE_RHYME_KEY, REVERSE_FIRST_SYLLABLE_KEY, FREQUENCY, PHONEMES, SYLLABLECOUNT)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, entries)
    db.commit()
    print(f"Built REVERSE_RHYME_KEYS: {len(entries):,} pronunciation records.")


def fetch_reverse_matches(db, field, source_keys, word, max_frequency=None):
    if not source_keys:
        return []
    if field not in ("REVERSE_RHYME_KEY", "REVERSE_FIRST_SYLLABLE_KEY"):
        raise ValueError("Invalid reverse-rhyme search field")
    placeholders = ",".join("?" for _ in source_keys)
    sql = f"""
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM REVERSE_RHYME_KEYS
        WHERE {field} IN ({placeholders})
          AND WORD <> ? COLLATE NOCASE
          AND SYLLABLECOUNT > 0
    """
    parameters = sorted(source_keys) + [word]
    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(max_frequency)
    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, parameters).fetchall()

def ensure_first_syllable_indexes(db):
    """Create indexes for the two first-syllable search fields."""

    db.execute("""
        CREATE INDEX IF NOT EXISTS IDX_FIRST_SYLLABLE_REVERSE
        ON RHYMES (FIRSTSYLLABLEREVERSE)
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS IDX_FIRST_SYLLABLE_WOCONS
        ON RHYMES (FIRSTSYLLABLEREVERSEWOCONS)
    """)

    db.commit()


def phoneme_distance_one(a, b):
    """True when two phoneme sequences differ by one edit."""
    if a == b:
        return False

    if abs(len(a) - len(b)) > 1:
        return False

    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1

    shorter, longer = (a, b) if len(a) < len(b) else (b, a)

    i = j = differences = 0

    while i < len(shorter) and j < len(longer):
        if shorter[i] == longer[j]:
            i += 1
            j += 1
        else:
            differences += 1
            j += 1

            if differences > 1:
                return False

    return True



def fetch_dictionary_entries(word, db_path=DB_PATH):
    """Return all exact dictionary entries for a spelling, in source order."""
    word = word.strip()
    if not word:
        return []

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute("""
            SELECT WORDID, WORD, USAGE, DEFINITION, WORDL
            FROM DICTIONARY
            WHERE WORD = ? COLLATE NOCASE
            ORDER BY WORDID
        """, (word,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        db.close()

def suggest_words(prefix, limit=20, db_path=DB_PATH):
    """Return words beginning with the supplied spelling prefix."""

    prefix = prefix.strip().lower()

    if not prefix:
        return []

    if limit < 1:
        raise ValueError("limit must be at least 1")

    escaped_prefix = (
        prefix
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    try:
        rows = db.execute("""
            SELECT
                WORD,
                MIN(COALESCE(FREQUENCY, 99)) AS FREQUENCY
            FROM RHYMES
            WHERE WORDL LIKE ? ESCAPE '\\'
            GROUP BY WORD
            ORDER BY WORD COLLATE NOCASE
            LIMIT ?
        """, (escaped_prefix + "%", limit)).fetchall()

    finally:
        db.close()

    return [
        {
            "word": row["WORD"],
            "frequency": row["FREQUENCY"],
        }
        for row in rows
    ]


def begins_with_sound_key(phonemes):
    """Return the complete initial phoneme sequence, ignoring stress."""
    if not phonemes:
        return None
    tokens = phonemes.split()
    if not tokens:
        return None
    return tuple(re.sub(r"[012]$", "", token) for token in tokens)


def fetch_begins_with_matches(db, source_rows, word, max_frequency=None):
    """Find words whose pronunciations start with a source pronunciation."""
    keys = {
        begins_with_sound_key(row["PHONEMES"])
        for row in source_rows
        if begins_with_sound_key(row["PHONEMES"])
    }
    if not keys:
        raise NoUsablePronunciationError(word)

    # A phoneme sequence is a prefix only when every source phoneme matches
    # the corresponding candidate phoneme. Compare token boundaries, not
    # raw string prefixes (so e.g. T cannot match TH).
    matches = []
    seen = set()
    for candidate in db.execute("""
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM RHYMES
        WHERE PHONEMES IS NOT NULL AND SYLLABLECOUNT > 0
          AND WORD <> ? COLLATE NOCASE
    """, (word,)):
        candidate_key = begins_with_sound_key(candidate["PHONEMES"])
        if candidate_key is None:
            continue
        if any(len(candidate_key) >= len(key) and candidate_key[:len(key)] == key
               for key in keys):
            if max_frequency is not None and candidate["FREQUENCY"] is not None \
                    and candidate["FREQUENCY"] > max_frequency:
                continue
            identity = candidate["WORDID"]
            if identity not in seen:
                seen.add(identity)
                matches.append(candidate)
    return matches


def ends_with_sound_key(phonemes):
    """Return the complete final phoneme sequence, ignoring stress."""
    if not phonemes:
        return None
    tokens = phonemes.split()
    if not tokens:
        return None
    return tuple(re.sub(r"[012]$", "", token) for token in tokens)


def fetch_ends_with_matches(db, source_rows, word, max_frequency=None):
    """Find words whose pronunciations end with a source pronunciation."""
    keys = {
        ends_with_sound_key(row["PHONEMES"])
        for row in source_rows
        if ends_with_sound_key(row["PHONEMES"])
    }
    if not keys:
        raise NoUsablePronunciationError(word)

    matches = []
    seen = set()
    for candidate in db.execute("""
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM RHYMES
        WHERE PHONEMES IS NOT NULL AND SYLLABLECOUNT > 0
          AND WORD <> ? COLLATE NOCASE
    """, (word,)):
        candidate_key = ends_with_sound_key(candidate["PHONEMES"])
        if candidate_key is None:
            continue
        if any(len(candidate_key) >= len(key)
               and candidate_key[-len(key):] == key for key in keys):
            if max_frequency is not None and candidate["FREQUENCY"] is not None \
                    and candidate["FREQUENCY"] > max_frequency:
                continue
            identity = candidate["WORDID"]
            if identity not in seen:
                seen.add(identity)
                matches.append(candidate)
    return matches


def fetch_ends_with_spelling_matches(db, word, max_frequency=None):
    """Fallback for text absent from the pronunciation dictionary."""
    suffix = word.strip()
    escaped = suffix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    sql = """SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
             FROM RHYMES WHERE WORD LIKE ? ESCAPE '\\'
               AND WORD <> ? COLLATE NOCASE AND SYLLABLECOUNT > 0"""
    args = ["%" + escaped, word]
    if max_frequency is not None:
        sql += " AND (FREQUENCY IS NULL OR FREQUENCY <= ?)"
        args.append(max_frequency)
    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, args).fetchall()


def contains_sound_key(phonemes):
    """Return the complete pronunciation as stress-independent phonemes."""
    if not phonemes:
        return None
    tokens = phonemes.split()
    if not tokens:
        return None
    return tuple(re.sub(r"[012]$", "", token) for token in tokens)


def fetch_contains_matches(db, source_rows, word, max_frequency=None):
    """Find pronunciations containing any complete source phoneme sequence."""
    source_keys = {
        contains_sound_key(row["PHONEMES"])
        for row in source_rows
        if contains_sound_key(row["PHONEMES"])
    }
    if not source_keys:
        raise NoUsablePronunciationError(word)

    matches = []
    seen = set()

    candidates = db.execute("""
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM RHYMES
        WHERE PHONEMES IS NOT NULL
          AND SYLLABLECOUNT > 0
          AND WORD <> ? COLLATE NOCASE
    """, (word,))

    for candidate in candidates:
        candidate_key = contains_sound_key(candidate["PHONEMES"])
        if candidate_key is None:
            continue

        found = any(
            len(candidate_key) >= len(key)
            and any(
                candidate_key[index:index + len(key)] == key
                for index in range(len(candidate_key) - len(key) + 1)
            )
            for key in source_keys
        )
        if not found:
            continue

        if (max_frequency is not None
                and candidate["FREQUENCY"] is not None
                and candidate["FREQUENCY"] > max_frequency):
            continue

        identity = candidate["WORDID"]
        if identity not in seen:
            seen.add(identity)
            matches.append(candidate)

    return matches


def fetch_contains_spelling_matches(db, word, max_frequency=None):
    """Fallback for text absent from the pronunciation dictionary."""
    fragment = word.strip()
    escaped = fragment.replace("\\\\", "\\\\\\\\").replace("%", "\\%").replace("_", "\\_")
    sql = """SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
             FROM RHYMES WHERE WORD LIKE ? ESCAPE '\\'
               AND WORD <> ? COLLATE NOCASE AND SYLLABLECOUNT > 0"""
    args = ["%" + escaped + "%", word]
    if max_frequency is not None:
        sql += " AND (FREQUENCY IS NULL OR FREQUENCY <= ?)"
        args.append(max_frequency)
    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, args).fetchall()


def fetch_begins_with_spelling_matches(db, word, max_frequency=None):
    """Fallback for text absent from the pronunciation dictionary."""
    prefix = word.strip()
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    sql = """SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
             FROM RHYMES WHERE WORD LIKE ? ESCAPE '\\'
               AND WORD <> ? COLLATE NOCASE AND SYLLABLECOUNT > 0"""
    args = [escaped + "%", word]
    if max_frequency is not None:
        sql += " AND (FREQUENCY IS NULL OR FREQUENCY <= ?)"
        args.append(max_frequency)
    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, args).fetchall()


def search_rhymes(
    word,
    near=False,
    max_frequency=None,
    db_path=DB_PATH,
    rhyme_type="perfect",
):
    """
    Search the pronunciation database.

    rhyme_type:
        perfect:
            Exact rhyme from the primary-stressed vowel onward.

        light:
            Same final rhyme sound, opposite final/penultimate
            primary-stress position.

        final_syllable:
            Same final rhyme sound, regardless of stress.

        first_syllable:
            Same first-syllable vowel and ending consonants.

        first_syllable_assonance:
            Same first-syllable vowel and initial consonants.

        homophones:
            Exact match of the complete pronunciation, including stress.

        consonance:
            Same final consonant phoneme, regardless of preceding sounds.

        double_consonance:
            Same final two consonant phonemes, skipping intervening vowels.

        full_consonance:
            Same complete ordered consonant pattern, ignoring vowels and stress.

        assonance:
            Same final vowel phoneme, including its stress marker.

        full_assonance:
            Same complete ordered vowel pattern, ignoring stress and
            syllable count.

        full_assonance_end_consonant:
            Same complete ordered vowel pattern and same final consonant.

        sight:
            Same final three written characters, excluding words that share
            the source word's perfect-rhyme pronunciation key.

        half_double:
            Match the stressed final syllable of one word with the stressed
            penultimate syllable of another, in either search direction.

        amphisbaenic:
            Reverse the phoneme order of the final syllable.

        elided:
            Match perfect-rhyme keys after deleting the source final vowel.

        begins_with:
            Match initial pronunciation sounds, or spelling prefix if unknown.

        ends_with:
            Match final pronunciation sounds, or spelling suffix if unknown.

        contains:
            Match a pronunciation sequence anywhere in the candidate, or
            a spelling substring if the search text is unknown.

    near:
        For perfect rhymes only, also include keys one phoneme edit away.
    """

    rhyme_type = (
        rhyme_type.lower()
        .replace("-", "_")
        .replace(" ", "_")
    )

    if rhyme_type not in RHYME_TYPES:
        raise ValueError(
            f"rhyme_type must be one of {RHYME_TYPES}"
        )

    if max_frequency is not None:
        if max_frequency not in FREQUENCY_CATEGORIES:
            raise ValueError(
                f"max_frequency must be one of {FREQUENCY_CATEGORIES}"
            )

    if near and rhyme_type != "perfect":
        raise ValueError(
            "near-rhyme mode is currently available only for perfect rhymes"
        )

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    try:
        source_rows = db.execute("""
            SELECT
                WORD,
                PHONEMES,
                REVERSEPHONEMES,
                STRESSEDSYLLABLE,
                FIRSTSYLLABLEREVERSE,
                FIRSTSYLLABLEREVERSEWOCONS
            FROM RHYMES
            WHERE WORD = ? COLLATE NOCASE
        """, (word,)).fetchall()

        if not source_rows and rhyme_type not in (
            "begins_with", "ends_with", "contains"
        ):
            raise WordNotFoundError(word)

        # ----------------------------------------------------
        # Contains
        # ----------------------------------------------------

        if rhyme_type == "contains":
            if source_rows:
                rows = fetch_contains_matches(
                    db, source_rows, word, max_frequency
                )
            else:
                rows = fetch_contains_spelling_matches(
                    db, word, max_frequency
                )

        # ----------------------------------------------------
        # Begins With
        # ----------------------------------------------------

        elif rhyme_type == "begins_with":
            if source_rows:
                rows = fetch_begins_with_matches(
                    db, source_rows, word, max_frequency
                )
            else:
                rows = fetch_begins_with_spelling_matches(
                    db, word, max_frequency
                )

        # ----------------------------------------------------
        # Ends With
        # ----------------------------------------------------

        elif rhyme_type == "ends_with":
            if source_rows:
                rows = fetch_ends_with_matches(
                    db, source_rows, word, max_frequency
                )
            else:
                rows = fetch_ends_with_spelling_matches(
                    db, word, max_frequency
                )

        # ----------------------------------------------------
        # Perfect rhymes
        # ----------------------------------------------------

        elif rhyme_type == "perfect":

            source_keys = {
                key
                for row in source_rows
                if (key := rhyme_key(row["REVERSEPHONEMES"])) is not None
            }

            if not source_keys:
                raise NoUsablePronunciationError(word)

            if near:
                all_keys = db.execute("""
                    SELECT DISTINCT RHYME_KEY
                    FROM RHYME_KEYS
                """).fetchall()

                matching_keys = set()

                for row in all_keys:
                    candidate = tuple(row["RHYME_KEY"].split())

                    if any(
                        phoneme_distance_one(source_key, candidate)
                        for source_key in source_keys
                    ):
                        matching_keys.add(row["RHYME_KEY"])

            else:
                matching_keys = {
                    " ".join(key) for key in source_keys
                }

            if not matching_keys:
                rows = []

            else:
                placeholders = ",".join(
                    "?" for _ in matching_keys
                )

                sql = f"""
                    SELECT
                        K.WORDID,
                        K.WORD,
                        K.FREQUENCY,
                        K.PHONEMES,
                        R.SYLLABLECOUNT
                    FROM RHYME_KEYS K
                    JOIN RHYMES R ON R.WORDID = K.WORDID
                    WHERE K.RHYME_KEY IN ({placeholders})
                      AND K.WORD <> ? COLLATE NOCASE
                      AND R.SYLLABLECOUNT > 0
                """

                parameters = sorted(matching_keys) + [word]

                if max_frequency is not None:
                    sql += " AND K.FREQUENCY <= ?"
                    parameters.append(max_frequency)

                sql += """
                    ORDER BY R.SYLLABLECOUNT, K.FREQUENCY, K.WORD
                """

                rows = db.execute(sql, parameters).fetchall()

        # ----------------------------------------------------
        # Light and Final Syllable rhymes
        # ----------------------------------------------------

        elif rhyme_type in ("light", "final_syllable"):

            ensure_final_rhyme_keys(db)

            source_keys = set()
            source_stresses = set()

            for row in source_rows:
                key = final_rhyme_key(row["REVERSEPHONEMES"])

                if key is not None:
                    source_keys.add(" ".join(key))

                    if row["STRESSEDSYLLABLE"] in (1, 2):
                        source_stresses.add(
                            row["STRESSEDSYLLABLE"]
                        )

            if not source_keys:
                raise NoUsablePronunciationError(word)

            if rhyme_type == "light":

                candidate_stresses = set()

                if 1 in source_stresses:
                    candidate_stresses.add(2)

                if 2 in source_stresses:
                    candidate_stresses.add(1)

                if not candidate_stresses:
                    rows = []

                else:
                    rows = fetch_final_rhymes(
                        db,
                        source_keys,
                        word,
                        candidate_stresses,
                        max_frequency,
                    )

            else:
                rows = fetch_final_rhymes(
                    db,
                    source_keys,
                    word,
                    None,
                    max_frequency,
                )

        # ----------------------------------------------------
        # Back rhymes
        # ----------------------------------------------------

        elif rhyme_type == "back":

            ensure_back_rhyme_keys(db)

            source_keys = {
                " ".join(key)
                for row in source_rows
                if (key := back_rhyme_key(
                    row["PHONEMES"], row["STRESSEDSYLLABLE"]
                )) is not None
            }

            if not source_keys:
                raise NoUsablePronunciationError(word)

            rows = fetch_back_rhyme_matches(
                db, source_keys, word, max_frequency
            )

        # ----------------------------------------------------
        # Reverse and Reverse First Syllable rhymes
        # ----------------------------------------------------

        elif rhyme_type in ("reverse", "reverse_first_syllable"):
            ensure_reverse_rhyme_keys(db)
            if rhyme_type == "reverse":
                field = "REVERSE_RHYME_KEY"
                source_keys = {
                    " ".join(key)
                    for row in source_rows
                    if (key := reverse_rhyme_key(row["REVERSEPHONEMES"])) is not None
                }
            else:
                field = "REVERSE_FIRST_SYLLABLE_KEY"
                source_keys = {
                    " ".join(key)
                    for row in source_rows
                    if (key := reverse_first_syllable_key(row["PHONEMES"])) is not None
                }
            if not source_keys:
                raise NoUsablePronunciationError(word)
            rows = fetch_reverse_matches(
                db, field, source_keys, word, max_frequency
            )

        # ----------------------------------------------------
        # Homophones
        # ----------------------------------------------------

        elif rhyme_type == "homophones":
            ensure_homophone_keys(db)
            source_keys = {
                row["PHONEMES"]
                for row in source_rows
                if row["PHONEMES"]
            }
            if not source_keys:
                raise NoUsablePronunciationError(word)
            rows = fetch_homophone_matches(
                db, source_keys, word, max_frequency
            )

        # ----------------------------------------------------
        # Double Consonance
        # ----------------------------------------------------

        elif rhyme_type == "double_consonance":
            ensure_double_consonance_keys(db)
            source_keys = {
                key
                for row in source_rows
                if (key := double_consonance_key(row["PHONEMES"])) is not None
            }
            if not source_keys:
                raise NoUsablePronunciationError(word)
            rows = fetch_double_consonance_matches(
                db, source_keys, word, max_frequency
            )

        # ----------------------------------------------------
        # Sight Rhymes
        # ----------------------------------------------------

        elif rhyme_type == "sight":
            ensure_sight_rhyme_keys(db)
            spelling_key = sight_spelling_key(word)
            source_rhyme_keys = {
                key
                for row in source_rows
                if row["REVERSEPHONEMES"]
                and (key := rhyme_key(row["REVERSEPHONEMES"])) is not None
            }
            if spelling_key is None:
                raise NoUsablePronunciationError(word)
            rows = fetch_sight_matches(
                db, spelling_key, source_rhyme_keys, word, max_frequency
            )

        # ----------------------------------------------------
        # Half-double Rhymes
        # ----------------------------------------------------

        elif rhyme_type == "half_double":
            ensure_half_double_keys(db)
            rows = fetch_half_double_matches(
                db, source_rows, word, max_frequency
            )
            if not rows and not any(
                row["STRESSEDSYLLABLE"] in (1, 2)
                and half_double_syllable_key(
                    row["PHONEMES"], row["STRESSEDSYLLABLE"]
                ) is not None
                for row in source_rows
            ):
                raise NoUsablePronunciationError(word)

        # ----------------------------------------------------
        # Amphisbaenic Rhymes
        # ----------------------------------------------------

        elif rhyme_type == "amphisbaenic":
            ensure_amphisbaenic_keys(db)
            rows = fetch_amphisbaenic_matches(db, source_rows, word, max_frequency)
            if not any(amphisbaenic_key(row["PHONEMES"]) for row in source_rows):
                raise NoUsablePronunciationError(word)

        # ----------------------------------------------------
        # Elided Rhymes
        # ----------------------------------------------------

        elif rhyme_type == "elided":
            ensure_elided_keys(db)
            rows = fetch_elided_matches(db, source_rows, word, max_frequency)
            if not any(
                elided_perfect_key(row["PHONEMES"])
                for row in source_rows
            ):
                raise NoUsablePronunciationError(word)

        # ----------------------------------------------------
        # Full Consonance
        # ----------------------------------------------------

        elif rhyme_type == "full_consonance":
            ensure_full_consonance_keys(db)
            source_keys = {
                key
                for row in source_rows
                if (key := full_consonance_key(row["PHONEMES"])) is not None
            }
            if not source_keys:
                raise NoUsablePronunciationError(word)
            rows = fetch_full_consonance_matches(
                db, source_keys, word, max_frequency
            )

        # ----------------------------------------------------
        # Assonance
        # ----------------------------------------------------

        elif rhyme_type == "assonance":
            ensure_assonance_keys(db)
            source_keys = {
                key
                for row in source_rows
                if (key := assonance_key(row["PHONEMES"])) is not None
            }
            if not source_keys:
                raise NoUsablePronunciationError(word)
            rows = fetch_assonance_matches(
                db, source_keys, word, max_frequency
            )

        # ----------------------------------------------------
        # Full Assonance
        # ----------------------------------------------------

        elif rhyme_type == "full_assonance":
            ensure_full_assonance_keys(db)
            source_keys = {
                key
                for row in source_rows
                if (key := full_assonance_key(row["PHONEMES"])) is not None
            }
            if not source_keys:
                raise NoUsablePronunciationError(word)
            rows = fetch_full_assonance_matches(
                db, source_keys, word, max_frequency
            )

        # ----------------------------------------------------
        # Full Assonance & End Consonant
        # ----------------------------------------------------

        elif rhyme_type == "full_assonance_end_consonant":
            ensure_full_assonance_end_consonant_keys(db)
            source_keys = {
                key
                for row in source_rows
                if (key := full_assonance_end_consonant_key(
                    row["PHONEMES"]
                )) is not None
            }
            if not source_keys:
                raise NoUsablePronunciationError(word)
            rows = fetch_full_assonance_end_consonant_matches(
                db, source_keys, word, max_frequency
            )

        # ----------------------------------------------------
        # Consonance
        # ----------------------------------------------------

        elif rhyme_type == "consonance":
            ensure_consonance_keys(db)
            source_keys = {
                key
                for row in source_rows
                if (key := final_consonant_key(row["PHONEMES"])) is not None
            }
            if not source_keys:
                raise NoUsablePronunciationError(word)
            rows = fetch_consonance_matches(
                db, source_keys, word, max_frequency
            )

        # ----------------------------------------------------
        # First Syllable and First Syllable Assonance
        # ----------------------------------------------------

        else:

            ensure_first_syllable_indexes(db)

            if rhyme_type == "first_syllable":
                field = "FIRSTSYLLABLEREVERSE"
            else:
                field = "FIRSTSYLLABLEREVERSEWOCONS"

            source_keys = {
                row[field]
                for row in source_rows
                if row[field]
            }

            if not source_keys:
                raise NoUsablePronunciationError(word)

            rows = fetch_first_syllable_matches(
                db,
                field,
                source_keys,
                word,
                max_frequency,
            )

    finally:
        db.close()

    # --------------------------------------------------------
    # Group pronunciation records by syllable count and spelling
    # --------------------------------------------------------

    grouped = defaultdict(lambda: defaultdict(list))

    for row in rows:
        grouped[row["SYLLABLECOUNT"]][row["WORD"]].append(row)

    groups = []

    for syllables in sorted(grouped):
        words = []

        for spelling, pronunciations in grouped[syllables].items():

            frequencies = [
                row["FREQUENCY"]
                if row["FREQUENCY"] is not None else 99
                for row in pronunciations
            ]

            frequency = min(frequencies)

            phoneme_list = sorted({
                row["PHONEMES"]
                for row in pronunciations
                if row["PHONEMES"]
            })

            words.append({
                "word": spelling,
                "frequency": frequency,
                "pronunciations": phoneme_list,
            })

        words.sort(
            key=lambda item: (item["frequency"], item["word"])
        )

        groups.append({
            "syllables": syllables,
            "words": words,
        })

    total_words = sum(
        len(group["words"]) for group in groups
    )

    return {
        "word": word,
        "near": near,
        "rhyme_type": rhyme_type,
        "total_words": total_words,
        "groups": groups,
    }


def fetch_final_rhymes(
    db,
    source_keys,
    word,
    candidate_stresses=None,
    max_frequency=None,
):
    """Fetch final-syllable matches using the indexed key table."""

    if not source_keys:
        return []

    placeholders = ",".join("?" for _ in source_keys)

    sql = f"""
        SELECT
            WORDID,
            WORD,
            FREQUENCY,
            PHONEMES,
            SYLLABLECOUNT,
            STRESSEDSYLLABLE
        FROM FINAL_RHYME_KEYS
        WHERE FINAL_RHYME_KEY IN ({placeholders})
          AND WORD <> ? COLLATE NOCASE
          AND SYLLABLECOUNT > 0
    """

    parameters = sorted(source_keys) + [word]

    if candidate_stresses is not None:
        stress_placeholders = ",".join(
            "?" for _ in candidate_stresses
        )

        sql += f"""
            AND STRESSEDSYLLABLE IN ({stress_placeholders})
        """

        parameters.extend(sorted(candidate_stresses))

    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(max_frequency)

    sql += """
        ORDER BY SYLLABLECOUNT, FREQUENCY, WORD
    """

    return db.execute(sql, parameters).fetchall()


def fetch_first_syllable_matches(
    db,
    field,
    source_keys,
    word,
    max_frequency=None,
):
    """Fetch first-syllable matches using the appropriate index."""

    if not source_keys:
        return []

    # field is selected internally, never supplied by the user.
    if field not in (
        "FIRSTSYLLABLEREVERSE",
        "FIRSTSYLLABLEREVERSEWOCONS",
    ):
        raise ValueError("Invalid first-syllable search field")

    placeholders = ",".join("?" for _ in source_keys)

    sql = f"""
        SELECT
            WORDID,
            WORD,
            FREQUENCY,
            PHONEMES,
            SYLLABLECOUNT
        FROM RHYMES
        WHERE {field} IN ({placeholders})
          AND WORD <> ? COLLATE NOCASE
          AND SYLLABLECOUNT > 0
    """

    parameters = sorted(source_keys) + [word]

    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(max_frequency)

    sql += """
        ORDER BY SYLLABLECOUNT, FREQUENCY, WORD
    """

    return db.execute(sql, parameters).fetchall()


def fetch_back_rhyme_matches(db, source_keys, word, max_frequency=None):
    """Fetch Back-rhyme matches using the indexed Back-rhyme key table."""
    if not source_keys:
        return []

    placeholders = ",".join("?" for _ in source_keys)
    sql = f"""
        SELECT WORDID, WORD, FREQUENCY, PHONEMES, SYLLABLECOUNT
        FROM BACK_RHYME_KEYS
        WHERE BACK_RHYME_KEY IN ({placeholders})
          AND WORD <> ? COLLATE NOCASE
          AND SYLLABLECOUNT > 0
    """
    parameters = sorted(source_keys) + [word]

    if max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(max_frequency)

    sql += " ORDER BY SYLLABLECOUNT, FREQUENCY, WORD"
    return db.execute(sql, parameters).fetchall()


def search_thesaurus_headwords(term, db_path=DB_PATH):
    """Find Thesaurus entries whose headword or full text contains term."""
    term = (term or "").strip()
    if not term:
        return []

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute("""
            SELECT WORDID, WORD
            FROM THESAURUS
            WHERE instr(lower(COALESCE(WORD, '')), lower(?)) > 0
               OR instr(lower(COALESCE(TEXT, '')), lower(?)) > 0
            ORDER BY WORD COLLATE NOCASE, WORDID
        """, (term, term)).fetchall()
        return [dict(row) for row in rows]
    finally:
        db.close()


def fetch_thesaurus_entry_by_number(concept_number, db_path=DB_PATH):
    """Return a Thesaurus entry by its Roget concept number."""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute("""
            SELECT WORDID, WORD, TEXT
            FROM THESAURUS
            WHERE TEXT IS NOT NULL
        """).fetchall()
        target = str(int(concept_number))
        for row in rows:
            text = (row["TEXT"] or "").lstrip()
            match = re.match(r"#\s*(\d+)\.", text)
            if match and match.group(1) == target:
                return dict(row)
        return None
    finally:
        db.close()


def fetch_thesaurus_entry(wordid, db_path=DB_PATH):
    """Return the complete Thesaurus entry identified by WORDID."""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        row = db.execute("""
            SELECT WORDID, WORD, TEXT
            FROM THESAURUS
            WHERE WORDID = ?
        """, (wordid,)).fetchone()
        return dict(row) if row else None
    finally:
        db.close()

