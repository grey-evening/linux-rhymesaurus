#!/usr/bin/env python3

import argparse

from rhyme_engine import (
    FREQUENCY_CATEGORIES,
    WordNotFoundError,
    NoUsablePronunciationError,
    search_rhymes,
)


def main():
    parser = argparse.ArgumentParser(
        description="Find exact and near rhymes using Rhymesaurus data."
    )

    parser.add_argument("word", help="Word to find rhymes for")

    parser.add_argument(
        "--near",
        action="store_true",
        help="Find near rhymes (one phoneme-token edit away)",
    )

    parser.add_argument(
        "--max-frequency",
        type=int,
        choices=FREQUENCY_CATEGORIES,
        help="Exclude words with a higher frequency category",
    )

    args = parser.parse_args()

    try:
        results = search_rhymes(
            args.word,
            near=args.near,
            max_frequency=args.max_frequency,
        )

    except WordNotFoundError:
        print(f"Word not found: {args.word}")
        return

    except NoUsablePronunciationError:
        print("No usable pronunciation keys found.")
        return

    mode = "near rhymes" if results["near"] else "rhymes"

    print(
        f"\n{results['total_words']:,} {mode} "
        f"for {results['word'].upper()}:\n"
    )

    for group in results["groups"]:
        syllables = group["syllables"]
        print(f"\n{syllables} syllable{'s' if syllables != 1 else ''}")
        print("-" * 88)

        for item in group["words"]:
            pronunciations = " / ".join(item["pronunciations"])

            print(
                f"{item['word']:<25} [{item['frequency']}]  "
                f"{pronunciations}"
            )


if __name__ == "__main__":
    main()
