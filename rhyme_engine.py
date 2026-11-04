#!/usr/bin/env python3

import sqlite3
from collections import defaultdict
from pathlib import Path


DB_PATH = Path(__file__).with_name("rhymesaurus.sqlite3")

FREQUENCY_CATEGORIES = (1, 2, 5, 9, 10)

RHYME_TYPES = ("perfect", "light", "final_syllable")


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
    """
    Return the final vowel and following consonants of a pronunciation.

    The phonemes are reversed, so this consists of the initial consonants
    encountered, followed by the first vowel. Stress digits are removed.
    """
    if not reversed_phonemes:
        return None

    key = []

    for token in reversed_phonemes.split():
        key.append(token.rstrip("012"))

        if token.endswith(("0", "1", "2")):
            return tuple(key)

    return None


def ensure_final_rhyme_keys(db):
    """
    Create and populate the indexed final-rhyme table if necessary.

    This is a one-time operation. Once populated, subsequent searches
    use the index rather than scanning all RHYMES records.
    """

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

    count = db.execute("""
        SELECT COUNT(*) FROM FINAL_RHYME_KEYS
    """).fetchone()[0]

    if count:
        return

    source_rows = db.execute("""
        SELECT
            WORDID,
            WORD,
            REVERSEPHONEMES,
            FREQUENCY,
            PHONEMES,
            STRESSEDSYLLABLE,
            SYLLABLECOUNT
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
            WORDID,
            WORD,
            FINAL_RHYME_KEY,
            FREQUENCY,
            PHONEMES,
            STRESSEDSYLLABLE,
            SYLLABLECOUNT
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, entries)

    db.commit()

    print(
        f"Built FINAL_RHYME_KEYS: {len(entries):,} pronunciation records."
    )


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
    """
    Return words beginning with the supplied spelling prefix.

    Results are alphabetical and case-insensitive.
    """

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
    Search for perfect, light, or final-syllable rhymes.

    rhyme_type:
        perfect:
            Exact rhyme from the primary-stressed vowel onward.

        light:
            Same final rhyme sound, opposite final/penultimate
            primary-stress position.

        final_syllable:
            Same final rhyme sound, regardless of stress.

    near:
        For perfect rhymes only, also include keys one phoneme edit away.
    """

    rhyme_type = rhyme_type.lower().replace("-", "_").replace(" ", "_")

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
                REVERSEPHONEMES,
                STRESSEDSYLLABLE
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

                rows = db.execute(
                    sql, parameters
                ).fetchall()

        # ----------------------------------------------------
        # Light and Final Syllable rhymes
        # ----------------------------------------------------

        else:

            # Build the auxiliary table on the first search.
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
