def solve(text):
    s = text.split()[0]
    for length in range(len(s) - 1, 0, -1):
        t = s[:length]
        if s.endswith(t) and s.find(t, 1) != -1 and s.find(t, 1) + length < len(s): return t + "\n"
    return "Just a legend\n"
