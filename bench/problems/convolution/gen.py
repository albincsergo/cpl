MAX_KINDS = ["random"]
MOD = 998244353
def generate(kind, rng):
    n, m = (rng.randint(1, 10), rng.randint(1, 10)) if kind == "small" else (524288, 524288)
    return f"{n} {m}\n" + " ".join(str(rng.randrange(MOD)) for _ in range(n)) + "\n" + " ".join(str(rng.randrange(MOD)) for _ in range(m)) + "\n"
