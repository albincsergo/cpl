def solve(text):
    s, goodness, k = text.split(); k = int(k); found = set()
    for i in range(len(s)):
        for j in range(i + 1, len(s) + 1):
            t = s[i:j]
            if sum(goodness[ord(c) - 97] == "0" for c in t) <= k: found.add(t)
    return f"{len(found)}\n"
