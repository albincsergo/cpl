MAX_KINDS = ["random", "two_letters"]
def generate(kind, rng):
    if kind == "small":
        return "".join(rng.choice("abc") for _ in range(rng.randint(1, 8))) + "\n" + "".join(rng.choice("abc") for _ in range(rng.randint(1, 8))) + "\n"
    letters = "abcdefghijklmnopqrstuvwxyz" if kind == "random" else "ab"
    return "".join(rng.choice(letters) for _ in range(3000)) + "\n" + "".join(rng.choice(letters) for _ in range(3000)) + "\n"
