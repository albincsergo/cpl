MAX_KINDS = ["random", "long_cycle", "dag_path"]
def generate(kind, rng):
    if kind == "small":
        n = rng.randint(1, 7); m = rng.randint(1, 12)
        edges = [(rng.randrange(n), rng.randrange(n)) for _ in range(m)]
    else:
        n = m = 500000
        if kind == "random":
            edges = [(rng.randrange(n), rng.randrange(n)) for _ in range(m)]
        elif kind == "long_cycle":
            # one SCC with every vertex: the recursion goes 500000 levels deep
            perm = list(range(n)); rng.shuffle(perm)
            edges = [(perm[i], perm[(i + 1) % n]) for i in range(n)]
        else:
            # a single path: 500000 components and maximal recursion depth
            edges = [(i, i + 1) for i in range(n - 1)] + [(n - 1, n - 1)]
    return f"{n} {len(edges)}\n" + "".join(f"{a} {b}\n" for a, b in edges)
