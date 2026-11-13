MAX_KINDS = ["random"]
MOD = 998244353
def generate(kind, rng):
    n, q = (rng.randint(1, 8), rng.randint(1, 20)) if kind == "small" else (500000, 500000)
    lines = [f"{n} {q}", " ".join(str(rng.randrange(MOD)) for _ in range(n))]
    for _ in range(q):
        l = rng.randrange(n); r = rng.randint(l + 1, n)
        if rng.randint(0, 1) == 0: lines.append(f"0 {l} {r} {rng.randint(1, MOD - 1)} {rng.randrange(MOD)}")
        else: lines.append(f"1 {l} {r}")
    return "\n".join(lines) + "\n"
