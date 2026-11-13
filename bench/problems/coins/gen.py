MAX_KINDS = ["random"]
def generate(kind, rng):
    n = rng.choice([1, 3, 5, 7]) if kind == "small" else 2999
    return f"{n}\n" + " ".join(f"0.{rng.randint(1, 99):02d}" for _ in range(n)) + "\n"
