#!/usr/bin/env python3

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

        if not source_rows:
            raise WordNotFoundError(word)

        # ----------------------------------------------------
        # Perfect rhymes
        # ----------------------------------------------------

        if rhyme_type == "perfect":

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
