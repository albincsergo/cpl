MAX_KINDS = ["random", "small_values"]
def generate(kind, rng):
    n, top = (rng.randint(1, 8), 6) if kind == "small" else (100000, 10**9 if kind == "random" else 1000)
    return f"{n}\n" + "\n".join(" ".join(str(rng.randint(1, top)) for _ in range(n)) for _ in range(3)) + "\n"
