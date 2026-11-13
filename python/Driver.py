import os
import shutil
import subprocess
import sys
import tempfile
from ctypes import CFUNCTYPE, c_int
from pathlib import Path

from llvmlite import ir
import llvmlite.binding as llvm

from AST import Program
from Compiler import Compiler
from Lexer import Lexer
from Parser import Parser
from Target import initializeLLVM, targetMachine


REPO_ROOT: Path = Path(__file__).resolve().parent.parent
RUNTIME_SOURCE: Path = REPO_ROOT / "runtime" / "cpl_runtime.c"
CACHE_DIR: Path = REPO_ROOT / "build" / "runtime"


class CompileFailure(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


# region compiling
def parse(source: str) -> Program:
    parser: Parser = Parser(Lexer(source))
    program: Program = parser.parseProgram()
    if parser.errors:
        raise CompileFailure(parser.errors)
    return program


def compileProgram(program: Program) -> ir.Module:
    compiler: Compiler = Compiler()
    compiler.compile(program)
    if compiler.errors:
        raise CompileFailure(compiler.errors)

    return compiler.module


def compileSource(source: str) -> ir.Module:
    return compileProgram(parse(source))


def optimize(module: ir.Module, optLevel: int, linkRuntime: bool = True) -> llvm.ModuleRef:
    initializeLLVM()
    parsed: llvm.ModuleRef = llvm.parse_assembly(str(module))
    parsed.verify()

    # whole-program optimization: with the runtime linked in as bitcode, LLVM can inline input
    # parsing, printing and string access straight into the program's loops
    if linkRuntime and runtimeBitcode() is not None:
        runtime: llvm.ModuleRef = llvm.parse_bitcode(runtimeBitcode().read_bytes())
        runtime.triple = parsed.triple
        runtime.data_layout = parsed.data_layout
        parsed.link_in(runtime)
        # only main has to stay visible; everything else may be inlined or dropped
        for function in parsed.functions:
            if not function.is_declaration and function.name != "main":
                function.linkage = "internal"
        for variable in parsed.global_variables:
            if not variable.is_declaration:
                variable.linkage = "internal"

    if optLevel > 0:
        passBuilder = llvm.create_pass_builder(targetMachine(optLevel), llvm.create_pipeline_tuning_options(speed_level=optLevel))
        passBuilder.getModulePassManager().run(parsed, passBuilder)
    return parsed
# endregion


# region runtime library
def findCCompiler() -> str:
    for candidate in [os.environ.get("CC"), "cc", "gcc", "clang"]:
        if candidate and shutil.which(candidate):
            return candidate
    raise CompileFailure(["~~~ ERROR: no C compiler found (tried $CC, cc, gcc and clang); CPL needs one for its runtime library"])


def findClang() -> str | None:
    candidates: list[str | None] = [os.environ.get("CPL_CLANG"), "clang"] + [f"clang-{version}" for version in range(22, 10, -1)]
    for candidate in candidates:
        if candidate and shutil.which(candidate):
            return candidate
    return None


def buildCached(output: Path, command: list[str]) -> bool:
    # builds output from the runtime source unless an up-to-date copy is cached
    if output.exists() and output.stat().st_mtime >= RUNTIME_SOURCE.stat().st_mtime:
        return True
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temporary: Path = output.with_name(f".{output.name}.{os.getpid()}")
    result = subprocess.run(command + ["-o", str(temporary), str(RUNTIME_SOURCE)], capture_output=True, text=True)
    if result.returncode != 0:
        return False
    temporary.replace(output)
    return True


_bitcodeChecked: bool = False
_bitcode: Path | None = None


def runtimeBitcode() -> Path | None:
    # the runtime as LLVM bitcode, if clang is available; otherwise it gets linked as a normal library
    global _bitcodeChecked, _bitcode
    if not _bitcodeChecked:
        _bitcodeChecked = True
        clang: str | None = findClang()
        output: Path = CACHE_DIR / "cpl_runtime.bc"
        if clang is not None and buildCached(output, [clang, "-O2", "-std=gnu11", "-fPIC", "-emit-llvm", "-c"]):
            try:
                llvm.parse_bitcode(output.read_bytes())
                _bitcode = output
            except RuntimeError:
                # bitcode from a newer clang than llvmlite's LLVM can't be read
                _bitcode = None
    return _bitcode


def runtimeLibrary(shared: bool) -> Path:
    output: Path = CACHE_DIR / ("libcpl_runtime.so" if shared else "cpl_runtime.o")
    command: list[str] = [findCCompiler(), "-O2", "-std=gnu11", "-fPIC", "-pthread"] + (["-shared"] if shared else ["-c"])
    if not buildCached(output, command):
        result = subprocess.run(command + ["-o", "/dev/null", str(RUNTIME_SOURCE)], capture_output=True, text=True)
        raise CompileFailure([f"~~~ ERROR: building the runtime library failed:\n{result.stderr}"])
    return output
# endregion


# region running
def runJit(module: ir.Module, optLevel: int) -> int:
    optimized: llvm.ModuleRef = optimize(module, optLevel)
    if runtimeBitcode() is None:
        llvm.load_library_permanently(str(runtimeLibrary(shared=True)))

    engine = llvm.create_mcjit_compiler(optimized, targetMachine(optLevel))
    engine.finalize_object()
    engine.run_static_constructors()

    entry: int = engine.get_function_address("main")
    sys.stdout.flush()
    return CFUNCTYPE(c_int)(entry)()


def buildExecutable(module: ir.Module, output: Path, optLevel: int) -> None:
    optimized: llvm.ModuleRef = optimize(module, optLevel)
    objectCode: bytes = targetMachine(optLevel).emit_object(optimized)

    with tempfile.TemporaryDirectory() as directory:
        objectPath: Path = Path(directory) / "program.o"
        objectPath.write_bytes(objectCode)

        runtime: list[str] = [] if runtimeBitcode() is not None else [str(runtimeLibrary(shared=False))]
        command: list[str] = [findCCompiler(), str(objectPath), *runtime, "-pthread", "-lm", "-o", str(output)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise CompileFailure([f"~~~ ERROR: linking failed:\n{result.stderr}"])
# endregion
