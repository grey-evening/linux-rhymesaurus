#!/usr/bin/env python3

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).with_name("rhymesaurus.sqlite3")


def main():
    parser = argparse.ArgumentParser(
        description="Find rhyming words using the Rhymesaurus database."
    )

    parser.add_argument(
        "word",
        help="Word to find rhymes for"
    )

    parser.add_argument(
        "--max-frequency",
        type=int,
        choices=[1, 2, 5, 9, 10],
        help="Exclude words above this frequency category"
    )

    args = parser.parse_args()

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    # Find all pronunciations of the requested word.
    source = db.execute("""
        SELECT WORD, PHONEMES, REVERSEPHONEMES
        FROM RHYMES
        WHERE WORD = ? COLLATE NOCASE
    """, (args.word,)).fetchall()

    if not source:
        print(f"No pronunciation found for: {args.word}")
        db.close()
        return

    # Derive rhyme keys from the reversed phoneme sequences.
    keys = set()

    for row in source:
        tokens = row["REVERSEPHONEMES"].split()

        for i, token in enumerate(tokens):
            if token.endswith("1"):
                keys.add(" ".join(tokens[:i + 1]))
                break

    if not keys:
        print(f"No primary-stressed rhyme key found for: {args.word}")
        db.close()
        return

    # Search the indexed rhyme-key table.
    placeholders = ",".join("?" for _ in keys)

    sql = f"""
        SELECT WORD, FREQUENCY
        FROM RHYME_KEYS
        WHERE RHYME_KEY IN ({placeholders})
          AND WORD <> ? COLLATE NOCASE
    """

    parameters = list(keys) + [args.word]

    if args.max_frequency is not None:
        sql += " AND FREQUENCY <= ?"
        parameters.append(args.max_frequency)

    sql += " ORDER BY FREQUENCY, WORD"

    rows = db.execute(sql, parameters).fetchall()

    # Group results by spelling.
    results = defaultdict(list)

    for row in rows:
        results[row["WORD"]].append(row)

    print(f"\nRHYMES FOR: {args.word.upper()}")
    print("=" * 60)

    print("\nPronunciations:")
    for row in source:
        print(f"  {row['PHONEMES']}")

    print(f"\nRhyme keys: {', '.join(sorted(keys))}")
    print(f"\nFound {len(results)} rhyming words:\n")

    # Sort words by their best (lowest) frequency category.
    def sort_key(word):
        frequencies = [
            row["FREQUENCY"]
            for row in results[word]
            if row["FREQUENCY"] is not None
        ]

        frequency = min(frequencies) if frequencies else 99
        return frequency, word

    for word in sorted(results, key=sort_key):
        word_rows = results[word]

        frequencies = [
            row["FREQUENCY"]
            for row in word_rows
            if row["FREQUENCY"] is not None
        ]

        frequency = min(frequencies) if frequencies else "?"

        # Retrieve pronunciations from the original RHYMES table.
        pronunciations = db.execute("""
            SELECT DISTINCT PHONEMES
            FROM RHYMES
            WHERE WORD = ? COLLATE NOCASE
              AND PHONEMES IS NOT NULL
            ORDER BY PHONEMES
        """, (word,)).fetchall()

        pronunciation_text = "; ".join(
            row["PHONEMES"] for row in pronunciations
        )

        print(f"{word:<25} [{frequency}]  {pronunciation_text}")

    db.close()


if __name__ == "__main__":
    main()
