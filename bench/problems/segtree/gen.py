MAX_KINDS = ["random"]
def generate(kind, rng):
    n, q, top = (rng.randint(1, 8), rng.randint(1, 20), 10) if kind == "small" else (200000, 200000, 10**9)
    lines = [f"{n} {q}", " ".join(str(rng.randint(0, top)) for _ in range(n))]
    for _ in range(q):
        t = rng.randint(1, 3)
        if t == 2:
            l = rng.randint(1, n); r = rng.randint(l, n); lines.append(f"2 {l} {r}")
        else:
            lines.append(f"{t} {rng.randint(1, n)} {rng.randint(0, top)}")
    return "\n".join(lines) + "\n"
