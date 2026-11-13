"""Runs the CPL test suite.

    python tests/run_tests.py            run everything with the JIT
    python tests/run_tests.py --native   also build every program as an executable and run that
    python tests/run_tests.py hello maps only run tests whose name contains one of these words

Test layout:
    tests/programs/name.cpl         must compile and run; stdout must equal name.out (if it exists),
                                    stdin comes from name.in (if it exists), the exit code must equal
                                    name.code (default 0)
    tests/errors/name.cpl           must fail to compile; every line of name.err must appear in the errors
    tests/runtime_errors/name.cpl   must compile, then stop with exit code 1; every line of name.err
                                    must appear in stderr
    examples/name.cpl               treated like tests/programs
"""

import resource
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT: Path = Path(__file__).resolve().parent.parent
MAIN: Path = ROOT / "python" / "main.py"
TIMEOUT: int = 60
# every test runs with this much address space, which also exercises the runtime's fallbacks for
# small limits; it keeps the stack overflow test from filling a quarter of the machine's memory
ADDRESS_SPACE_LIMIT: int = 4 << 30


def readOptional(path: Path, default: str = "") -> str:
    return path.read_text() if path.exists() else default


def runCpl(arguments: list[str], stdin: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(MAIN), *arguments], input=stdin, capture_output=True, text=True, timeout=TIMEOUT)


def runProgram(source: Path, native: bool) -> subprocess.CompletedProcess:
    stdin: str = readOptional(source.with_suffix(".in"))
    if not native:
        return runCpl(["run", str(source)], stdin)

    with tempfile.TemporaryDirectory() as directory:
        executable: Path = Path(directory) / source.stem
        built: subprocess.CompletedProcess = runCpl(["build", str(source), "-o", str(executable)], "")
        if built.returncode != 0:
            return built
        return subprocess.run([str(executable)], input=stdin, capture_output=True, text=True, timeout=TIMEOUT)


def checkProgram(source: Path, native: bool) -> str | None:
    result: subprocess.CompletedProcess = runProgram(source, native)
    expectedCode: int = int(readOptional(source.with_suffix(".code"), "0").strip())
    expectedOutput: Path = source.with_suffix(".out")

    if result.returncode != expectedCode:
        return f"exit code {result.returncode}, expected {expectedCode}\n{result.stderr}"
    if expectedOutput.exists() and result.stdout != expectedOutput.read_text():
        return diff(expectedOutput.read_text(), result.stdout)
    return None


def checkError(source: Path, native: bool, runtime: bool) -> str | None:
    result: subprocess.CompletedProcess = runProgram(source, native) if runtime else runCpl(["check", str(source)], "")
    if result.returncode != 1:
        return f"exit code {result.returncode}, expected 1\nstdout: {result.stdout}\nstderr: {result.stderr}"

    for expected in readOptional(source.with_suffix(".err")).splitlines():
        if expected.strip() and expected.strip() not in result.stderr:
            return f"missing error: {expected.strip()}\ngot:\n{result.stderr}"
    return None


def diff(expected: str, actual: str) -> str:
    expectedLines: list[str] = expected.splitlines()
    actualLines: list[str] = actual.splitlines()
    for index in range(max(len(expectedLines), len(actualLines))):
        want: str = expectedLines[index] if index < len(expectedLines) else "<nothing>"
        got: str = actualLines[index] if index < len(actualLines) else "<nothing>"
        if want != got:
            return f"line {index + 1}:\n  expected: {want!r}\n  got:      {got!r}"
    return "output differs in trailing whitespace or newlines"


def collectTests(filters: list[str]) -> list[tuple[str, Path]]:
    tests: list[tuple[str, Path]] = []
    for kind, directory in [("program", ROOT / "tests" / "programs"), ("program", ROOT / "examples"),
                            ("error", ROOT / "tests" / "errors"), ("runtime", ROOT / "tests" / "runtime_errors")]:
        for source in sorted(directory.glob("*.cpl")):
            name: str = f"{directory.name}/{source.stem}"
            if not filters or any(word in name for word in filters):
                tests.append((kind, source))
    return tests


def main(arguments: list[str]) -> int:
    _, hardLimit = resource.getrlimit(resource.RLIMIT_AS)
    if hardLimit == resource.RLIM_INFINITY or hardLimit > ADDRESS_SPACE_LIMIT:
        resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_SPACE_LIMIT, hardLimit))

    native: bool = "--native" in arguments
    filters: list[str] = [argument for argument in arguments if not argument.startswith("--")]
    tests: list[tuple[str, Path]] = collectTests(filters)

    modes: list[bool] = [False, True] if native else [False]
    jobs: list[tuple[str, Path, bool]] = [(kind, source, mode) for mode in modes for kind, source in tests
                                          if not (mode and kind == "error")]

    def run(job: tuple[str, Path, bool]) -> tuple[str, str | None]:
        kind, source, isNative = job
        label: str = f"{source.parent.name}/{source.stem}" + (" (native)" if isNative else "")
        try:
            if kind == "program":
                return label, checkProgram(source, isNative)
            return label, checkError(source, isNative, runtime=kind == "runtime")
        except subprocess.TimeoutExpired:
            return label, f"timed out after {TIMEOUT} seconds"

    # build the runtime library once up front, so parallel tests don't race to create it
    runCpl(["check", str(ROOT / "tests" / "programs" / "hello.cpl")], "")

    failures: int = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for label, problem in pool.map(run, jobs):
            if problem is None:
                print(f"  ok    {label}")
            else:
                failures += 1
                print(f"  FAIL  {label}\n" + "\n".join("        " + line for line in problem.splitlines()))

    print(f"\n{len(jobs) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
