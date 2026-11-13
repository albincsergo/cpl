from Lexer import Lexer
from Parser import Parser
from AST import Program
from Compiler import Compiler
import json
import time
from pathlib import Path

from llvmlite import ir
import llvmlite.binding as llvm
from ctypes import CFUNCTYPE, c_int, c_double

LEXER_DEBUG: bool = 0
PARSER_DEBUG: bool = 0
COMPILER_DEBUG: bool = 0
RUN_PROGRAM: bool = 1

# resolve paths relative to the repo root so the script works from any directory
ROOT_DIR: Path = Path(__file__).resolve().parent.parent
TEST_FILE: Path = ROOT_DIR / "tests" / "test.cpl"
DEBUG_DIR: Path = ROOT_DIR / "debug"

if __name__ == '__main__':
    with open(TEST_FILE, "r") as f:
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
        exit(1)

    if PARSER_DEBUG:
        print("=== PARSER DEBUG ===")
        DEBUG_DIR.mkdir(exist_ok=True)
        with open(DEBUG_DIR / "ast.json", "w") as f:
            json.dump(program.json(), f, indent=4)
        
        print ("AST saved to ast.json")

    compiler: Compiler = Compiler()
    compiler.compile(program)

    if len(compiler.errors) > 0:
        for error in compiler.errors:
            print(error)
        exit(1)

    # output
    module: ir.Module = compiler.module
    module.triple = llvm.get_default_triple()

    if COMPILER_DEBUG:
        DEBUG_DIR.mkdir(exist_ok=True)
        with open(DEBUG_DIR / "a.ll", "w") as f:
            f.write(str(module))
        print("=== COMPILER DEBUG ===")
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

        entry = engine.get_function_address('mn')
        if entry == 0:
            print("~~~ COMPILE ERROR: No entry function 'mn' found.")
            exit(1)

        cfunc = CFUNCTYPE(c_int)(entry)

        startTime = time.time()
        result = cfunc()
        endTime = time.time()

        print(f'\nProgram returned: {result}\n === Executed in {round((endTime - startTime) * 1000, 9)} ms. ===')