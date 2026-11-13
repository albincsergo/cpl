import argparse
import json
import sys
import time
from pathlib import Path

from Driver import CompileFailure, buildExecutable, compileProgram, optimize, parse, runJit
from Lexer import Lexer
from Token import TokenType


COMMANDS: list[str] = ["run", "build", "check", "ir", "ast", "tokens"]

USAGE: str = """cpl - the Competitive Programming Language

usage:
  cpl run <file.cpl>          compile and run (reads stdin, writes stdout)
  cpl <file.cpl>              same as run
  cpl build <file.cpl> [-o x] compile to a native executable
  cpl check <file.cpl>        only report errors
  cpl ir <file.cpl>           print the LLVM IR
  cpl ast <file.cpl>          print the syntax tree as JSON
  cpl tokens <file.cpl>       print the tokens

options:
  -O0 .. -O3                  optimization level (default -O2)
  --time                      print how long the program ran, to stderr
"""


def parseArguments(arguments: list[str]) -> argparse.Namespace:
    # 'cpl file.cpl' is short for 'cpl run file.cpl'
    positional: list[str] = [argument for argument in arguments if not argument.startswith("-")]
    if positional and positional[0] not in COMMANDS:
        arguments = ["run"] + arguments

    parser = argparse.ArgumentParser(prog="cpl", usage=USAGE, add_help=False)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("file", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("-O", dest="optLevel", type=int, default=2, choices=[0, 1, 2, 3])
    parser.add_argument("--time", action="store_true")
    return parser.parse_args(arguments)


def main(arguments: list[str]) -> int:
    if not arguments or arguments[0] in ["-h", "--help", "help"]:
        print(USAGE, end="")
        return 0 if arguments else 2

    options: argparse.Namespace = parseArguments(arguments)

    try:
        source: str = options.file.read_text()
    except OSError as error:
        print(f"~~~ ERROR: can't read {options.file}: {error.strerror}", file=sys.stderr)
        return 1

    try:
        if options.command == "tokens":
            lexer: Lexer = Lexer(source)
            token = lexer.nextToken()
            while token.type != TokenType.EOF:
                print(token)
                token = lexer.nextToken()
            return 0

        program = parse(source)
        if options.command == "ast":
            print(json.dumps(program.json(), indent=4))
            return 0

        module = compileProgram(program)
        match options.command:
            case "check":
                return 0
            case "ir":
                # the program's own code, without the runtime that gets linked in when it's built
                print(optimize(module, options.optLevel, linkRuntime=False) if options.optLevel > 0 else module)
                return 0
            case "build":
                output: Path = options.output or Path(options.file.stem)
                buildExecutable(module, output, options.optLevel)
                return 0

        startTime: float = time.perf_counter()
        exitCode: int = runJit(module, options.optLevel)
        if options.time:
            print(f"=== Executed in {(time.perf_counter() - startTime) * 1000:.3f} ms. ===", file=sys.stderr)
        return exitCode
    except CompileFailure as failure:
        for error in failure.errors:
            print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
