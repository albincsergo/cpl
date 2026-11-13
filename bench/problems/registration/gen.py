MAX_KINDS = ["few_names", "distinct"]
def generate(kind, rng):
    if kind == "small":
        n = rng.randint(1, 15); names = [rng.choice(["a", "b", "ab", "a1"[0] + "b"]) for _ in range(n)]
    elif kind == "few_names":
        n = 100000; pool = ["".join(rng.choice("abc") for _ in range(rng.randint(5, 32))) for _ in range(300)]
        names = [rng.choice(pool) for _ in range(n)]
    else:
        n = 100000; names = ["".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(32)) for _ in range(n)]
    return f"{n}\n" + "".join(name + "\n" for name in names)
