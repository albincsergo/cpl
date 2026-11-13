def solve(text):
    s = text.split()[0]
    return f"{len({s[i:j] for i in range(len(s)) for j in range(i + 1, len(s) + 1)})}\n"
