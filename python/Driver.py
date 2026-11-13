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


def optimize(module: ir.Module, optLevel: int) -> llvm.ModuleRef:
    initializeLLVM()
    parsed: llvm.ModuleRef = llvm.parse_assembly(str(module))
    parsed.verify()

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


def runtimeLibrary(shared: bool) -> Path:
    # the runtime is plain C; build it once and rebuild whenever the source changes
    output: Path = CACHE_DIR / ("libcpl_runtime.so" if shared else "cpl_runtime.o")
    if output.exists() and output.stat().st_mtime >= RUNTIME_SOURCE.stat().st_mtime:
        return output

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temporary: Path = output.with_name(f".{output.name}.{os.getpid()}")
    command: list[str] = [findCCompiler(), "-O2", "-std=gnu11", "-fPIC", "-pthread"]
    command += ["-shared", "-o", str(temporary), str(RUNTIME_SOURCE), "-lm"] if shared else ["-c", "-o", str(temporary), str(RUNTIME_SOURCE)]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise CompileFailure([f"~~~ ERROR: building the runtime library failed:\n{result.stderr}"])
    temporary.replace(output)
    return output
# endregion


# region running
def runJit(module: ir.Module, optLevel: int) -> int:
    optimized: llvm.ModuleRef = optimize(module, optLevel)
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

        command: list[str] = [findCCompiler(), str(objectPath), str(runtimeLibrary(shared=False)), "-pthread", "-lm", "-o", str(output)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise CompileFailure([f"~~~ ERROR: linking failed:\n{result.stderr}"])
# endregion
