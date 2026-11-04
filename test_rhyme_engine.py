from rhyme_engine import search_rhymes

results = search_rhymes("time", max_frequency=5)

print("Search word:", results["word"])
print("Total results:", results["total_words"])
print()

for group in results["groups"]:
    print(f"{group['syllables']} syllables:")
    for item in group["words"]:
        print(" ", item["word"], item["frequency"])
