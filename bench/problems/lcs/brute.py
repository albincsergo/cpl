from functools import lru_cache
def check(text, output):
    s, t = text.split()[:2]; answer = output.strip()
    @lru_cache(None)
    def best(i, j):
        if i == len(s) or j == len(t): return 0
        return best(i + 1, j + 1) + 1 if s[i] == t[j] else max(best(i + 1, j), best(i, j + 1))
    def isSubsequence(x, y):
        it = iter(y); return all(c in it for c in x)
    if len(answer) != best(0, 0): return f"length {len(answer)}, expected {best(0, 0)}"
    if not (isSubsequence(answer, s) and isSubsequence(answer, t)): return f"{answer!r} is not a common subsequence"
    return None
