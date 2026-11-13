MAX_KINDS = ["random", "few_letters", "all_a"]
def generate(kind, rng):
    if kind == "small":
        return "".join(rng.choice("ab" if rng.random() < 0.5 else "abc") for _ in range(rng.randint(1, 12))) + "\n"
    n = 500000
    if kind == "random": return "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(n)) + "\n"
    if kind == "few_letters": return "".join(rng.choice("ab") for _ in range(n)) + "\n"
    return "a" * n + "\n"
