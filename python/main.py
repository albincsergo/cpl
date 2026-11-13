import json
import os
import time
from pathlib import Path
from ctypes import CFUNCTYPE, c_int

from llvmlite import ir
import llvmlite.binding as llvm

from AST import Program
from Compiler import Compiler
from Lexer import Lexer
from Parser import Parser


def envFlag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# resolve paths relative to the repo root so the script works from any directory
BASE_DIR: Path = Path(__file__).resolve().parent
REPO_ROOT: Path = BASE_DIR.parent
DEBUG_DIR: Path = REPO_ROOT / "debug"

LEXER_DEBUG: bool = envFlag("CPL_LEXER_DEBUG", False)
PARSER_DEBUG: bool = envFlag("CPL_PARSER_DEBUG", False)
COMPILER_DEBUG: bool = envFlag("CPL_COMPILER_DEBUG", False)
RUN_PROGRAM: bool = envFlag("CPL_RUN_PROGRAM", True)


if __name__ == "__main__":
    sourcePath = Path(os.environ.get("CPL_SOURCE", str(REPO_ROOT / "tests" / "test.cpl")))
    with open(sourcePath, "r") as f:
        source: str = f.read()

    if LEXER_DEBUG:
        print("=== LEXER DEBUG ===")
        debugLexer: Lexer = Lexer(source)
        while debugLexer.currentChar is not None:
            print(debugLexer.nextToken())

    lexer: Lexer = Lexer(source)
    parser: Parser = Parser(lexer)
    program: Program = parser.parseProgram()

    if len(parser.errors) > 0:
        for error in parser.errors:
            print(error)
        raise SystemExit(1)

    if PARSER_DEBUG:
        DEBUG_DIR.mkdir(exist_ok=True)
        astPath = DEBUG_DIR / "ast.json"
        print("=== PARSER DEBUG ===")
        with open(astPath, "w") as f:
            json.dump(program.json(), f, indent=4)
        print(f"AST saved to {astPath}")

    compiler: Compiler = Compiler()
    compiler.compile(program)

    if len(compiler.errors) > 0:
        for error in compiler.errors:
            print(error)
        raise SystemExit(1)

    # output
    module: ir.Module = compiler.module
    module.triple = llvm.get_default_triple()

    if COMPILER_DEBUG:
        DEBUG_DIR.mkdir(exist_ok=True)
        irPath = DEBUG_DIR / "a.ll"
        with open(irPath, "w") as f:
            f.write(str(module))
        print("=== COMPILER DEBUG ===")
        print(f"IR saved to {irPath}")
        print(module)

    if RUN_PROGRAM:
        # newer llvmlite versions initialize LLVM automatically and raise if this is called
        try:
            llvm.initialize()
        except RuntimeError:
            pass
        llvm.initialize_native_target()
        llvm.initialize_native_asmprinter()

        try:
            llvmIrParsed = llvm.parse_assembly(str(module))
            llvmIrParsed.verify()
        except Exception as exc:
            print(exc)
            raise

        targetMachine = llvm.Target.from_default_triple().create_target_machine()
        engine = llvm.create_mcjit_compiler(llvmIrParsed, targetMachine)
        engine.finalize_object()

        entryName = os.environ.get("CPL_ENTRY", "mn")
        entry = engine.get_function_address(entryName)
        if entry == 0:
            print(f"~~~ COMPILE ERROR: No entry function '{entryName}' found.")
            raise SystemExit(1)

        cfunc = CFUNCTYPE(c_int)(entry)

        startTime = time.time()
        result = cfunc()
        endTime = time.time()

        elapsedMs = round((endTime - startTime) * 1000, 9)
        print(f"\nProgram returned: {result}\n === Executed in {elapsedMs} ms. ===")
