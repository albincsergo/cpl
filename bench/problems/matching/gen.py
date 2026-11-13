MAX_KINDS = ["all_compatible", "random"]
def generate(kind, rng):
    n = rng.randint(1, 6) if kind == "small" else 21
    probability = 1.0 if kind == "all_compatible" else 0.7
    return f"{n}\n" + "".join(" ".join("1" if rng.random() < probability else "0" for _ in range(n)) + "\n" for _ in range(n))
