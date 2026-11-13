from itertools import product
def check(text, output):
    data = text.split(); n = int(data[0]); p = list(map(float, data[1:1 + n])); total = 0.0
    for heads in product([0, 1], repeat=n):
        if sum(heads) * 2 > n:
            q = 1.0
            for h, x in zip(heads, p): q *= x if h else 1 - x
            total += q
    return None if abs(float(output) - total) <= 1e-9 else f"{output.strip()} but expected {total}"
