MAX_KINDS = ["random"]
def generate(kind, rng):
    n, q = (rng.randint(1, 8), rng.randint(1, 20)) if kind == "small" else (500000, 500000)
    lines = [f"{n} {q}", " ".join(str(rng.randint(0, 10**9)) for _ in range(n))]
    for _ in range(q):
        if rng.randint(0, 1) == 0:
            lines.append(f"0 {rng.randrange(n)} {rng.randint(0, 10**9)}")
        else:
            l = rng.randrange(n); r = rng.randint(l + 1, n); lines.append(f"1 {l} {r}")
    return "\n".join(lines) + "\n"
