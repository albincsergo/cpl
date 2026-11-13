MAX_KINDS = ["random"]
def generate(kind, rng):
    n, W = (rng.randint(1, 8), rng.randint(1, 30)) if kind == "small" else (100, 100000)
    return f"{n} {W}\n" + "".join(f"{rng.randint(1, W if kind == 'small' else 3000)} {rng.randint(1, 10**9)}\n" for _ in range(n))
