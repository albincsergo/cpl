MAX_KINDS = ["all_good", "random"]
def generate(kind, rng):
    if kind == "small":
        n = rng.randint(1, 10); s = "".join(rng.choice("abc") for _ in range(n))
        goodness = "".join(rng.choice("01") for _ in range(26)); k = rng.randint(0, n)
    else:
        n = 1500; s = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(n))
        goodness = "1" * 26 if kind == "all_good" else "".join(rng.choice("01") for _ in range(26))
        k = n if kind == "all_good" else 300
    return f"{s}\n{goodness}\n{k}\n"
