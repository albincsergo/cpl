MAX_KINDS = ["random", "long_path"]
def generate(kind, rng):
    if kind == "small":
        n = rng.randint(2, 7); m = rng.randint(0, 12)
        edges = [(rng.randint(1, n), rng.randint(1, n), rng.randint(1, 5)) for _ in range(m)]
    elif kind == "random":
        n = m = 100000
        edges = [(rng.randint(1, n), rng.randint(1, n), rng.randint(1, 10**6)) for _ in range(m)]
    else:
        # a shuffled path plus random shortcuts: the answer goes through many vertices
        n = m = 100000; order = list(range(2, n)); rng.shuffle(order); order = [1] + order + [n]
        edges = [(order[i], order[i + 1], rng.randint(1, 10)) for i in range(n - 1)]
        edges += [(rng.randint(1, n), rng.randint(1, n), rng.randint(10**5, 10**6)) for _ in range(m - (n - 1))]
    return f"{n} {len(edges)}\n" + "".join(f"{a} {b} {w}\n" for a, b, w in edges)
