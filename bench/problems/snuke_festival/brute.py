def solve(text):
    data = list(map(int, text.split())); n = data[0]; a, b, c = data[1:1 + n], data[1 + n:1 + 2 * n], data[1 + 2 * n:1 + 3 * n]
    return f"{sum(1 for x in a for y in b for z in c if x < y < z)}\n"
