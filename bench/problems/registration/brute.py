def solve(text):
    data = text.split(); n = int(data[0]); seen = {}; out = []
    for name in data[1:1 + n]:
        times = seen.get(name, 0)
        out.append("OK" if times == 0 else f"{name}{times}"); seen[name] = times + 1
    return "".join(s + "\n" for s in out)
