"""CPL vs C++ on competitive programming problems.

    python bench/run.py verify [problem ...]   samples + random small tests against a brute force
    python bench/run.py bench [problem ...]    max-size tests: compare outputs, then time everything

Every problem in bench/problems has the same algorithm written twice: sol.cpl and sol.cpp. The C++
version is built twice: with buffered I/O equivalent to CPL's runtime (FAST_IO), and with the usual
cin/cout. Everything is compiled like on the judges (g++ -O2, cpl build -O2) and runs with an
unlimited stack, which judges allow and which recursive C++ solutions need.

gen.py makes tests: generate("small", rng) for verification and generate(kind, rng) for each kind in
MAX_KINDS. brute.py either has solve(input) -> output, or check(input, output) -> error or None for
problems that accept several answers.
"""

import importlib.util
import os
import random
import resource
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


BENCH: Path = Path(__file__).resolve().parent
ROOT: Path = BENCH.parent
PROBLEMS: Path = BENCH / "problems"
BUILD: Path = BENCH / ".build"
RUNS: int = int(os.environ.get("BENCH_RUNS", "5"))
SMALL_TESTS: int = 200


def load(path: Path):
    spec = importlib.util.spec_from_file_location(f"{path.parent.name}_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unlimitedStack() -> None:
    # set once in this process and inherited by every child; a preexec_fn would force a real fork,
    # and the child's peak memory would then include this Python interpreter's
    _, hard = resource.getrlimit(resource.RLIMIT_STACK)
    resource.setrlimit(resource.RLIMIT_STACK, (hard, hard))


# region building
def build(problem: Path) -> dict[str, Path]:
    out: Path = BUILD / problem.name
    out.mkdir(parents=True, exist_ok=True)
    binaries: dict[str, Path] = {"C++": out / "cpp_fast", "C++ cin": out / "cpp_cin", "CPL": out / "cpl"}
    commands: list[list[str]] = [
        ["g++", "-O2", "-std=gnu++17", "-DFAST_IO", "-o", str(binaries["C++"]), str(problem / "sol.cpp")],
        ["g++", "-O2", "-std=gnu++17", "-o", str(binaries["C++ cin"]), str(problem / "sol.cpp")],
        [str(ROOT / "cpl"), "build", "-O2", str(problem / "sol.cpl"), "-o", str(binaries["CPL"])],
    ]
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(f"building {problem.name} failed:\n{' '.join(command)}\n{result.stdout}{result.stderr}")
    return binaries
# endregion


# region running
def run(binary: Path, inputPath: Path, outputPath: Path) -> tuple[float, int, int]:
    # wall time, peak memory in MB and exit code. GNU time measures the memory: it forks from a tiny
    # process, while a child of this Python process would count Python's own memory too
    memoryPath: Path = outputPath.with_suffix(".memory")
    with open(inputPath, "rb") as stdin, open(outputPath, "wb") as stdout:
        start: float = time.perf_counter()
        process = subprocess.run(["/usr/bin/time", "-f", "%M", "-o", str(memoryPath), str(binary)],
                                 stdin=stdin, stdout=stdout, stderr=subprocess.DEVNULL)
        elapsed: float = time.perf_counter() - start
    lines: list[str] = memoryPath.read_text().strip().splitlines()
    return elapsed, int(lines[-1]) // 1024 if lines and lines[-1].isdigit() else 0, process.returncode


def judge(brute, text: str, output: str, expected: str | None) -> str | None:
    if hasattr(brute, "check"):
        return brute.check(text, output)
    if expected is None:
        expected = brute.solve(text)
    if output.split() != expected.split():
        return f"expected {expected.strip()[:200]!r}, got {output.strip()[:200]!r}"
    return None
# endregion


def verify(problem: Path) -> list[str]:
    binaries = build(problem)
    generator = load(problem / "gen.py")
    brute = load(problem / "brute.py")
    work: Path = BUILD / problem.name / "verify"
    work.mkdir(exist_ok=True)
    failures: list[str] = []

    tests: list[tuple[str, str, str | None]] = []
    for sample in sorted(problem.glob("sample*.in")):
        expected: Path = sample.with_suffix(".out")
        tests.append((sample.stem, sample.read_text(), expected.read_text() if expected.exists() else None))
    rng = random.Random(1)
    for index in range(SMALL_TESTS):
        tests.append((f"random {index}", generator.generate("small", rng), None))

    for name, text, expected in tests:
        inputPath: Path = work / "test.in"
        inputPath.write_text(text)
        for label, binary in binaries.items():
            outputPath: Path = work / "test.out"
            _, _, code = run(binary, inputPath, outputPath)
            problemText: str | None = f"exit code {code}" if code != 0 else judge(brute, text, outputPath.read_text(), expected)
            if problemText is not None:
                failures.append(f"{problem.name} / {name} / {label}: {problemText}\n    input: {text[:300]!r}")
                break
        if len(failures) >= 3:
            break
    return failures


def benchmark(problem: Path) -> list[dict]:
    binaries = build(problem)
    generator = load(problem / "gen.py")
    brute = load(problem / "brute.py")
    work: Path = BUILD / problem.name / "bench"
    work.mkdir(exist_ok=True)
    rows: list[dict] = []

    for kind in generator.MAX_KINDS:
        inputPath: Path = work / f"{kind}.in"
        if not inputPath.exists():
            inputPath.write_text(generator.generate(kind, random.Random(f"{problem.name}/{kind}")))

        outputs: dict[str, str] = {}
        row: dict = {"problem": problem.name, "test": kind, "input": inputPath.stat().st_size}
        for label, binary in binaries.items():
            times: list[float] = []
            memory: int = 0
            for _ in range(RUNS):
                elapsed, peak, code = run(binary, inputPath, work / f"{kind}.{label.replace(' ', '_')}.out")
                if code != 0:
                    raise SystemExit(f"{problem.name}/{kind}: {label} exited with {code}")
                times.append(elapsed)
                memory = max(memory, peak)
            outputs[label] = (work / f"{kind}.{label.replace(' ', '_')}.out").read_text()
            row[label] = (min(times), memory)

        # outputs must match exactly, or (for problems with several right answers) both pass the checker
        for label in ["C++ cin", "CPL"]:
            if outputs[label] != outputs["C++"]:
                if not hasattr(brute, "check"):
                    raise SystemExit(f"{problem.name}/{kind}: {label} disagrees with C++")
                text: str = inputPath.read_text()
                for name in ["C++", label]:
                    error: str | None = brute.check(text, outputs[name])
                    if error is not None:
                        raise SystemExit(f"{problem.name}/{kind}: {name} is wrong: {error}")
        rows.append(row)
    return rows


def main(arguments: list[str]) -> int:
    if not arguments or arguments[0] not in ["verify", "bench"]:
        print(__doc__)
        return 2
    unlimitedStack()
    problems: list[Path] = sorted(path for path in PROBLEMS.iterdir() if (path / "sol.cpl").exists())
    if arguments[1:]:
        problems = [path for path in problems if path.name in arguments[1:]]

    if arguments[0] == "verify":
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(verify, problems))
        failures: list[str] = [failure for result in results for failure in result]
        for problem, result in zip(problems, results):
            print(f"  {'ok  ' if not result else 'FAIL'}  {problem.name}")
        for failure in failures:
            print(failure)
        print(f"\n{len(problems) - sum(1 for result in results if result)} of {len(problems)} problems verified "
              f"({SMALL_TESTS} random tests each, plus samples)")
        return 1 if failures else 0

    print("| Problem | Test | C++ (fast I/O) | C++ (cin) | CPL | CPL vs C++ |")
    print("|---|---|---|---|---|---|")
    for problem in problems:
        for row in benchmark(problem):
            cpp, cin, cpl = row["C++"], row["C++ cin"], row["CPL"]
            ratio: float = cpp[0] / cpl[0]
            verdict: str = f"{ratio:.2f}x faster" if ratio >= 1 else f"{1 / ratio:.2f}x slower"
            print(f"| {row['problem']} | {row['test']} | {cpp[0] * 1000:.0f} ms, {cpp[1]} MB | {cin[0] * 1000:.0f} ms, {cin[1]} MB "
                  f"| {cpl[0] * 1000:.0f} ms, {cpl[1]} MB | {verdict} |", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
