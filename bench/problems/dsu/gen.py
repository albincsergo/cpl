MAX_KINDS = ["random", "chain"]
def generate(kind, rng):
    n, q = (rng.randint(1, 8), rng.randint(1, 20)) if kind == "small" else (200000, 200000)
    lines = [f"{n} {q}"]
    for i in range(q):
        if kind == "chain" and i < n - 1 and i % 2 == 0:
            lines.append(f"0 {i // 2} {i // 2 + 1}")   # builds one long path first
        else:
            lines.append(f"{rng.randint(0, 1)} {rng.randrange(n)} {rng.randrange(n)}")
    return "\n".join(lines) + "\n"
