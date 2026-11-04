#!/usr/bin/env python3

import argparse
import sqlite3
import textwrap
from pathlib import Path

DB_PATH = Path(__file__).with_name("rhymesaurus.sqlite3")
WIDTH = 88


def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def lookup(word):
    with connect() as db:
        return db.execute("""
            SELECT WORDID, WORD, USAGE, DEFINITION
            FROM DICTIONARY
            WHERE LOWER(WORDL) = LOWER(?)
            ORDER BY WORDID
        """, (word.strip(),)).fetchall()


def prefix_search(prefix, limit=50):
    with connect() as db:
        return db.execute("""
            SELECT WORDL, MIN(WORD) AS WORD, COUNT(*) AS ENTRIES
            FROM DICTIONARY
            WHERE LOWER(WORDL) LIKE LOWER(?) || '%'
            GROUP BY WORDL
            ORDER BY WORDL
            LIMIT ?
        """, (prefix.strip(), limit)).fetchall()


def display(word, entries):
    if not entries:
        print(f"\nNo dictionary entry found for '{word}'.")
        return

    print(f"\n{entries[0]['WORD'].upper()}")
    print("=" * WIDTH)
    print(f"{len(entries)} entries\n")

    for number, entry in enumerate(entries, 1):
        usage = entry["USAGE"] or "—"
        definition = (entry["DEFINITION"] or "").strip()

        print(f"{number}.  {usage}")
        print(textwrap.fill(
            definition,
            width=WIDTH,
            initial_indent="    ",
            subsequent_indent="    "
        ))
        print()


def browse_prefix(prefix, limit):
    results = prefix_search(prefix, limit)

    if not results:
        print(f"\nNo words found beginning with '{prefix}'.")
        return

    print(f"\nWords beginning with '{prefix}'")
    print("=" * WIDTH)

    for number, row in enumerate(results, 1):
        print(
            f"{number:>3}.  {row['WORDL']:<30} "
            f"{row['ENTRIES']:>4} entries"
        )

    print(f"\n{len(results)} words shown.")

    selection = input(
        "\nEnter a number to view its definition, "
        "or press Enter to return: "
    ).strip()

    if not selection:
        return

    try:
        number = int(selection)
    except ValueError:
        print("Please enter a valid number.")
        return

    if not 1 <= number <= len(results):
        print("That number is outside the displayed range.")
        return

    word = results[number - 1]["WORDL"]
    display(word, lookup(word))


def main():
    parser = argparse.ArgumentParser(
        description="Look up words in the Rhymesaurus dictionary."
    )
    parser.add_argument(
        "word",
        help="Word to look up or prefix to search"
    )
    parser.add_argument(
        "--prefix",
        action="store_true",
        help="Search for words beginning with the supplied text"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum prefix results (default: 50)"
    )

    args = parser.parse_args()

    if args.prefix:
        browse_prefix(args.word, args.limit)
    else:
        display(args.word, lookup(args.word))


if __name__ == "__main__":
    main()
