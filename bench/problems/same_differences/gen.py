MAX_KINDS = ["many_tests", "one_big_test"]
def generate(kind, rng):
    if kind == "small":
        tests = [rng.randint(1, 8) for _ in range(rng.randint(1, 4))]
    elif kind == "many_tests":
        tests = [20] * 10000
    else:
        tests = [200000]
    lines = [str(len(tests))]
    for n in tests:
        lines.append(str(n))
        lines.append(" ".join(str(rng.randint(max(1, i + 1 - 3), min(n, i + 1 + 3)) if kind == "one_big_test" else rng.randint(1, n)) for i in range(n)))
    return "\n".join(lines) + "\n"
