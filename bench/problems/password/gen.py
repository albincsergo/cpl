MAX_KINDS = ["periodic", "random", "all_a"]
def generate(kind, rng):
    if kind == "small": return "".join(rng.choice("ab") for _ in range(rng.randint(1, 12))) + "\n"
    n = 1000000
    if kind == "periodic":
        unit = "".join(rng.choice("ab") for _ in range(7)); return (unit * (n // 7 + 1))[:n] + "\n"
    if kind == "random": return "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(n)) + "\n"
    return "a" * n + "\n"
