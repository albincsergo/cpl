from llvmlite import ir
import llvmlite.binding as llvm

from AST import (
    AssignStatement,
    BlockStatement,
    CallExpression,
    CastExpression,
    Expression,
    ExpressionStatement,
    ForStatement,
    FunctionStatement,
    IdentifierLiteral,
    IfStatement,
    IndexExpression,
    InfixExpression,
    InputStatement,
    MemberExpression,
    Node,
    NodeType,
    OutputStatement,
    PrefixExpression,
    Program,
    ReturnStatement,
    ShallStatement,
    Statement,
    StructStatement,
    TypeExpression,
    WhileStatement,
)
from Environment import Environment
from Target import targetMachine
from Types import (
    BO, BYTE_POINTER, CH, DU, IT, LL, NIL, PRIMITIVES, SORT_UNSIGNED, ST, ULL, VO,
    CType, StructInfo, integerFor,
)


I1 = ir.IntType(1)
I8 = ir.IntType(8)
I32 = ir.IntType(32)
I64 = ir.IntType(64)
DOUBLE = ir.DoubleType()
VOID = ir.VoidType()

COMPARISON_OPERATORS: list[str] = ["==", "!=", "<", ">", "<=", ">="]

# competitive programmer spelling first, then what a C++ programmer would type
METHOD_ALIASES: dict[str, str] = {
    "push_back": "pb", "pop_back": "pp", "size": "sz", "back": "bk", "clear": "clr", "sort": "srt",
    "reverse": "rev", "empty": "emp", "substr": "sub", "count": "has", "contains": "has", "erase": "del",
    "push": "ps", "top": "tp", "pop": "pp", "lower_bound": "lb", "upper_bound": "ub",
}

MAX_ERRORS: int = 20


class TypedValue:
    def __init__(self, value: ir.Value | None, ctype: CType, literal: int | float | None = None) -> None:
        self.value = value
        self.ctype = ctype
        # the number itself when this is a literal, for conversions like 'll x = 1e18'
        self.literal = literal


class FunctionInfo:
    def __init__(self, name: str, irFunction: ir.Function, parameters: list[tuple[str, CType]], returnType: CType, node: FunctionStatement) -> None:
        self.name = name
        self.irFunction = irFunction
        self.parameters = parameters
        self.returnType = returnType
        self.node = node


class LoopContext:
    def __init__(self, breakBlock: ir.Block, continueBlock: ir.Block) -> None:
        self.breakBlock = breakBlock
        self.continueBlock = continueBlock
        self.hasBreak: bool = False


class CompileError(Exception):
    # raised to bail out of a deeply nested expression after the error was already reported
    pass


class Compiler:
    def __init__(self) -> None:
        # a fresh context per program, so struct names from one compile never clash with the next
        self.module: ir.Module = ir.Module("main", context=ir.Context())
        # the real layout of this machine, so sizes computed here match what LLVM generates
        machine: llvm.TargetMachine = targetMachine()
        self.targetData: llvm.TargetData = machine.target_data
        self.module.triple = machine.triple
        self.module.data_layout = str(self.targetData)
        self.typeSizes: dict[str, int] = {}

        # CplVec { len, cap, elemSize, data } - the layout from the runtime
        self.vecStruct: ir.IdentifiedStructType = self.module.context.get_identified_type("CplVec")
        self.vecStruct.set_body(I64, I64, I64, BYTE_POINTER)
        self.vecPointer: ir.PointerType = self.vecStruct.as_pointer()

        self.builder: ir.IRBuilder | None = None
        self.allocaBuilder: ir.IRBuilder | None = None
        self.globalEnvironment: Environment = Environment()
        self.environment: Environment = self.globalEnvironment
        self.atGlobalScope: bool = False

        self.structs: dict[str, CType] = {}
        self.structFieldTypes: dict[str, list[TypeExpression]] = {}
        self.functions: dict[str, FunctionInfo] = {}
        self.currentFunction: FunctionInfo | None = None
        self.loops: list[LoopContext] = []

        self.runtimeFunctions: dict[str, ir.Function] = {}
        self.intrinsics: dict[str, ir.Function] = {}
        self.stringConstants: dict[str, ir.Constant] = {}

        # type-based alias analysis: vector headers, vector elements of each type and struct fields
        # never overlap, and telling LLVM so lets it keep v.len and v.data in registers inside loops
        self.tbaaRoot = self.module.add_metadata(["cpl alias classes"])
        self.tbaaTags: dict[str, ir.Value] = {}
        self.invariantNode: ir.Value | None = None
        self.pointerTags: dict[ir.Value, str] = {}
        self.mapSlotCount: int = 0
        # > 0 while compiling the expression inside v[...]
        self.indexDepth: int = 0
        # index expressions proven in bounds by loop versioning (see rangeLoop)
        self.uncheckedIndexes: set[int] = set()
        # generated functions: comparators for sorting, heap operations for priority queues
        self.helpers: dict[str, ir.Function] = {}

        # temporary error collection used by main.py
        self.errors: list[str] = []

    # region errors
    def error(self, message: str, node: Node | TypeExpression | None) -> None:
        line: int = getattr(node, "line", 0) if node is not None else 0
        text: str = f"~~~ COMPILE ERROR (line {line}): {message}" if line else f"~~~ COMPILE ERROR: {message}"
        if text not in self.errors and len(self.errors) < MAX_ERRORS:
            self.errors.append(text)
    # endregion

    # region entry point
    def compile(self, program: Program) -> None:
        topLevel: list[Statement] = program.statements

        # pass 1: struct names, so that structs and functions can refer to each other in any order
        for statement in topLevel:
            if statement.type() == NodeType.StructStatement:
                self.declareStruct(statement)
        for statement in topLevel:
            if statement.type() == NodeType.StructStatement:
                self.defineStructFields(statement)

        # pass 2: function signatures
        for statement in topLevel:
            if statement.type() == NodeType.FunctionStatement:
                self.declareFunction(statement)

        # pass 3: global variables, initialized by cpl.init before mn runs
        self.reassignedNames = assignedNames(program)
        initFunction: ir.Function = ir.Function(self.module, ir.FunctionType(VOID, []), name="cpl.init")
        initFunction.linkage = "internal"
        self.startFunction(initFunction)
        self.atGlobalScope = True
        for statement in topLevel:
            match statement.type():
                case NodeType.FunctionStatement | NodeType.StructStatement:
                    pass
                case NodeType.ShallStatement:
                    self.guarded(self.visitShallStatement, statement)
                case _:
                    self.error("only declarations, functions and structs can be at the top level; put this inside a function", statement)
        self.atGlobalScope = False
        if not self.currentBlockTerminated():
            self.builder.ret_void()
        self.finishFunction()

        # pass 4: function bodies
        for info in self.functions.values():
            self.guarded(self.compileFunctionBody, info)

        self.createMain(initFunction)

    def guarded(self, function: callable, argument: object) -> None:
        # after an error the half-built IR is thrown away anyway, so internal follow-up failures are just noise
        try:
            function(argument)
        except CompileError:
            pass
        except Exception:
            if len(self.errors) == 0:
                raise

    def createMain(self, initFunction: ir.Function) -> None:
        info: FunctionInfo | None = self.functions.get("mn")
        if info is None:
            self.error("there is no entry function; add 'f mn() -> it { ... }'", None)
            return

        if len(info.parameters) > 0:
            self.error("the entry function mn can't take parameters", info.node)
            return

        if info.returnType.kind not in ["void", "int", "char"]:
            self.error(f"the entry function mn must return an integer or nothing, not {info.returnType}", info.node)
            return

        # cpl.entry runs the global initializers and mn; main starts it on the runtime's big stack
        entry: ir.Function = ir.Function(self.module, ir.FunctionType(I32, []), name="cpl.entry")
        entry.linkage = "internal"
        builder: ir.IRBuilder = ir.IRBuilder(entry.append_basic_block("entry"))
        builder.call(initFunction, [])
        result = builder.call(info.irFunction, [])

        exitCode: ir.Value = ir.Constant(I32, 0)
        if info.returnType.kind != "void":
            bits: int = info.returnType.bits
            if bits > 32:
                exitCode = builder.trunc(result, I32)
            elif bits < 32:
                exitCode = builder.zext(result, I32)
            else:
                exitCode = result
        builder.ret(exitCode)

        main: ir.Function = ir.Function(self.module, ir.FunctionType(I32, []), name="main")
        builder = ir.IRBuilder(main.append_basic_block("entry"))
        code: ir.Value = builder.call(self.runtime("cpl_start"), [entry])
        builder.call(self.runtime("cpl_flush"), [])
        builder.ret(code)
    # endregion

    # region declarations
    def declareStruct(self, node: StructStatement) -> None:
        if node.name in self.structs or node.name in PRIMITIVES:
            self.error(f"type '{node.name}' is already defined", node)
            return

        irType: ir.IdentifiedStructType = self.module.context.get_identified_type(f"struct.{node.name}")
        info: StructInfo = StructInfo(node.name, irType)
        self.structs[node.name] = CType("struct", node.name, irType.as_pointer(), struct=info)

    def defineStructFields(self, node: StructStatement) -> None:
        ctype: CType | None = self.structs.get(node.name)
        if ctype is None or ctype.struct.fieldsResolved:
            return

        info: StructInfo = ctype.struct
        typeExpressions: list[TypeExpression] = []
        for name, typeExpression in node.fields:
            if info.fieldIndex(name) is not None:
                self.error(f"struct {node.name} already has a field '{name}'", node)
                continue
            fieldType: CType | None = self.resolveType(typeExpression)
            if fieldType is None:
                continue
            if fieldType.kind == "void":
                self.error(f"field '{name}' can't have type vo", typeExpression)
                continue
            info.fields.append((name, fieldType))
            typeExpressions.append(typeExpression)

        if len(info.fields) == 0:
            # LLVM doesn't like empty structs much; give it a dummy byte
            info.irType.set_body(I8)
        else:
            info.irType.set_body(*[fieldType.irType for _, fieldType in info.fields])
        info.fieldsResolved = True
        self.structFieldTypes[node.name] = typeExpressions

    def declareFunction(self, node: FunctionStatement) -> None:
        name: str = node.name
        if name in ["f", "r"]:
            self.error(f"a function can't be called '{name}', since {name}(...) at the start of a statement means {'func' if name == 'f' else 'ret'}", node)
            return
        if name in self.functions:
            self.error(f"function '{name}' is already defined", node)
            return
        if name in self.structs:
            self.error(f"'{name}' is already the name of a struct", node)
            return

        parameters: list[tuple[str, CType]] = []
        for parameterName, typeExpression in node.parameters:
            parameterType: CType | None = self.resolveType(typeExpression)
            if parameterType is None:
                return
            if parameterType.kind == "void":
                self.error(f"parameter '{parameterName}' can't have type vo", typeExpression)
                return
            if parameterName in [existing for existing, _ in parameters]:
                self.error(f"function '{name}' has two parameters named '{parameterName}'", node)
                return
            parameters.append((parameterName, parameterType))

        returnType: CType | None = VO if node.returnType is None else self.resolveType(node.returnType)
        if returnType is None:
            return

        functionType: ir.FunctionType = ir.FunctionType(returnType.irType, [ctype.irType for _, ctype in parameters])
        irFunction: ir.Function = ir.Function(self.module, functionType, name=f"cpl.{name}")
        irFunction.linkage = "internal"
        self.functions[name] = FunctionInfo(name, irFunction, parameters, returnType, node)

    def resolveType(self, typeExpression: TypeExpression) -> CType | None:
        name: str = typeExpression.name
        arguments: list = typeExpression.arguments

        if name in PRIMITIVES:
            if arguments:
                self.error(f"type {name} doesn't take type arguments", typeExpression)
                return None
            return PRIMITIVES[name]

        if name in self.structs:
            if arguments:
                self.error(f"struct {name} doesn't take type arguments", typeExpression)
                return None
            return self.structs[name]

        if name == "vec" or name == "arr":
            expectedCount: int = 1 if name == "vec" else 2
            if len(arguments) != expectedCount or not isinstance(arguments[0], TypeExpression):
                usage: str = "vec<type>" if name == "vec" else "arr<type, size>"
                self.error(f"expected {usage} but found {typeExpression}", typeExpression)
                return None
            if name == "arr" and (not isinstance(arguments[1], int) or arguments[1] < 0):
                self.error("the size of an arr must be a non-negative integer literal, as in arr<it, 100>", typeExpression)
                return None

            elem: CType | None = self.resolveType(arguments[0])
            if elem is None:
                return None
            if elem.kind == "void":
                self.error("a vector can't hold vo", typeExpression)
                return None
            return self.vecType(elem)

        if name == "map":
            if len(arguments) != 2 or not all(isinstance(argument, TypeExpression) for argument in arguments):
                self.error(f"expected map<key type, value type> but found {typeExpression}", typeExpression)
                return None
            key: CType | None = self.resolveType(arguments[0])
            value: CType | None = self.resolveType(arguments[1])
            if key is None or value is None:
                return None
            packablePair: bool = key.kind == "pair" and key.first.isPackableKey and key.second.isPackableKey
            if key.kind not in ["int", "char", "bool", "float", "string"] and not packablePair:
                self.error(f"map keys must be numbers, characters, booleans, strings or pairs of 32-bit integers, not {key}", typeExpression)
                return None
            if value.kind == "void":
                self.error("a map can't hold vo", typeExpression)
                return None
            return self.mapType(key, value)

        if name == "pr":
            if len(arguments) != 2 or not all(isinstance(argument, TypeExpression) for argument in arguments):
                self.error(f"expected pr<first type, second type> but found {typeExpression}", typeExpression)
                return None
            first: CType | None = self.resolveType(arguments[0])
            second: CType | None = self.resolveType(arguments[1])
            if first is None or second is None:
                return None
            return self.pairType(first, second, typeExpression)

        if name in ["pq", "minpq"]:
            if len(arguments) != 1 or not isinstance(arguments[0], TypeExpression):
                self.error(f"expected {name}<type> but found {typeExpression}", typeExpression)
                return None
            elem = self.resolveType(arguments[0])
            if elem is None:
                return None
            if not elem.isOrderable:
                self.error(f"a {name} needs elements that can be compared with <, like numbers, strings or pairs, not {elem}", typeExpression)
                return None
            return self.pqType(elem, minFirst=name == "minpq")

        self.error(f"unknown type '{name}'", typeExpression)
        return None

    def pairType(self, first: CType, second: CType, node: Node | TypeExpression | None) -> CType | None:
        for half in [first, second]:
            if half.kind in ["void", "nil"] or half.isContainer and half.kind != "struct":
                self.error(f"a pair can hold numbers, characters, booleans, strings, structs and pairs, not {half}", node)
                return None
        return CType("pair", f"pr<{first}, {second}>", ir.LiteralStructType([first.irType, second.irType]), first=first, second=second)

    def pqType(self, elem: CType, minFirst: bool) -> CType:
        return CType("pq", f"{'minpq' if minFirst else 'pq'}<{elem}>", self.vecPointer, elem=elem, minFirst=minFirst)

    def mapKeyKind(self, key: CType) -> int:
        # pairs are packed into an unsigned 64-bit number that sorts in the same order
        return SORT_UNSIGNED if key.kind == "pair" else key.sortKind

    def vecType(self, elem: CType) -> CType:
        return CType("vec", f"vec<{elem}>", self.vecPointer, elem=elem)

    def mapType(self, key: CType, value: CType) -> CType:
        return CType("map", f"map<{key}, {value}>", BYTE_POINTER, key=key, value=value)
    # endregion

    # region functions
    def startFunction(self, irFunction: ir.Function) -> None:
        # all local variables live in the entry block, so LLVM can turn them into registers;
        # the code itself starts in a separate block that the entry jumps to once the function is done
        entry: ir.Block = irFunction.append_basic_block("entry")
        self.bodyBlock: ir.Block = irFunction.append_basic_block("body")
        self.allocaBuilder = ir.IRBuilder(entry)
        self.builder = ir.IRBuilder(self.bodyBlock)

    def finishFunction(self) -> None:
        self.allocaBuilder.branch(self.bodyBlock)

    def allocate(self, irType: ir.Type, name: str = "") -> ir.Value:
        return self.allocaBuilder.alloca(irType, name=name)

    def compileFunctionBody(self, info: FunctionInfo) -> None:
        self.currentFunction = info
        self.startFunction(info.irFunction)
        self.environment = Environment(parent=self.globalEnvironment, name=info.name)
        self.loops = []

        for (name, ctype), argument in zip(info.parameters, info.irFunction.args):
            pointer: ir.Value = self.allocate(ctype.irType, name)
            self.builder.store(argument, pointer)
            self.environment.define(name, pointer, ctype)

        errorCount: int = len(self.errors)
        self.visitStatements(info.node.body.statements)

        if not self.currentBlockTerminated():
            if info.returnType.kind == "void":
                self.builder.ret_void()
            elif info.name == "mn" and info.returnType.isInteger:
                # like main in C++, falling off the end of mn means success
                self.builder.ret(ir.Constant(info.returnType.irType, 0))
            elif len(self.errors) == errorCount:
                # only report a missing return if the body itself compiled cleanly
                self.error(f"function {info.name} doesn't return a value at the end", info.node)

        self.finishFunction()
        self.environment = self.globalEnvironment
        self.currentFunction = None

    def runtime(self, name: str) -> ir.Function:
        if name in self.runtimeFunctions:
            return self.runtimeFunctions[name]

        string = BYTE_POINTER
        vec = self.vecPointer
        signatures: dict[str, tuple[ir.Type, list[ir.Type]]] = {
            "cpl_flush": (VOID, []), "cpl_start": (I32, [ir.FunctionType(I32, []).as_pointer()]),
            "cpl_print_i64": (VOID, [I64]), "cpl_print_u64": (VOID, [I64]), "cpl_print_f64": (VOID, [DOUBLE]),
            "cpl_print_char": (VOID, [I8]), "cpl_print_bool": (VOID, [I8]), "cpl_print_str": (VOID, [string]),
            "cpl_panic_index": (VOID, [I64, I64]), "cpl_panic_div": (VOID, []),
            "cpl_panic_nil": (VOID, []), "cpl_panic_empty": (VOID, []),
            "cpl_alloc": (BYTE_POINTER, [I64]),
            "cpl_eof": (I8, []), "cpl_read_i64": (I64, []), "cpl_read_u64": (I64, []), "cpl_read_f64": (DOUBLE, []),
            "cpl_read_char": (I8, []), "cpl_read_bool": (I8, []), "cpl_read_str": (string, []),
            "cpl_read_line": (string, []),
            "cpl_str_len": (I64, [string]), "cpl_str_concat": (string, [string, string]),
            "cpl_str_cmp": (I32, [string, string]), "cpl_str_at": (I8, [string, I64]),
            "cpl_str_append_char": (string, [string, I8]),
            "cpl_str_sub": (string, [string, I64, I64]), "cpl_str_from_char": (string, [I8]),
            "cpl_str_from_i64": (string, [I64]), "cpl_str_from_u64": (string, [I64]),
            "cpl_str_from_f64": (string, [DOUBLE]), "cpl_str_from_bool": (string, [I8]),
            "cpl_str_prec": (string, [DOUBLE, I64]), "cpl_str_to_i64": (I64, [string]),
            "cpl_str_to_f64": (DOUBLE, [string]),
            "cpl_ipow": (I64, [I64, I64]),
            "cpl_vec_new": (vec, [I64, I64]), "cpl_vec_grow": (VOID, [vec]), "cpl_vec_pop": (VOID, [vec]),
            "cpl_vec_clear": (VOID, [vec]), "cpl_vec_sort": (VOID, [vec, I32]), "cpl_vec_reverse": (VOID, [vec]),
            "cpl_temp_alloc": (BYTE_POINTER, [I64]), "cpl_temp_free": (VOID, [BYTE_POINTER]),
            "cpl_map_new": (BYTE_POINTER, [I32]), "cpl_map_at": (BYTE_POINTER, [BYTE_POINTER, I64, I8.as_pointer()]),
            "cpl_map_has": (I8, [BYTE_POINTER, I64]), "cpl_map_del": (VOID, [BYTE_POINTER, I64]),
            "cpl_map_size": (I64, [BYTE_POINTER]), "cpl_map_keys": (vec, [BYTE_POINTER, I64]),
            "cpl_map_clear": (VOID, [BYTE_POINTER]),
        }

        returnType, argumentTypes = signatures[name]
        function: ir.Function = ir.Function(self.module, ir.FunctionType(returnType, argumentTypes), name=name)
        if name.startswith("cpl_panic"):
            function.attributes.add("noreturn")
            function.attributes.add("cold")
        self.runtimeFunctions[name] = function
        return function

    def intrinsic(self, name: str, argumentCount: int = 1) -> ir.Function:
        fullName: str = f"llvm.{name}.f64"
        if fullName not in self.intrinsics:
            functionType: ir.FunctionType = ir.FunctionType(DOUBLE, [DOUBLE] * argumentCount)
            self.intrinsics[fullName] = ir.Function(self.module, functionType, name=fullName)
        return self.intrinsics[fullName]

    def helperFunction(self, name: str, functionType: ir.FunctionType, generate: callable) -> ir.Function:
        # builds a small internal function once, without disturbing the function being compiled
        if name in self.helpers:
            return self.helpers[name]
        function: ir.Function = ir.Function(self.module, functionType, name=name)
        function.linkage = "internal"
        self.helpers[name] = function

        saved = (self.builder, self.allocaBuilder, getattr(self, "bodyBlock", None), self.environment, self.loops)
        self.startFunction(function)
        self.loops = []
        generate(function)
        self.finishFunction()
        self.builder, self.allocaBuilder, self.bodyBlock, self.environment, self.loops = saved
        return function

    def lessThan(self, a: TypedValue, b: TypedValue, node: Node) -> ir.Value:
        result: TypedValue | None = self.binaryOperation("<", a, b, node)
        if result is None:
            raise CompileError()
        return result.value

    def sortFunction(self, elem: CType, node: Node, comparator: "FunctionInfo | None" = None) -> ir.Function:
        # a stable merge sort generated for one element type and order, so comparisons get inlined:
        # sort(T* data, T* scratch, i64 count), where scratch has room for count / 2 + 1 elements
        def less(a: ir.Value, b: ir.Value) -> ir.Value:
            if comparator is not None:
                return self.builder.call(comparator.irFunction, [a, b])
            return self.lessThan(TypedValue(a, elem), TypedValue(b, elem), node)

        def generate(function: ir.Function) -> None:
            data, scratch, count = function.args
            builder: ir.IRBuilder = self.builder
            one: ir.Constant = ir.Constant(I64, 1)

            def at(base: ir.Value, index: ir.Value) -> ir.Value:
                return builder.gep(base, [index], inbounds=True)

            def counter(name: str, start: ir.Value) -> ir.Value:
                variable: ir.Value = self.allocate(I64, name)
                builder.store(start, variable)
                return variable

            def loop(name: str, condition: callable, body: callable) -> None:
                conditionBlock: ir.Block = function.append_basic_block(f"{name}_condition")
                bodyBlock: ir.Block = function.append_basic_block(f"{name}_body")
                endBlock: ir.Block = function.append_basic_block(f"{name}_end")
                builder.branch(conditionBlock)
                builder.position_at_end(conditionBlock)
                builder.cbranch(condition(), bodyBlock, endBlock)
                builder.position_at_end(bodyBlock)
                body()
                builder.branch(conditionBlock)
                builder.position_at_end(endBlock)

            # short runs: insertion sort, which is stable and fast on a handful of elements
            smallBlock: ir.Block = function.append_basic_block("small")
            largeBlock: ir.Block = function.append_basic_block("large")
            builder.cbranch(builder.icmp_signed("<=", count, ir.Constant(I64, 16)), smallBlock, largeBlock)

            builder.position_at_end(smallBlock)
            i: ir.Value = counter("i", one)
            j: ir.Value = counter("j", one)
            item: ir.Value = self.allocate(elem.irType, "item")

            def insertOne() -> None:
                index: ir.Value = builder.load(i)
                builder.store(builder.load(at(data, index)), item)
                builder.store(builder.sub(index, one), j)

                def shiftCondition() -> ir.Value:
                    # j >= 0 && item < data[j], without reading data[-1]
                    position: ir.Value = builder.load(j)
                    inRange: ir.Value = builder.icmp_signed(">=", position, ir.Constant(I64, 0))
                    safe: ir.Value = builder.select(inRange, position, ir.Constant(I64, 0))
                    return builder.and_(inRange, less(builder.load(item), builder.load(at(data, safe))))

                def shift() -> None:
                    position: ir.Value = builder.load(j)
                    builder.store(builder.load(at(data, position)), at(data, builder.add(position, one)))
                    builder.store(builder.sub(position, one), j)

                loop("shift", shiftCondition, shift)
                builder.store(builder.load(item), at(data, builder.add(builder.load(j), one)))
                builder.store(builder.add(index, one), i)

            loop("insert", lambda: builder.icmp_signed("<", builder.load(i), count), insertOne)
            builder.ret_void()

            # long runs: sort both halves, then merge them through the scratch space
            builder.position_at_end(largeBlock)
            half: ir.Value = builder.lshr(count, one)
            builder.call(function, [data, scratch, half])
            builder.call(function, [at(data, half), scratch, builder.sub(count, half)])

            mergeBlock: ir.Block = function.append_basic_block("merge")
            doneBlock: ir.Block = function.append_basic_block("done")
            # already in order: nothing to merge
            outOfOrder: ir.Value = less(builder.load(at(data, half)), builder.load(at(data, builder.sub(half, one))))
            builder.cbranch(outOfOrder, mergeBlock, doneBlock)

            builder.position_at_end(mergeBlock)
            copyIndex: ir.Value = counter("c", ir.Constant(I64, 0))

            def copyOne() -> None:
                index: ir.Value = builder.load(copyIndex)
                builder.store(builder.load(at(data, index)), at(scratch, index))
                builder.store(builder.add(index, one), copyIndex)

            loop("copy", lambda: builder.icmp_signed("<", builder.load(copyIndex), half), copyOne)

            left: ir.Value = counter("left", ir.Constant(I64, 0))
            right: ir.Value = counter("right", half)
            out: ir.Value = counter("out", ir.Constant(I64, 0))

            def mergeCondition() -> ir.Value:
                return builder.and_(builder.icmp_signed("<", builder.load(left), half), builder.icmp_signed("<", builder.load(right), count))

            def mergeOne() -> None:
                leftIndex: ir.Value = builder.load(left)
                rightIndex: ir.Value = builder.load(right)
                leftValue: ir.Value = builder.load(at(scratch, leftIndex))
                rightValue: ir.Value = builder.load(at(data, rightIndex))
                # take from the right only when it is strictly smaller, which keeps equal elements in order
                takeRight: ir.Value = less(rightValue, leftValue)
                builder.store(builder.select(takeRight, rightValue, leftValue), at(data, builder.load(out)))
                builder.store(builder.add(builder.load(out), one), out)
                builder.store(builder.select(takeRight, builder.add(rightIndex, one), rightIndex), right)
                builder.store(builder.select(takeRight, leftIndex, builder.add(leftIndex, one)), left)

            loop("merge", mergeCondition, mergeOne)

            def restOne() -> None:
                leftIndex: ir.Value = builder.load(left)
                builder.store(builder.load(at(scratch, leftIndex)), at(data, builder.load(out)))
                builder.store(builder.add(builder.load(out), one), out)
                builder.store(builder.add(leftIndex, one), left)

            loop("rest", lambda: builder.icmp_signed("<", builder.load(left), half), restOne)
            builder.branch(doneBlock)

            builder.position_at_end(doneBlock)
            builder.ret_void()

        pointerType: ir.PointerType = elem.irType.as_pointer()
        name: str = f"cpl.sort.{comparator.name}" if comparator is not None else f"cpl.sort.{elem}"
        return self.helperFunction(name, ir.FunctionType(VOID, [pointerType, pointerType, I64]), generate)

    def sortVec(self, vec: ir.Value, elem: CType, node: Node, comparator: "FunctionInfo | None" = None) -> None:
        count: ir.Value = self.vecLength(vec)
        with self.builder.if_then(self.builder.icmp_signed(">", count, ir.Constant(I64, 1))):
            # the scratch space is malloc'd and freed: sorting in a loop shouldn't grow the arena
            halfPlusOne: ir.Value = self.builder.add(self.builder.lshr(count, ir.Constant(I64, 1)), ir.Constant(I64, 1))
            bytes: ir.Value = self.builder.mul(halfPlusOne, ir.Constant(I64, self.elementSize(elem)))
            scratch: ir.Value = self.callRuntime("cpl_temp_alloc", [bytes])
            pointerType: ir.PointerType = elem.irType.as_pointer()
            self.builder.call(self.sortFunction(elem, node, comparator),
                              [self.vecData(vec, elem), self.builder.bitcast(scratch, pointerType), count])
            self.callRuntime("cpl_temp_free", [scratch])

    def callRuntime(self, name: str, arguments: list[ir.Value]) -> ir.Value:
        return self.builder.call(self.runtime(name), arguments)
    # endregion

    # region statements
    def visitStatements(self, statements: list[Statement]) -> None:
        for statement in statements:
            if self.currentBlockTerminated():
                self.error("unreachable code: this comes after a return, break or continue", statement)
                return
            self.visitStatement(statement)

    def visitStatement(self, node: Statement) -> None:
        match node.type():
            case NodeType.ExpressionStatement:
                self.visitExpressionStatement(node)
            case NodeType.ShallStatement:
                self.visitShallStatement(node)
            case NodeType.AssignStatement:
                self.visitAssignStatement(node)
            case NodeType.ReturnStatement:
                self.visitReturnStatement(node)
            case NodeType.BlockStatement:
                self.visitScopedBlock(node)
            case NodeType.IfStatement:
                self.visitIfStatement(node)
            case NodeType.WhileStatement:
                self.visitWhileStatement(node)
            case NodeType.ForStatement:
                self.visitForStatement(node)
            case NodeType.ForEachStatement:
                self.visitForEachStatement(node)
            case NodeType.BreakStatement | NodeType.ContinueStatement:
                self.visitJumpStatement(node)
            case NodeType.InputStatement:
                self.visitInputStatement(node)
            case NodeType.OutputStatement:
                self.visitOutputStatement(node)
            case NodeType.FunctionStatement | NodeType.StructStatement:
                self.error("functions and structs must be defined at the top level, not inside a function", node)
            case _:
                self.error(f"can't compile {node.type().value}", node)

    def visitScopedBlock(self, node: BlockStatement) -> None:
        # variables declared inside a block are only visible inside it
        previousEnvironment: Environment = self.environment
        self.environment = Environment(parent=previousEnvironment, name="block")
        self.visitStatements(node.statements)
        self.environment = previousEnvironment

    def visitExpressionStatement(self, node: ExpressionStatement) -> None:
        if node.expression.type() != NodeType.CallExpression:
            self.error("this expression doesn't do anything; did you mean to assign it or print it?", node)
            return
        self.visitExpression(node.expression, allowVoid=True)

    def visitShallStatement(self, node: ShallStatement) -> None:
        valueType: CType | None = self.resolveType(node.valueType)
        if valueType is None:
            return
        if valueType.kind == "void":
            self.error("variables can't have type vo", node.valueType)
            return

        for name in node.names:
            if name in self.environment.records:
                self.error(f"'{name}' was already declared in this scope", node)
                continue

            value: ir.Value | None = None
            if node.value is not None:
                resolved: TypedValue | None = self.visitExpression(node.value)
                if resolved is not None and self.atGlobalScope and self.declareConstant(name, valueType, resolved):
                    continue
                if resolved is not None:
                    value = self.convert(resolved, valueType, node.value, f"the declaration of {name}")
                if value is None:
                    # declare it anyway, so every later use doesn't report it as missing too
                    self.environment.define(name, self.allocate(valueType.irType, name), valueType)
                    continue
            else:
                value = self.defaultValue(valueType, node.valueType)

            if self.atGlobalScope:
                pointer: ir.Value = ir.GlobalVariable(self.module, valueType.irType, name=f"global.{name}")
                pointer.linkage = "internal"
                pointer.initializer = ir.Constant(valueType.irType, None)
                # globals live apart from everything else, so give each one its own alias class
                self.withTag(pointer, f"global {name}")
            else:
                pointer = self.allocate(valueType.irType, name)

            self.builder.store(value, pointer)
            self.environment.define(name, pointer, valueType)

    def declareConstant(self, name: str, valueType: CType, resolved: TypedValue) -> bool:
        # a global number that starts as a literal and is never assigned anywhere is a constant, so
        # '% mod' compiles to a multiplication instead of a 40 cycle division, as with const in C++
        if name in self.reassignedNames or resolved.literal is None or valueType.kind not in ["int", "char", "float"]:
            return False
        literal: int | float = resolved.literal
        if valueType.kind == "float":
            constant: ir.Constant = ir.Constant(DOUBLE, float(literal))
        else:
            if not float(literal).is_integer():
                return False
            number: int = int(literal)
            low: int = -(2 ** (valueType.bits - 1)) if valueType.kind == "int" and valueType.signed else 0
            high: int = 2 ** (valueType.bits - 1) if valueType.kind == "int" and valueType.signed else 2 ** valueType.bits
            if not low <= number < high:
                return False
            constant = ir.Constant(valueType.irType, number)

        variable: ir.GlobalVariable = ir.GlobalVariable(self.module, valueType.irType, name=f"constant.{name}")
        variable.linkage = "internal"
        variable.global_constant = True
        variable.initializer = constant
        self.environment.define(name, variable, valueType)
        return True

    def visitAssignStatement(self, node: AssignStatement) -> None:
        # the right side goes first: it may grow a map or vector that the target points into
        right: TypedValue | None = self.visitExpression(node.rightValue)
        if right is None:
            return

        target = self.visitAddress(node.target)
        if target is None:
            return
        pointer, targetType = target

        if node.operator != "=":
            current: TypedValue = TypedValue(self.load(pointer), targetType)
            right = self.binaryOperation(node.operator, current, right, node)
            if right is None:
                return

        value: ir.Value | None = self.convert(right, targetType, node, "this assignment")
        if value is None:
            return

        self.store(value, pointer)

    def visitReturnStatement(self, node: ReturnStatement) -> None:
        if self.currentFunction is None:
            self.error("'r' can only be used inside a function", node)
            return
        returnType: CType = self.currentFunction.returnType

        if node.returnValue is None:
            if returnType.kind != "void":
                self.error(f"function {self.currentFunction.name} must return a value of type {returnType}", node)
                return
            self.builder.ret_void()
            return

        if returnType.kind == "void":
            self.error(f"function {self.currentFunction.name} doesn't return a value; use 'r.' on its own", node)
            return

        resolved: TypedValue | None = self.visitExpression(node.returnValue)
        if resolved is None:
            return

        value: ir.Value | None = self.convert(resolved, returnType, node.returnValue, "the return value")
        if value is None:
            return

        self.builder.ret(value)

    def visitIfStatement(self, node: IfStatement) -> None:
        if self.tryBranchlessIf(node):
            return

        condition: ir.Value | None = self.visitCondition(node.condition)
        if condition is None:
            return

        function: ir.Function = self.builder.function
        thenBlock: ir.Block = function.append_basic_block("if_then")
        elseBlock: ir.Block | None = function.append_basic_block("if_else") if node.alternative is not None else None
        mergeBlock: ir.Block = function.append_basic_block("if_end")

        self.builder.cbranch(condition, thenBlock, elseBlock if elseBlock is not None else mergeBlock)

        # without an else branch the merge block is always reachable through the false edge
        mergeReachable: bool = elseBlock is None

        self.builder.position_at_end(thenBlock)
        self.visitScopedBlock(node.consequence)
        if not self.currentBlockTerminated():
            self.builder.branch(mergeBlock)
            mergeReachable = True

        if elseBlock is not None:
            self.builder.position_at_end(elseBlock)
            if node.alternative.type() == NodeType.IfStatement:
                self.visitIfStatement(node.alternative)
            else:
                self.visitScopedBlock(node.alternative)
            if not self.currentBlockTerminated():
                self.builder.branch(mergeBlock)
                mergeReachable = True

        self.builder.position_at_end(mergeBlock)

        # every branch returned, so nothing can run after this if
        if not mergeReachable:
            self.builder.unreachable()

    def tryBranchlessIf(self, node: IfStatement) -> bool:
        # if c { x = A. } else { x = B. }  ->  x = c ? A : B without a branch, when computing both
        # sides is harmless: no side effects, no division, and only indexes proven in bounds. A
        # mispredicted branch in a DP loop costs more than computing both values.
        def single(block: Statement | None) -> AssignStatement | None:
            if block is None or block.type() != NodeType.BlockStatement or len(block.statements) != 1:
                return None
            statement: Statement = block.statements[0]
            return statement if statement.type() == NodeType.AssignStatement and statement.operator == "=" else None

        then: AssignStatement | None = single(node.consequence)
        if then is None:
            return False
        otherwise: AssignStatement | None = None
        if node.alternative is not None:
            otherwise = single(node.alternative)
            if otherwise is None or otherwise.target.json() != then.target.json():
                return False

        target: Expression = then.target
        if not (target.type() == NodeType.IdentifierLiteral or self.isHarmless(target)):
            return False
        if not self.isHarmless(then.rightValue) or (otherwise is not None and not self.isHarmless(otherwise.rightValue)):
            return False

        condition: ir.Value | None = self.visitCondition(node.condition)
        if condition is None:
            return True
        chosen: TypedValue | None = self.visitExpression(then.rightValue)
        other: TypedValue | None = self.visitExpression(otherwise.rightValue) if otherwise is not None else None
        address = self.visitAddress(target)
        if chosen is None or address is None or (otherwise is not None and other is None):
            return True
        pointer, targetType = address
        if other is None:
            other = TypedValue(self.load(pointer), targetType)

        first: ir.Value | None = self.convert(chosen, targetType, then, "this assignment")
        second: ir.Value | None = self.convert(other, targetType, otherwise or then, "this assignment")
        if first is not None and second is not None:
            self.store(self.builder.select(condition, first, second), pointer)
        return True

    def isHarmless(self, expression: Expression) -> bool:
        # safe to evaluate even when its branch isn't taken
        match expression.type():
            case NodeType.IntegerLiteral | NodeType.DoubleLiteral | NodeType.BooleanLiteral | NodeType.CharLiteral:
                return True
            case NodeType.IdentifierLiteral:
                return self.environment.lookup(expression.value) is not None
            case NodeType.PrefixExpression:
                return self.isHarmless(expression.rightNode)
            case NodeType.InfixExpression:
                return expression.operator not in ["/", "%", "^"] and self.isHarmless(expression.leftNode) and self.isHarmless(expression.rightNode)
            case NodeType.IndexExpression:
                return id(expression) in self.uncheckedIndexes and self.isHarmless(expression.index)
            case NodeType.CallExpression:
                function: Expression = expression.function
                return (function.type() == NodeType.IdentifierLiteral and function.value in ["min", "max", "abs"]
                        and function.value not in self.functions and all(self.isHarmless(argument) for argument in expression.arguments))
        return False

    def visitWhileStatement(self, node: WhileStatement) -> None:
        function: ir.Function = self.builder.function
        conditionBlock: ir.Block = function.append_basic_block("while_condition")
        bodyBlock: ir.Block = function.append_basic_block("while_body")
        endBlock: ir.Block = function.append_basic_block("while_end")

        self.builder.branch(conditionBlock)
        self.builder.position_at_end(conditionBlock)
        condition: ir.Value | None = self.visitCondition(node.condition)
        if condition is None:
            return
        self.builder.cbranch(condition, bodyBlock, endBlock)

        self.builder.position_at_end(bodyBlock)
        loop: LoopContext = LoopContext(endBlock, conditionBlock)
        self.loops.append(loop)
        self.visitScopedBlock(node.body)
        self.loops.pop()
        if not self.currentBlockTerminated():
            self.builder.branch(conditionBlock)

        self.finishLoop(endBlock, loop, node.condition)

    def visitForStatement(self, node: ForStatement) -> None:
        # the loop variable lives in its own scope around the loop
        previousEnvironment: Environment = self.environment
        self.environment = Environment(parent=previousEnvironment, name="for")

        if node.initializer is not None:
            self.visitStatement(node.initializer)

        function: ir.Function = self.builder.function
        conditionBlock: ir.Block = function.append_basic_block("for_condition")
        bodyBlock: ir.Block = function.append_basic_block("for_body")
        stepBlock: ir.Block = function.append_basic_block("for_step")
        endBlock: ir.Block = function.append_basic_block("for_end")

        self.builder.branch(conditionBlock)
        self.builder.position_at_end(conditionBlock)
        if node.condition is not None:
            condition: ir.Value | None = self.visitCondition(node.condition)
            if condition is None:
                self.environment = previousEnvironment
                return
            self.builder.cbranch(condition, bodyBlock, endBlock)
        else:
            self.builder.branch(bodyBlock)

        self.builder.position_at_end(bodyBlock)
        loop: LoopContext = LoopContext(endBlock, stepBlock)
        self.loops.append(loop)
        self.visitScopedBlock(node.body)
        self.loops.pop()
        if not self.currentBlockTerminated():
            self.builder.branch(stepBlock)

        self.builder.position_at_end(stepBlock)
        if node.step is not None:
            self.visitStatement(node.step)
        self.builder.branch(conditionBlock)

        self.finishLoop(endBlock, loop, node.condition)
        self.environment = previousEnvironment

    def visitForEachStatement(self, node) -> None:
        if len(node.names) == 2 and node.names[0] == node.names[1]:
            self.error(f"the two loop variables can't both be called '{node.names[0]}'", node)
            return

        previousEnvironment: Environment = self.environment
        self.environment = Environment(parent=previousEnvironment, name="for")
        try:
            iterable: Expression = node.iterable
            isRange: bool = (iterable.type() == NodeType.CallExpression and iterable.function.type() == NodeType.IdentifierLiteral
                             and iterable.function.value == "rng" and "rng" not in self.functions)
            if isRange:
                self.rangeLoop(node)
            else:
                self.collectionLoop(node)
        except CompileError:
            pass
        self.environment = previousEnvironment

    def loopVariable(self, name: str, ctype: CType) -> ir.Value:
        pointer: ir.Value = self.allocate(ctype.irType, name)
        self.environment.define(name, pointer, ctype)
        return pointer

    def rangeLoop(self, node) -> None:
        # rng(end), rng(start, end), rng(start, end, step): like Python's range, without building a vector
        arguments: list[Expression] = node.iterable.arguments
        if not 1 <= len(arguments) <= 3:
            self.error(f"rng() takes an end, a start and an end, or a start, an end and a step, not {len(arguments)} values", node.iterable)
            raise CompileError()
        if len(node.names) != 1:
            self.error("a loop over rng() has one variable: for (i in rng(n))", node)
            raise CompileError()

        values: list[TypedValue] = []
        for argument in arguments:
            resolved: TypedValue | None = self.visitExpression(argument)
            if resolved is None:
                raise CompileError()
            if not resolved.ctype.isInteger:
                self.error(f"rng() counts with integers, not {resolved.ctype}", argument)
                raise CompileError()
            values.append(resolved)

        counterType: CType = IT
        for value in values:
            counterType = self.commonNumericType(counterType, value.ctype)
        converted: list[ir.Value] = [self.convert(value, counterType, node, "", explicit=True) for value in values]
        zero: ir.Constant = ir.Constant(counterType.irType, 0)
        start, end, step = (zero, converted[0], ir.Constant(counterType.irType, 1)) if len(converted) == 1 else (
            converted[0], converted[1], converted[2] if len(converted) == 3 else ir.Constant(counterType.irType, 1))

        counter: ir.Value = self.allocate(counterType.irType, "counter")
        variable: ir.Value = self.loopVariable(node.names[0], counterType)

        compare = self.builder.icmp_signed if counterType.signed else self.builder.icmp_unsigned
        stepIsLiteral: bool = len(arguments) < 3 or arguments[2].type() == NodeType.IntegerLiteral or (
            arguments[2].type() == NodeType.PrefixExpression and arguments[2].operator == "-" and arguments[2].rightNode.type() == NodeType.IntegerLiteral)
        negative: bool = len(arguments) == 3 and arguments[2].type() == NodeType.PrefixExpression

        def condition() -> ir.Value:
            current: ir.Value = self.builder.load(counter)
            if stepIsLiteral:
                return compare(">" if negative else "<", current, end)
            # the direction depends on the sign of the step
            goingUp: ir.Value = self.builder.icmp_signed(">", step, zero)
            return self.builder.select(goingUp, compare("<", current, end), compare(">", current, end))

        def bodyStart() -> None:
            self.builder.store(self.builder.load(counter), variable)

        # with a step of 1 or -1 the counter stops at the end before it could overflow, which lets LLVM
        # widen it to 64 bits; other steps keep wrapping arithmetic
        unitStep: bool = len(arguments) < 3 or (stepIsLiteral and self.literalValue(arguments[2]) in [1, -1])

        def advance() -> None:
            flags: tuple = ("nsw",) if unitStep else ()
            self.builder.store(self.builder.add(self.builder.load(counter), step, flags=flags), counter)

        def emit() -> None:
            self.builder.store(start, counter)
            self.emitLoop(condition, bodyStart, advance, node.body)

        # loop versioning: if every v[i + E] in the body is in bounds for the whole range, checked
        # once here, run a copy of the loop without per-element bounds checks
        candidates: list[IndexExpression] = self.uncheckableIndexes(node.body, node.names[0]) if stepIsLiteral and counterType.signed else []
        if not candidates:
            emit()
            return

        one: ir.Constant = ir.Constant(counterType.irType, 1)
        if negative:
            isEmpty: ir.Value = self.builder.icmp_signed("<=", start, end)
            lowest, highest = self.builder.add(end, one), start
        else:
            isEmpty = self.builder.icmp_signed(">=", start, end)
            lowest, highest = start, self.builder.sub(end, one)

        inBounds: ir.Value = ir.Constant(I1, 1)
        for candidate in candidates:
            container: TypedValue = self.visitExpression(candidate.leftNode)
            length: ir.Value = self.vecLength(container.value) if container.ctype.kind == "vec" else self.stringLength(container.value)
            # the index grows with i, so the smallest and largest indices come from the ends of the range
            self.builder.store(lowest, variable)
            smallest: ir.Value = self.convert(self.visitIndexValue(candidate.index), LL, candidate, "")
            self.builder.store(highest, variable)
            largest: ir.Value = self.convert(self.visitIndexValue(candidate.index), LL, candidate, "")
            fits: ir.Value = self.builder.and_(self.builder.icmp_signed(">=", smallest, ir.Constant(I64, 0)),
                                               self.builder.icmp_signed("<", largest, length))
            inBounds = self.builder.and_(inBounds, fits)

        with self.builder.if_else(self.builder.or_(isEmpty, inBounds)) as (fast, checked):
            with fast:
                added: set[int] = {id(candidate) for candidate in candidates} - self.uncheckedIndexes
                self.uncheckedIndexes |= added
                emit()
                self.uncheckedIndexes -= added
            with checked:
                emit()

    def literalValue(self, expression: Expression) -> int | None:
        if expression.type() == NodeType.IntegerLiteral:
            return expression.value
        if expression.type() == NodeType.PrefixExpression and expression.operator == "-" and expression.rightNode.type() == NodeType.IntegerLiteral:
            return -expression.rightNode.value
        return None

    def uncheckableIndexes(self, body: BlockStatement, variable: str) -> list[IndexExpression]:
        # the v[i + E] in a loop body whose bounds can be checked once before the loop: v must keep
        # its length (no pb, pp, clr, swap or user function calls in the body, and v isn't reassigned),
        # and E must not change inside the loop
        changed: set[str] = assignedNames(body) | declaredNames(body)
        if variable in changed:
            return []

        mayResize: bool = False
        callsFunctions: bool = False
        indexes: list[IndexExpression] = []
        for node in walk(body):
            match node.type():
                case NodeType.CallExpression:
                    function: Expression = node.function
                    if function.type() == NodeType.MemberExpression:
                        if METHOD_ALIASES.get(function.name, function.name) in ["pb", "pp", "clr", "ps"]:
                            mayResize = True
                    elif function.type() == NodeType.IdentifierLiteral:
                        if function.value in self.functions:
                            callsFunctions = True
                            mayResize = True
                        elif function.value == "swap":
                            mayResize = True
                case NodeType.IndexExpression:
                    indexes.append(node)

        candidates: list[IndexExpression] = []
        for index in indexes:
            if index.leftNode.type() != NodeType.IdentifierLiteral or index.leftNode.value in changed:
                continue
            record = self.environment.lookup(index.leftNode.value)
            if record is None:
                continue
            pointer, ctype = record
            if ctype.kind == "vec" and mayResize:
                continue
            # a string is immutable, but a function may still assign a new one to a global
            if ctype.kind == "string" and callsFunctions and isinstance(pointer, ir.GlobalVariable):
                continue
            if ctype.kind not in ["vec", "string"]:
                continue
            if self.loopCoefficient(index.index, variable, changed) == 1:
                candidates.append(index)
        return candidates

    def loopCoefficient(self, expression: Expression, variable: str, changed: set[str]) -> int | None:
        # how much the expression grows per step of the loop variable, or None if it's not of the form
        # i + E with E fixed during the loop (only integer variables, literals, + - * and negation)
        match expression.type():
            case NodeType.IdentifierLiteral:
                if expression.value == variable:
                    return 1
                if expression.value in changed:
                    return None
                record = self.environment.lookup(expression.value)
                return 0 if record is not None and record[1].isInteger and not isinstance(record[0], ir.Function) else None
            case NodeType.IntegerLiteral:
                return 0
            case NodeType.PrefixExpression:
                if expression.operator != "-":
                    return None
                inner: int | None = self.loopCoefficient(expression.rightNode, variable, changed)
                return None if inner is None else -inner
            case NodeType.InfixExpression:
                if expression.operator not in ["+", "-", "*"]:
                    return None
                left: int | None = self.loopCoefficient(expression.leftNode, variable, changed)
                right: int | None = self.loopCoefficient(expression.rightNode, variable, changed)
                if left is None or right is None:
                    return None
                if expression.operator == "*":
                    return 0 if left == 0 and right == 0 else None
                return left + right if expression.operator == "+" else left - right
        return None

    def collectionLoop(self, node) -> None:
        collection: TypedValue | None = self.visitExpression(node.iterable)
        if collection is None:
            raise CompileError()
        ctype: CType = collection.ctype

        if ctype.kind == "map":
            # loops over a snapshot of the keys, in sorted order; the second variable is the value
            keys: TypedValue = mapKeys(self, collection, node)
            keyVariable: ir.Value = self.loopVariable(node.names[0], ctype.key)
            valueVariable: ir.Value | None = self.loopVariable(node.names[1], ctype.value) if len(node.names) == 2 else None
            index: ir.Value = self.allocate(I64, "index")
            self.builder.store(ir.Constant(I64, 0), index)

            def mapBodyStart() -> None:
                key: ir.Value = self.load(self.vecSlot(keys.value, ctype.key, self.builder.load(index)))
                self.builder.store(key, keyVariable)
                if valueVariable is not None:
                    slot: ir.Value = self.mapSlot(collection.value, ctype, TypedValue(key, ctype.key), node)
                    self.builder.store(self.builder.load(slot), valueVariable)

            self.emitLoop(lambda: self.builder.icmp_signed("<", self.builder.load(index), self.vecLength(keys.value)),
                          mapBodyStart, lambda: self.builder.store(self.builder.add(self.builder.load(index), ir.Constant(I64, 1)), index),
                          node.body)
            return

        if ctype.kind not in ["vec", "string"]:
            self.error(f"can't loop over a {ctype}; loops work on vectors, strings, maps and rng(...)", node.iterable)
            raise CompileError()

        # the second variable is the element, the first one its index
        elem: CType = ctype.elem if ctype.kind == "vec" else CH
        indexVariable: ir.Value | None = self.loopVariable(node.names[0], LL) if len(node.names) == 2 else None
        elemVariable: ir.Value = self.loopVariable(node.names[-1], elem)
        index = self.allocate(I64, "index")
        self.builder.store(ir.Constant(I64, 0), index)

        def length() -> ir.Value:
            # read again every time around, so pushing inside the loop is safe
            if ctype.kind == "vec":
                return self.vecLength(collection.value)
            return self.stringLength(collection.value)

        def bodyStart() -> None:
            current: ir.Value = self.builder.load(index)
            if indexVariable is not None:
                self.builder.store(current, indexVariable)
            if ctype.kind == "vec":
                element: ir.Value = self.load(self.vecSlot(collection.value, elem, current))
            else:
                # the loop condition already checked the index
                element = self.stringByte(collection.value, current, checked=False)
            self.builder.store(element, elemVariable)

        self.emitLoop(lambda: self.builder.icmp_signed("<", self.builder.load(index), length()), bodyStart,
                      lambda: self.builder.store(self.builder.add(self.builder.load(index), ir.Constant(I64, 1)), index), node.body)

    def emitLoop(self, condition: callable, bodyStart: callable, advance: callable, body: BlockStatement) -> None:
        function: ir.Function = self.builder.function
        conditionBlock: ir.Block = function.append_basic_block("each_condition")
        bodyBlock: ir.Block = function.append_basic_block("each_body")
        stepBlock: ir.Block = function.append_basic_block("each_step")
        endBlock: ir.Block = function.append_basic_block("each_end")

        self.builder.branch(conditionBlock)
        self.builder.position_at_end(conditionBlock)
        self.builder.cbranch(condition(), bodyBlock, endBlock)

        self.builder.position_at_end(bodyBlock)
        bodyStart()
        loop: LoopContext = LoopContext(endBlock, stepBlock)
        self.loops.append(loop)
        self.visitScopedBlock(body)
        self.loops.pop()
        if not self.currentBlockTerminated():
            self.builder.branch(stepBlock)

        self.builder.position_at_end(stepBlock)
        advance()
        self.builder.branch(conditionBlock)
        self.builder.position_at_end(endBlock)

    def finishLoop(self, endBlock: ir.Block, loop: LoopContext, condition: Expression | None) -> None:
        self.builder.position_at_end(endBlock)
        # 'while true' without a break never gets here, which matters for the missing return check
        if not loop.hasBreak and self.isAlwaysTrue(condition):
            self.builder.unreachable()

    def isAlwaysTrue(self, condition: Expression | None) -> bool:
        if condition is None:
            return True
        match condition.type():
            case NodeType.BooleanLiteral:
                return condition.value
            case NodeType.IntegerLiteral:
                return condition.value != 0
        return False

    def visitJumpStatement(self, node: Statement) -> None:
        isBreak: bool = node.type() == NodeType.BreakStatement
        if len(self.loops) == 0:
            self.error(f"'{'brk' if isBreak else 'cont'}' can only be used inside a loop", node)
            return

        loop: LoopContext = self.loops[-1]
        if isBreak:
            loop.hasBreak = True
            self.builder.branch(loop.breakBlock)
        else:
            self.builder.branch(loop.continueBlock)

    def visitInputStatement(self, node: InputStatement) -> None:
        for targetNode in node.targets:
            target = self.visitAddress(targetNode)
            if target is None:
                continue
            pointer, ctype = target
            if not self.isReadable(ctype):
                self.error(f"can't read a {ctype} from the input; read its elements one by one", targetNode)
                continue
            self.readInto(pointer, ctype)

    def isReadable(self, ctype: CType) -> bool:
        if ctype.kind == "pair":
            return self.isReadable(ctype.first) and self.isReadable(ctype.second)
        return ctype.kind in ["int", "char", "float", "bool", "string"]

    def readInto(self, pointer: ir.Value, ctype: CType) -> None:
        value: ir.Value
        match ctype.kind:
            case "pair":
                # a pair reads its two halves, one after the other
                for index, half in enumerate([ctype.first, ctype.second]):
                    self.readInto(self.builder.gep(pointer, [ir.Constant(I32, 0), ir.Constant(I32, index)], inbounds=True), half)
                return
            case "int":
                raw: ir.Value = self.callRuntime("cpl_read_i64" if ctype.signed else "cpl_read_u64", [])
                value = raw if ctype.bits == 64 else self.builder.trunc(raw, ctype.irType)
            case "char":
                value = self.callRuntime("cpl_read_char", [])
            case "float":
                value = self.callRuntime("cpl_read_f64", [])
            case "bool":
                value = self.builder.icmp_unsigned("!=", self.callRuntime("cpl_read_bool", []), ir.Constant(I8, 0))
            case _:
                value = self.callRuntime("cpl_read_str", [])
        self.store(value, pointer)

    def visitOutputStatement(self, node: OutputStatement) -> None:
        for valueNode in node.values:
            resolved: TypedValue | None = self.visitExpression(valueNode)
            if resolved is None:
                continue
            if not self.isPrintable(resolved.ctype):
                self.error(f"can't print a {resolved.ctype}; print its parts one by one", valueNode)
                continue
            self.printValue(resolved)

    def isPrintable(self, ctype: CType) -> bool:
        if ctype.kind == "pair":
            return self.isPrintable(ctype.first) and self.isPrintable(ctype.second)
        if ctype.kind == "vec":
            # vectors print their elements separated by spaces, but only one level deep
            return ctype.elem.kind != "vec" and self.isPrintable(ctype.elem)
        return ctype.kind in ["int", "char", "float", "bool", "string"]

    def printValue(self, resolved: TypedValue) -> None:
        value: ir.Value = resolved.value
        ctype: CType = resolved.ctype
        space: ir.Constant = ir.Constant(I8, ord(" "))

        match ctype.kind:
            case "pair":
                first, second = self.pairHalves(resolved)
                self.printValue(first)
                self.callRuntime("cpl_print_char", [space])
                self.printValue(second)
            case "vec":
                def printElement(index: ir.Value) -> None:
                    with self.builder.if_then(self.builder.icmp_signed(">", index, ir.Constant(I64, 0))):
                        self.callRuntime("cpl_print_char", [space])
                    self.printValue(TypedValue(self.load(self.vecSlot(value, ctype.elem, index)), ctype.elem))
                self.countedLoop(self.vecLength(value), printElement)
            case "int":
                if ctype.signed:
                    wide: ir.Value = value if ctype.bits == 64 else self.builder.sext(value, I64)
                    self.callRuntime("cpl_print_i64", [wide])
                else:
                    wide = value if ctype.bits == 64 else self.builder.zext(value, I64)
                    self.callRuntime("cpl_print_u64", [wide])
            case "char":
                self.callRuntime("cpl_print_char", [value])
            case "float":
                self.callRuntime("cpl_print_f64", [value])
            case "bool":
                self.callRuntime("cpl_print_bool", [self.builder.zext(value, I8)])
            case "string":
                self.callRuntime("cpl_print_str", [value])
    # endregion

    # region expressions
    def visitExpression(self, node: Expression, allowVoid: bool = False) -> TypedValue | None:
        result: TypedValue | None
        match node.type():
            case NodeType.IntegerLiteral:
                result = self.visitIntegerLiteral(node)
            case NodeType.DoubleLiteral:
                result = TypedValue(ir.Constant(DOUBLE, node.value), DU, literal=node.value)
            case NodeType.BooleanLiteral:
                result = TypedValue(ir.Constant(I1, int(node.value)), BO)
            case NodeType.CharLiteral:
                result = self.visitCharLiteral(node)
            case NodeType.StringLiteral:
                result = TypedValue(self.stringConstant(node.value), ST)
            case NodeType.NilLiteral:
                result = TypedValue(ir.Constant(BYTE_POINTER, None), NIL)
            case NodeType.IdentifierLiteral:
                result = self.visitIdentifier(node)
            case NodeType.PrefixExpression:
                result = self.visitPrefixExpression(node)
            case NodeType.InfixExpression:
                result = self.visitInfixExpression(node)
            case NodeType.CallExpression:
                result = self.visitCallExpression(node)
            case NodeType.IndexExpression:
                result = self.visitIndexExpression(node)
            case NodeType.MemberExpression:
                result = self.visitMemberExpression(node)
            case NodeType.CastExpression:
                result = self.visitCastExpression(node)
            case NodeType.ConditionalExpression:
                result = self.visitConditionalExpression(node)
            case _:
                self.error(f"can't compile expression of type {node.type().value}", node)
                return None

        if result is not None and result.ctype.kind == "void" and not allowVoid:
            self.error("this doesn't produce a value (the function returns nothing)", node)
            return None
        return result

    def visitIntegerLiteral(self, node) -> TypedValue | None:
        value: int = node.value
        if value < 2 ** 31:
            return TypedValue(ir.Constant(I32, value), IT, literal=value)
        if value < 2 ** 63:
            return TypedValue(ir.Constant(I64, value), LL, literal=value)
        if value < 2 ** 64:
            return TypedValue(ir.Constant(I64, value), ULL, literal=value)
        self.error(f"the number {value} is too big, even for ull", node)
        return None

    def visitCharLiteral(self, node) -> TypedValue | None:
        code: int = ord(node.value)
        if code > 255:
            self.error(f"character {node.value!r} doesn't fit in a ch; only single byte characters do", node)
            return None
        return TypedValue(ir.Constant(I8, code), CH)

    def stringConstant(self, text: str) -> ir.Constant:
        # a CplStr { len, data } header and its bytes, baked into the binary
        if text in self.stringConstants:
            return self.stringConstants[text]
        if text == "":
            # the empty string is a nil pointer everywhere
            return ir.Constant(BYTE_POINTER, None)

        number: int = len(self.stringConstants)
        data: bytearray = bytearray(text.encode("utf-8"))
        bytesType: ir.ArrayType = ir.ArrayType(I8, len(data))
        bytesConstant: ir.GlobalVariable = ir.GlobalVariable(self.module, bytesType, name=f"string.{number}.bytes")
        bytesConstant.linkage = "private"
        bytesConstant.global_constant = True
        bytesConstant.initializer = ir.Constant(bytesType, data)

        headerType: ir.LiteralStructType = ir.LiteralStructType([I64, BYTE_POINTER])
        header: ir.GlobalVariable = ir.GlobalVariable(self.module, headerType, name=f"string.{number}")
        header.linkage = "private"
        header.global_constant = True
        header.initializer = ir.Constant(headerType, [ir.Constant(I64, len(data)), bytesConstant.bitcast(BYTE_POINTER)])

        pointer: ir.Constant = header.bitcast(BYTE_POINTER)
        self.stringConstants[text] = pointer
        return pointer

    def visitIdentifier(self, node: IdentifierLiteral) -> TypedValue | None:
        record = self.environment.lookup(node.value)
        if record is None:
            if node.value in self.functions:
                self.error(f"'{node.value}' is a function; call it like {node.value}(...)", node)
            elif node.value in self.structs:
                self.error(f"'{node.value}' is a struct; create one like {node.value}(...)", node)
            else:
                self.error(f"'{node.value}' wasn't declared", node)
            return None

        pointer, ctype = record
        return TypedValue(self.load(pointer), ctype)

    def visitPrefixExpression(self, node: PrefixExpression) -> TypedValue | None:
        if node.operator == "!":
            condition: ir.Value | None = self.visitCondition(node.rightNode)
            if condition is None:
                return None
            return TypedValue(self.builder.not_(condition), BO)

        operand: TypedValue | None = self.visitExpression(node.rightNode)
        if operand is None:
            return None
        if operand.ctype.kind == "char":
            operand = TypedValue(self.builder.zext(operand.value, I32), IT)

        if node.operator == "-":
            if operand.literal is not None and operand.ctype.kind == "float":
                return TypedValue(ir.Constant(DOUBLE, -operand.literal), DU, literal=-operand.literal)
            if operand.literal is not None and operand.ctype.kind == "int" and operand.ctype.signed:
                return TypedValue(ir.Constant(operand.ctype.irType, -operand.literal), operand.ctype, literal=-operand.literal)
            if operand.ctype.kind == "float":
                return TypedValue(self.builder.fneg(operand.value), DU)
            if operand.ctype.kind == "int":
                return TypedValue(self.builder.neg(operand.value), operand.ctype)
        elif node.operator == "~":
            if operand.ctype.kind == "int":
                return TypedValue(self.builder.not_(operand.value), operand.ctype)

        self.error(f"operator {node.operator} doesn't work on {operand.ctype}", node)
        return None

    def visitInfixExpression(self, node: InfixExpression) -> TypedValue | None:
        if node.operator in ["&&", "||"]:
            return self.visitLogicalExpression(node)

        left: TypedValue | None = self.visitExpression(node.leftNode)
        right: TypedValue | None = self.visitExpression(node.rightNode)
        if left is None or right is None:
            return None

        return self.binaryOperation(node.operator, left, right, node)

    def visitConditionalExpression(self, node) -> TypedValue | None:
        # only the chosen side runs; both sides end up with a common type
        condition: ir.Value | None = self.visitCondition(node.condition)
        if condition is None:
            return None

        function: ir.Function = self.builder.function
        thenBlock: ir.Block = function.append_basic_block("choose_then")
        elseBlock: ir.Block = function.append_basic_block("choose_else")
        mergeBlock: ir.Block = function.append_basic_block("choose_end")
        self.builder.cbranch(condition, thenBlock, elseBlock)

        self.builder.position_at_end(thenBlock)
        consequence: TypedValue | None = self.visitExpression(node.consequence)
        thenEnd: ir.Block = self.builder.block
        self.builder.position_at_end(elseBlock)
        alternative: TypedValue | None = self.visitExpression(node.alternative)
        elseEnd: ir.Block = self.builder.block
        if consequence is None or alternative is None:
            return None

        leftType: CType = consequence.ctype
        rightType: CType = alternative.ctype
        if leftType == rightType:
            resultType: CType = leftType
        elif leftType.isNumeric and rightType.isNumeric:
            resultType = self.commonNumericType(leftType, rightType)
        elif leftType.kind == "nil" and rightType.kind == "struct" or leftType.kind == "struct" and rightType.kind == "nil":
            resultType = rightType if leftType.kind == "nil" else leftType
        else:
            self.error(f"the two sides of ? : must have the same type, not {leftType} and {rightType}", node)
            return None

        incoming: list[tuple[ir.Value, ir.Block]] = []
        for value, end, side in [(consequence, thenEnd, node.consequence), (alternative, elseEnd, node.alternative)]:
            self.builder.position_at_end(end)
            converted: ir.Value | None = self.convert(value, resultType, side, "", explicit=resultType.isNumeric)
            if converted is None:
                return None
            incoming.append((converted, self.builder.block))
            self.builder.branch(mergeBlock)

        self.builder.position_at_end(mergeBlock)
        result: ir.PhiInstr = self.builder.phi(resultType.irType)
        for value, block in incoming:
            result.add_incoming(value, block)
        return TypedValue(result, resultType)

    def visitLogicalExpression(self, node: InfixExpression) -> TypedValue | None:
        # short-circuit: the right side only runs when it can change the result
        isAnd: bool = node.operator == "&&"

        left: ir.Value | None = self.visitCondition(node.leftNode)
        if left is None:
            return None
        leftBlock: ir.Block = self.builder.block

        function: ir.Function = self.builder.function
        rightBlock: ir.Block = function.append_basic_block("logic_right")
        endBlock: ir.Block = function.append_basic_block("logic_end")
        if isAnd:
            self.builder.cbranch(left, rightBlock, endBlock)
        else:
            self.builder.cbranch(left, endBlock, rightBlock)

        self.builder.position_at_end(rightBlock)
        right: ir.Value | None = self.visitCondition(node.rightNode)
        if right is None:
            return None
        rightEndBlock: ir.Block = self.builder.block
        self.builder.branch(endBlock)

        self.builder.position_at_end(endBlock)
        result: ir.PhiInstr = self.builder.phi(I1)
        result.add_incoming(ir.Constant(I1, 0 if isAnd else 1), leftBlock)
        result.add_incoming(right, rightEndBlock)
        return TypedValue(result, BO)

    def binaryOperation(self, operator: str, left: TypedValue, right: TypedValue, node: Node) -> TypedValue | None:
        leftType: CType = left.ctype
        rightType: CType = right.ctype

        # strings: concatenation (with strings or characters) and comparison
        if leftType.kind == "string" or rightType.kind == "string":
            return self.stringOperation(operator, left, right, node)

        if leftType.kind == "pair" or rightType.kind == "pair":
            return self.pairComparison(operator, left, right, node)

        # structs can only be compared with each other or nil
        if leftType.kind in ["struct", "nil"] or rightType.kind in ["struct", "nil"]:
            bothPointers: bool = leftType.kind in ["struct", "nil"] and rightType.kind in ["struct", "nil"]
            compatible: bool = leftType == rightType or leftType.kind == "nil" or rightType.kind == "nil"
            if operator in ["==", "!="] and bothPointers and compatible:
                leftPointer: ir.Value = self.builder.bitcast(left.value, BYTE_POINTER)
                rightPointer: ir.Value = self.builder.bitcast(right.value, BYTE_POINTER)
                return TypedValue(self.builder.icmp_unsigned(operator, leftPointer, rightPointer), BO)
            self.error(f"operator {operator} doesn't work on {leftType} and {rightType}", node)
            return None

        if leftType.kind == "bool" or rightType.kind == "bool":
            if leftType.kind == "bool" and rightType.kind == "bool":
                match operator:
                    case "==" | "!=" | "<" | ">" | "<=" | ">=":
                        # false < true, so booleans can be sorted and kept in pairs
                        return TypedValue(self.builder.icmp_unsigned(operator, left.value, right.value), BO)
                    case "&":
                        return TypedValue(self.builder.and_(left.value, right.value), BO)
                    case "|":
                        return TypedValue(self.builder.or_(left.value, right.value), BO)
                    case "^^":
                        return TypedValue(self.builder.xor(left.value, right.value), BO)
            self.error(f"operator {operator} doesn't work on {leftType} and {rightType}", node)
            return None

        if not leftType.isNumeric or not rightType.isNumeric:
            self.error(f"operator {operator} doesn't work on {leftType} and {rightType}", node)
            return None

        commonType: CType = self.commonNumericType(leftType, rightType)
        leftValue: ir.Value = self.convert(left, commonType, node, "", explicit=True)
        rightValue: ir.Value = self.convert(right, commonType, node, "", explicit=True)

        if operator in COMPARISON_OPERATORS:
            if commonType.kind == "float":
                if operator == "!=":
                    return TypedValue(self.builder.fcmp_unordered(operator, leftValue, rightValue), BO)
                return TypedValue(self.builder.fcmp_ordered(operator, leftValue, rightValue), BO)
            if commonType.signed:
                return TypedValue(self.builder.icmp_signed(operator, leftValue, rightValue), BO)
            return TypedValue(self.builder.icmp_unsigned(operator, leftValue, rightValue), BO)

        if commonType.kind == "float":
            # fold literal arithmetic like 1e9 + 7, so it still counts as a literal for conversions
            if left.literal is not None and right.literal is not None and operator in ["+", "-", "*"]:
                folded: float = {"+": float.__add__, "-": float.__sub__, "*": float.__mul__}[operator](float(left.literal), float(right.literal))
                return TypedValue(ir.Constant(DOUBLE, folded), DU, literal=folded)
            match operator:
                case "+":
                    return TypedValue(self.builder.fadd(leftValue, rightValue), DU)
                case "-":
                    return TypedValue(self.builder.fsub(leftValue, rightValue), DU)
                case "*":
                    return TypedValue(self.builder.fmul(leftValue, rightValue), DU)
                case "/":
                    return TypedValue(self.builder.fdiv(leftValue, rightValue), DU)
                case "%":
                    return TypedValue(self.builder.frem(leftValue, rightValue), DU)
                case "^":
                    return TypedValue(self.builder.call(self.intrinsic("pow", 2), [leftValue, rightValue]), DU)
            self.error(f"operator {operator} only works on integers, not {commonType}", node)
            return None

        signed: bool = commonType.signed
        if left.literal is not None and right.literal is not None and operator in ["+", "-", "*"]:
            folded: int = {"+": int.__add__, "-": int.__sub__, "*": int.__mul__}[operator](int(left.literal), int(right.literal))
            low: int = -(2 ** (commonType.bits - 1)) if signed else 0
            high: int = 2 ** (commonType.bits - 1) if signed else 2 ** commonType.bits
            if low <= folded < high:
                return TypedValue(ir.Constant(commonType.irType, folded), commonType, literal=folded)
        match operator:
            case "+":
                return TypedValue(self.builder.add(leftValue, rightValue), commonType)
            case "-":
                return TypedValue(self.builder.sub(leftValue, rightValue), commonType)
            case "*":
                return TypedValue(self.builder.mul(leftValue, rightValue), commonType)
            case "/" | "%":
                self.checkNotZero(rightValue, commonType)
                if operator == "/":
                    value: ir.Value = self.builder.sdiv(leftValue, rightValue) if signed else self.builder.udiv(leftValue, rightValue)
                else:
                    value = self.builder.srem(leftValue, rightValue) if signed else self.builder.urem(leftValue, rightValue)
                return TypedValue(value, commonType)
            case "^":
                return TypedValue(self.integerPower(leftValue, rightValue, commonType), commonType)
            case "&":
                return TypedValue(self.builder.and_(leftValue, rightValue), commonType)
            case "|":
                return TypedValue(self.builder.or_(leftValue, rightValue), commonType)
            case "^^":
                return TypedValue(self.builder.xor(leftValue, rightValue), commonType)
            case "<<" | ">>":
                # shifting by the full width or more is undefined in LLVM, so wrap the amount like x86 does
                amount: ir.Value = self.builder.and_(rightValue, ir.Constant(commonType.irType, commonType.bits - 1))
                if operator == "<<":
                    return TypedValue(self.builder.shl(leftValue, amount), commonType)
                if signed:
                    return TypedValue(self.builder.ashr(leftValue, amount), commonType)
                return TypedValue(self.builder.lshr(leftValue, amount), commonType)

        self.error(f"unknown operator {operator}", node)
        return None

    def pairComparison(self, operator: str, left: TypedValue, right: TypedValue, node: Node) -> TypedValue | None:
        # pairs compare like tuples: by the first half, then by the second
        if left.ctype.kind != "pair" or right.ctype.kind != "pair" or operator not in COMPARISON_OPERATORS:
            self.error(f"operator {operator} doesn't work on {left.ctype} and {right.ctype}", node)
            return None

        if left.ctype != right.ctype:
            errorCount: int = len(self.errors)
            converted: ir.Value | None = self.convert(right, left.ctype, node, "")
            if converted is not None:
                right = TypedValue(converted, left.ctype)
            else:
                del self.errors[errorCount:]
                converted = self.convert(left, right.ctype, node, "")
                if converted is None:
                    del self.errors[errorCount:]
                    self.error(f"can't compare {left.ctype} with {right.ctype}", node)
                    return None
                left = TypedValue(converted, right.ctype)

        if operator in [">", "<="]:
            left, right = right, left
            operator = "<" if operator == ">" else ">="

        leftFirst, leftSecond = self.pairHalves(left)
        rightFirst, rightSecond = self.pairHalves(right)

        def compare(op: str, a: TypedValue, b: TypedValue) -> ir.Value:
            result: TypedValue | None = self.binaryOperation(op, a, b, node)
            if result is None:
                raise CompileError()
            return result.value

        if operator in ["==", "!="]:
            equal: ir.Value = self.builder.and_(compare("==", leftFirst, rightFirst), compare("==", leftSecond, rightSecond))
            return TypedValue(equal if operator == "==" else self.builder.not_(equal), BO)

        less: ir.Value = self.builder.or_(
            compare("<", leftFirst, rightFirst),
            self.builder.and_(compare("==", leftFirst, rightFirst), compare("<", leftSecond, rightSecond)),
        )
        return TypedValue(less if operator == "<" else self.builder.not_(less), BO)

    def stringOperation(self, operator: str, left: TypedValue, right: TypedValue, node: Node) -> TypedValue | None:
        leftValue: ir.Value | None = self.stringOperand(left)
        rightValue: ir.Value | None = self.stringOperand(right)

        if leftValue is not None and rightValue is not None:
            if operator == "+":
                if right.ctype.kind == "char":
                    return TypedValue(self.callRuntime("cpl_str_append_char", [left.value, right.value]), ST)
                if left.ctype.kind == "char":
                    leftValue = self.callRuntime("cpl_str_from_char", [left.value])
                return TypedValue(self.callRuntime("cpl_str_concat", [leftValue, rightValue]), ST)

            if operator in COMPARISON_OPERATORS and left.ctype.kind == "string" and right.ctype.kind == "string":
                comparison: ir.Value = self.callRuntime("cpl_str_cmp", [leftValue, rightValue])
                return TypedValue(self.builder.icmp_signed(operator, comparison, ir.Constant(I32, 0)), BO)

        hint: str = ""
        if operator == "+" and (left.ctype.isNumeric or right.ctype.isNumeric):
            hint = "; turn the number into a string first with st(x)"
        self.error(f"operator {operator} doesn't work on {left.ctype} and {right.ctype}{hint}", node)
        return None

    def stringOperand(self, operand: TypedValue) -> ir.Value | None:
        # only checks that the operand can take part; characters become strings lazily below
        if operand.ctype.kind in ["string", "char"]:
            return operand.value
        return None

    def commonNumericType(self, leftType: CType, rightType: CType) -> CType:
        if leftType.kind == "float" or rightType.kind == "float":
            return DU

        # index arithmetic is done in 64 bits: an index that would overflow an it is out of bounds
        # anyway, and it lets LLVM treat v[i - w] as plain address arithmetic
        if self.indexDepth > 0:
            unsigned: bool = (leftType.kind == "int" and not leftType.signed and leftType.bits == 64) or \
                             (rightType.kind == "int" and not rightType.signed and rightType.bits == 64)
            return ULL if unsigned else LL

        # characters do arithmetic as it, like in C
        if leftType.kind == "char":
            leftType = IT
        if rightType.kind == "char":
            rightType = IT

        if leftType.bits != rightType.bits:
            return leftType if leftType.bits > rightType.bits else rightType
        return integerFor(leftType.bits, leftType.signed and rightType.signed)

    def checkNotZero(self, value: ir.Value, ctype: CType) -> None:
        isZero: ir.Value = self.builder.icmp_unsigned("==", value, ir.Constant(ctype.irType, 0))
        with self.builder.if_then(isZero, likely=False):
            self.callRuntime("cpl_panic_div", [])
            self.builder.unreachable()

    def integerPower(self, base: ir.Value, exponent: ir.Value, ctype: CType) -> ir.Value:
        extend = self.builder.sext if ctype.signed else self.builder.zext
        if ctype.bits < 64:
            base = extend(base, I64)
            exponent = extend(exponent, I64)
        result: ir.Value = self.callRuntime("cpl_ipow", [base, exponent])
        return result if ctype.bits == 64 else self.builder.trunc(result, ctype.irType)

    def visitCondition(self, node: Expression) -> ir.Value | None:
        resolved: TypedValue | None = self.visitExpression(node)
        if resolved is None:
            return None

        value: ir.Value = resolved.value
        match resolved.ctype.kind:
            case "bool":
                return value
            case "int" | "char":
                return self.builder.icmp_unsigned("!=", value, ir.Constant(resolved.ctype.irType, 0))
            case "float":
                return self.builder.fcmp_unordered("!=", value, ir.Constant(DOUBLE, 0.0))

        self.error(f"a {resolved.ctype} can't be used as a condition", node)
        return None
    # endregion

    # region calls
    def visitCallExpression(self, node: CallExpression) -> TypedValue | None:
        if node.function.type() == NodeType.MemberExpression:
            return self.visitMethodCall(node.function.leftNode, node.function.name, node.arguments, node)

        if node.function.type() != NodeType.IdentifierLiteral:
            self.error("only functions can be called", node)
            return None

        name: str = node.function.value
        if name in self.functions:
            return self.callFunction(self.functions[name], node)
        if name in self.structs:
            return self.constructStruct(self.structs[name], node)
        if name in BUILTINS:
            return BUILTINS[name](self, node)
        if self.environment.lookup(name) is not None:
            self.error(f"'{name}' is a variable, not a function", node)
        else:
            self.error(f"unknown function '{name}'", node)
        return None

    def visitArguments(self, node: CallExpression, expected: list[tuple[str, CType]], what: str) -> list[ir.Value] | None:
        if len(node.arguments) != len(expected):
            self.error(f"{what} takes {len(expected)} argument{'s' if len(expected) != 1 else ''} but got {len(node.arguments)}", node)
            return None

        values: list[ir.Value] = []
        for argumentNode, (name, ctype) in zip(node.arguments, expected):
            resolved: TypedValue | None = self.visitExpression(argumentNode)
            if resolved is None:
                return None
            value: ir.Value | None = self.convert(resolved, ctype, argumentNode, f"argument '{name}' of {what}")
            if value is None:
                return None
            values.append(value)
        return values

    def callFunction(self, info: FunctionInfo, node: CallExpression) -> TypedValue | None:
        arguments: list[ir.Value] | None = self.visitArguments(node, info.parameters, info.name)
        if arguments is None:
            return None
        return TypedValue(self.builder.call(info.irFunction, arguments), info.returnType)

    def constructStruct(self, ctype: CType, node: CallExpression) -> TypedValue | None:
        # Point() gives the defaults, Point(1, 2) sets every field in order
        if len(node.arguments) == 0:
            return TypedValue(self.allocateStruct(ctype), ctype)

        values: list[ir.Value] | None = self.visitArguments(node, ctype.struct.fields, ctype.name)
        if values is None:
            return None
        pointer: ir.Value = self.allocateStruct(ctype, initializeFields=False)
        for index, value in enumerate(values):
            self.store(value, self.structField(pointer, ctype, index))
        return TypedValue(pointer, ctype)

    def visitMethodCall(self, objectNode: Expression, name: str, arguments: list[Expression], node: CallExpression) -> TypedValue | None:
        method: str = METHOD_ALIASES.get(name, name)
        target: TypedValue | None = self.visitExpression(objectNode)
        if target is None:
            return None

        ctype: CType = target.ctype
        if ctype.kind == "vec" and method == "srt" and len(arguments) == 1:
            try:
                return self.sortWithComparator(target, arguments[0], node)
            except CompileError:
                return None

        handler = METHODS.get(ctype.kind, {}).get(method)
        if handler is None:
            if ctype.kind == "struct" and ctype.struct.fieldIndex(name) is not None:
                self.error(f"'{name}' is a field of {ctype}, not a method", node)
            else:
                self.error(f"{ctype} has no method '{name}'", node)
            return None

        expectedCount: int = handler.__code__.co_argcount - 3
        if len(arguments) != expectedCount:
            self.error(f"{name}() takes {expectedCount} argument{'s' if expectedCount != 1 else ''} but got {len(arguments)}", node)
            return None

        resolvedArguments: list[TypedValue] = []
        for argument in arguments:
            resolved: TypedValue | None = self.visitExpression(argument)
            if resolved is None:
                return None
            resolvedArguments.append(resolved)

        try:
            return handler(self, target, node, *resolvedArguments)
        except CompileError:
            return None

    def sortWithComparator(self, target: TypedValue, argument: Expression, node: Node) -> TypedValue:
        # v.srt(before) sorts with a function 'f before(a: T, b: T) -> bo' that says whether a goes first
        elem: CType = target.ctype.elem
        usage: str = f"v.srt(name) needs the name of a function like 'f before(a: {elem}, b: {elem}) -> bo'"
        if argument.type() != NodeType.IdentifierLiteral or argument.value not in self.functions:
            self.error(usage, argument)
            raise CompileError()

        comparator: FunctionInfo = self.functions[argument.value]
        parameterTypes: list[CType] = [ctype for _, ctype in comparator.parameters]
        if parameterTypes != [elem, elem] or comparator.returnType != BO:
            signature: str = ", ".join(str(ctype) for ctype in parameterTypes)
            self.error(f"{usage}, but {comparator.name} is ({signature}) -> {comparator.returnType}", argument)
            raise CompileError()

        self.sortVec(target.value, elem, node, comparator)
        return TypedValue(None, VO)

    def expect(self, value: TypedValue, ctype: CType, node: Node, context: str) -> ir.Value:
        # converts or raises, for the many builtins that take a fixed type
        converted: ir.Value | None = self.convert(value, ctype, node, context)
        if converted is None:
            raise CompileError()
        return converted
    # endregion

    # region vectors and maps
    def vecField(self, vec: ir.Value, index: int) -> ir.Value:
        return self.withTag(self.builder.gep(vec, [ir.Constant(I32, 0), ir.Constant(I32, index)], inbounds=True), "vec header")

    def vecLength(self, vec: ir.Value) -> ir.Value:
        return self.load(self.vecField(vec, 0))

    def vecData(self, vec: ir.Value, elem: CType) -> ir.Value:
        data: ir.Value = self.load(self.vecField(vec, 3))
        return self.builder.bitcast(data, elem.irType.as_pointer())

    def vecSlot(self, vec: ir.Value, elem: CType, index: ir.Value) -> ir.Value:
        return self.withTag(self.builder.gep(self.vecData(vec, elem), [index], inbounds=True), self.elementTag(elem))

    def vecElementPointer(self, vec: ir.Value, elem: CType, index: ir.Value) -> ir.Value:
        length: ir.Value = self.vecLength(vec)
        # one unsigned comparison catches negative indices too
        outOfBounds: ir.Value = self.builder.icmp_unsigned(">=", index, length)
        with self.builder.if_then(outOfBounds, likely=False):
            self.callRuntime("cpl_panic_index", [index, length])
            self.builder.unreachable()

        return self.vecSlot(vec, elem, index)

    def mapKey(self, value: ir.Value, ctype: CType) -> ir.Value:
        # every map key travels to the runtime as 64 bits
        match ctype.kind:
            case "pair":
                # (first, second) packed into one number that sorts the same way
                packed: list[ir.Value] = []
                for index, half in enumerate([ctype.first, ctype.second]):
                    part: ir.Value = self.builder.extract_value(value, index)
                    if half.bits < 32:
                        part = self.builder.zext(part, I32)
                    if half.kind == "int" and half.signed:
                        part = self.builder.xor(part, ir.Constant(I32, 1 << 31))
                    packed.append(self.builder.zext(part, I64))
                return self.builder.or_(self.builder.shl(packed[0], ir.Constant(I64, 32)), packed[1])
            case "int":
                if ctype.bits == 64:
                    return value
                return self.builder.sext(value, I64) if ctype.signed else self.builder.zext(value, I64)
            case "char" | "bool":
                return self.builder.zext(value, I64)
            case "float":
                return self.builder.bitcast(value, I64)
        return self.builder.ptrtoint(value, I64)

    def unpackMapKey(self, packed: ir.Value, ctype: CType) -> ir.Value:
        halves: list[ir.Value] = []
        for index, half in enumerate([ctype.first, ctype.second]):
            part: ir.Value = self.builder.lshr(packed, ir.Constant(I64, 32)) if index == 0 else packed
            part = self.builder.trunc(part, I32)
            if half.kind == "int" and half.signed:
                part = self.builder.xor(part, ir.Constant(I32, 1 << 31))
            if half.bits < 32:
                part = self.builder.trunc(part, half.irType)
            halves.append(part)
        return self.makePair(ctype, halves[0], halves[1])

    def mapSlot(self, mapValue: ir.Value, mapType: CType, keyValue: TypedValue, node: Node) -> ir.Value | None:
        key: ir.Value | None = self.convert(keyValue, mapType.key, node, "the map key")
        if key is None:
            return None

        inserted: ir.Value = self.allocate(I8, "inserted")
        # counted, because a new key can move the map's other values (see builtinSwap)
        self.mapSlotCount += 1
        slot: ir.Value = self.callRuntime("cpl_map_at", [mapValue, self.mapKey(key, mapType.key), inserted])
        pointer: ir.Value = self.builder.bitcast(slot, mapType.value.irType.as_pointer())

        # like C++, reading a missing key inserts the default value; containers and structs need a real object
        if mapType.value.isContainer:
            wasInserted: ir.Value = self.builder.icmp_unsigned("!=", self.builder.load(inserted), ir.Constant(I8, 0))
            with self.builder.if_then(wasInserted):
                self.builder.store(self.defaultValue(mapType.value), pointer)
        return pointer

    def elementSize(self, ctype: CType) -> int:
        # bytes per element in a vector, as LLVM lays the type out on this machine
        key: str = str(ctype.irType)
        if key not in self.typeSizes:
            self.typeSizes[key] = ctype.irType.get_abi_size(self.targetData, context=self.module.context)
        return self.typeSizes[key]

    def newVec(self, elem: CType, length: ir.Value, elemTypeExpression: TypeExpression | None = None) -> ir.Value:
        vec: ir.Value = self.callRuntime("cpl_vec_new", [ir.Constant(I64, self.elementSize(elem)), length])

        # zeroed memory is a fine default for numbers and strings, but containers and structs need real objects
        if elem.isContainer:
            self.fillVec(vec, elem, lambda: self.defaultValue(elem, elemTypeExpression))
        return vec

    def fillVec(self, vec: ir.Value, elem: CType, makeValue: callable) -> None:
        self.countedLoop(self.vecLength(vec), lambda index: self.store(makeValue(), self.vecSlot(vec, elem, index)))

    def countedLoop(self, count: ir.Value, body: callable) -> None:
        # for (index = 0; index < count; index++) body(index), with an i64 index
        function: ir.Function = self.builder.function
        conditionBlock: ir.Block = function.append_basic_block("loop_condition")
        bodyBlock: ir.Block = function.append_basic_block("loop_body")
        endBlock: ir.Block = function.append_basic_block("loop_end")

        counter: ir.Value = self.allocate(I64, "i")
        self.builder.store(ir.Constant(I64, 0), counter)
        self.builder.branch(conditionBlock)

        self.builder.position_at_end(conditionBlock)
        index: ir.Value = self.builder.load(counter)
        self.builder.cbranch(self.builder.icmp_signed("<", index, count), bodyBlock, endBlock)

        self.builder.position_at_end(bodyBlock)
        body(index)
        self.builder.store(self.builder.add(index, ir.Constant(I64, 1)), counter)
        self.builder.branch(conditionBlock)

        self.builder.position_at_end(endBlock)

    def allocateStruct(self, ctype: CType, initializeFields: bool = True) -> ir.Value:
        info: StructInfo = ctype.struct
        size: ir.Constant = ir.Constant(ctype.irType, None).gep([ir.Constant(I32, 1)]).ptrtoint(I64)
        pointer: ir.Value = self.builder.bitcast(self.callRuntime("cpl_alloc", [size]), ctype.irType)
        if not initializeFields:
            return pointer

        # struct fields start out as nil (so linked lists and trees don't recurse forever), containers start empty
        typeExpressions: list[TypeExpression] = self.structFieldTypes.get(info.name, [])
        for index, (_, fieldType) in enumerate(info.fields):
            if fieldType.isContainer and fieldType.kind != "struct":
                typeExpression: TypeExpression | None = typeExpressions[index] if index < len(typeExpressions) else None
                self.store(self.defaultValue(fieldType, typeExpression), self.structField(pointer, ctype, index))
        return pointer

    def defaultValue(self, ctype: CType, typeExpression: TypeExpression | None = None) -> ir.Value:
        match ctype.kind:
            case "vec":
                # arr<T, N> is a vec<T> that starts with N elements
                length: int = 0
                elemTypeExpression: TypeExpression | None = None
                if typeExpression is not None and typeExpression.name in ["vec", "arr"]:
                    elemTypeExpression = typeExpression.arguments[0]
                    if typeExpression.name == "arr":
                        length = typeExpression.arguments[1]
                return self.newVec(ctype.elem, ir.Constant(I64, length), elemTypeExpression)
            case "map":
                return self.callRuntime("cpl_map_new", [ir.Constant(I32, self.mapKeyKind(ctype.key))])
            case "pq":
                return self.callRuntime("cpl_vec_new", [ir.Constant(I64, self.elementSize(ctype.elem)), ir.Constant(I64, 0)])
            case "struct":
                return self.allocateStruct(ctype)
        # numbers are 0, booleans false and strings empty (a nil string pointer)
        return ir.Constant(ctype.irType, None)
    # endregion

    # region indexing and members
    def structField(self, pointer: ir.Value, ctype: CType, index: int) -> ir.Value:
        field: ir.Value = self.builder.gep(pointer, [ir.Constant(I32, 0), ir.Constant(I32, index)], inbounds=True)
        return self.withTag(field, f"struct {ctype.name} field {index}")

    def visitIndexValue(self, expression: Expression) -> TypedValue | None:
        self.indexDepth += 1
        try:
            return self.visitExpression(expression)
        finally:
            self.indexDepth -= 1

    def visitIndexExpression(self, node: IndexExpression) -> TypedValue | None:
        container: TypedValue | None = self.visitExpression(node.leftNode)
        if container is None:
            return None

        if container.ctype.kind == "string":
            index: TypedValue | None = self.visitIndexValue(node.index)
            if index is None:
                return None
            if not index.ctype.isInteger:
                self.error(f"string indices must be integers, not {index.ctype}", node.index)
                return None
            indexValue: ir.Value = self.convert(index, LL, node.index, "the index")
            return TypedValue(self.stringByte(container.value, indexValue, checked=id(node) not in self.uncheckedIndexes), CH)

        address = self.indexAddress(container, node)
        if address is None:
            return None
        pointer, ctype = address
        return TypedValue(self.load(pointer), ctype)

    def indexAddress(self, container: TypedValue, node: IndexExpression) -> tuple[ir.Value, CType] | None:
        if container.ctype.kind == "string":
            self.error("strings can't be changed in place; build a new one, like s = s.sub(0, i) + 'x' + s.sub(i + 1, s.sz())", node)
            return None
        if container.ctype.kind not in ["vec", "map"]:
            self.error(f"a {container.ctype} can't be indexed", node)
            return None

        index: TypedValue | None = self.visitIndexValue(node.index) if container.ctype.kind == "vec" else self.visitExpression(node.index)
        if index is None:
            return None

        if container.ctype.kind == "vec":
            if not index.ctype.isInteger:
                self.error(f"vector indices must be integers, not {index.ctype}", node.index)
                return None
            indexValue: ir.Value = self.convert(index, LL, node.index, "the index")
            if id(node) in self.uncheckedIndexes:
                return self.vecSlot(container.value, container.ctype.elem, indexValue), container.ctype.elem
            return self.vecElementPointer(container.value, container.ctype.elem, indexValue), container.ctype.elem

        pointer: ir.Value | None = self.mapSlot(container.value, container.ctype, index, node.index)
        if pointer is None:
            return None
        return pointer, container.ctype.value

    def visitMemberExpression(self, node: MemberExpression) -> TypedValue | None:
        owner: TypedValue | None = self.visitExpression(node.leftNode)
        if owner is None:
            return None

        if owner.ctype.kind == "pair":
            index: int | None = self.pairFieldIndex(owner.ctype, node)
            if index is None:
                return None
            half: CType = owner.ctype.first if index == 0 else owner.ctype.second
            return TypedValue(self.builder.extract_value(owner.value, index), half)

        address = self.structMemberAddress(owner, node)
        if address is None:
            return None
        pointer, ctype = address
        return TypedValue(self.load(pointer), ctype)

    def pairFieldIndex(self, ctype: CType, node: MemberExpression) -> int | None:
        index: int | None = PAIR_FIELDS.get(node.name)
        if index is None:
            self.error(f"a {ctype} has the fields f and s (or first and second), not '{node.name}'", node)
        return index

    def memberAddress(self, node: MemberExpression) -> tuple[ir.Value, CType] | None:
        # the parts of a pair live inside its variable or element, so they need the owner's address
        if node.leftNode.type() in [NodeType.IdentifierLiteral, NodeType.IndexExpression, NodeType.MemberExpression]:
            ownerAddress = self.visitAddress(node.leftNode)
            if ownerAddress is None:
                return None
            ownerPointer, ownerType = ownerAddress
            if ownerType.kind == "pair":
                index: int | None = self.pairFieldIndex(ownerType, node)
                if index is None:
                    return None
                half: CType = ownerType.first if index == 0 else ownerType.second
                return self.builder.gep(ownerPointer, [ir.Constant(I32, 0), ir.Constant(I32, index)], inbounds=True), half
            owner: TypedValue = TypedValue(self.load(ownerPointer), ownerType)
        else:
            owner = self.visitExpression(node.leftNode)
            if owner is None:
                return None
            if owner.ctype.kind == "pair":
                self.error("can't change part of a temporary pair; store it in a variable first", node)
                return None
        return self.structMemberAddress(owner, node)

    def structMemberAddress(self, owner: TypedValue, node: MemberExpression) -> tuple[ir.Value, CType] | None:
        if owner.ctype.kind != "struct":
            method: str = METHOD_ALIASES.get(node.name, node.name)
            if method in METHODS.get(owner.ctype.kind, {}):
                self.error(f"'{node.name}' is a method; call it like .{node.name}()", node)
            else:
                self.error(f"a {owner.ctype} has no field '{node.name}'", node)
            return None

        info: StructInfo = owner.ctype.struct
        index: int | None = info.fieldIndex(node.name)
        if index is None:
            self.error(f"struct {info.name} has no field '{node.name}'", node)
            return None

        isNil: ir.Value = self.builder.icmp_unsigned("==", owner.value, ir.Constant(owner.ctype.irType, None))
        with self.builder.if_then(isNil, likely=False):
            self.callRuntime("cpl_panic_nil", [])
            self.builder.unreachable()

        return self.structField(owner.value, owner.ctype, index), info.fields[index][1]

    def visitAddress(self, node: Expression) -> tuple[ir.Value, CType] | None:
        # where an assignment or input stores its value
        match node.type():
            case NodeType.IdentifierLiteral:
                record = self.environment.lookup(node.value)
                if record is None:
                    self.error(f"'{node.value}' wasn't declared", node)
                    return None
                return record
            case NodeType.IndexExpression:
                container: TypedValue | None = self.visitExpression(node.leftNode)
                if container is None:
                    return None
                return self.indexAddress(container, node)
            case NodeType.MemberExpression:
                return self.memberAddress(node)

        self.error("can't assign to this; only variables, elements like v[i] and fields like p.x can be assigned", node)
        return None
    # endregion

    # region conversions
    def visitCastExpression(self, node: CastExpression) -> TypedValue | None:
        if node.targetType.name == "pr":
            return self.constructPair(node)

        target: CType | None = self.resolveType(node.targetType)
        if target is None:
            return None

        if target.kind == "vec":
            return self.constructVec(target, node)
        if target.kind in ["map", "pq"]:
            if node.arguments:
                self.error(f"{target}() doesn't take arguments", node)
                return None
            return TypedValue(self.defaultValue(target), target)
        if target.kind == "void":
            self.error("can't convert to vo", node)
            return None

        if len(node.arguments) != 1:
            self.error(f"{target}(...) takes exactly one value to convert", node)
            return None

        source: TypedValue | None = self.visitExpression(node.arguments[0])
        if source is None:
            return None

        if target.kind == "string":
            return self.toString(source, node)

        if source.ctype.kind == "string":
            if target.kind == "int":
                parsed: TypedValue = TypedValue(self.callRuntime("cpl_str_to_i64", [source.value]), LL)
                return TypedValue(self.convert(parsed, target, node, "", explicit=True), target)
            if target.kind == "float":
                return TypedValue(self.callRuntime("cpl_str_to_f64", [source.value]), DU)
            self.error(f"can't convert a string to {target}", node)
            return None

        value: ir.Value | None = self.convert(source, target, node, "the conversion", explicit=True)
        if value is None:
            return None
        return TypedValue(value, target)

    def constructPair(self, node: CastExpression) -> TypedValue | None:
        # pr(a, b) takes its types from a and b; pr<A, B>(a, b) converts them; pr<A, B>() is the default
        target: CType | None = None
        if node.targetType.arguments:
            target = self.resolveType(node.targetType)
            if target is None:
                return None
            if not node.arguments:
                return TypedValue(ir.Constant(target.irType, None), target)

        if len(node.arguments) != 2:
            self.error(f"a pair is made from two values, as in pr(a, b), not {len(node.arguments)}", node)
            return None

        halves: list[TypedValue] = []
        for argument in node.arguments:
            resolved: TypedValue | None = self.visitExpression(argument)
            if resolved is None:
                return None
            halves.append(resolved)

        if target is None:
            target = self.pairType(halves[0].ctype, halves[1].ctype, node)
            if target is None:
                return None

        first: ir.Value | None = self.convert(halves[0], target.first, node.arguments[0], "the first half of the pair")
        second: ir.Value | None = self.convert(halves[1], target.second, node.arguments[1], "the second half of the pair")
        if first is None or second is None:
            return None
        return TypedValue(self.makePair(target, first, second), target)

    def makePair(self, ctype: CType, first: ir.Value, second: ir.Value) -> ir.Value:
        value: ir.Value = self.builder.insert_value(ir.Constant(ctype.irType, ir.Undefined), first, 0)
        return self.builder.insert_value(value, second, 1)

    def pairHalves(self, pair: TypedValue) -> tuple[TypedValue, TypedValue]:
        return (TypedValue(self.builder.extract_value(pair.value, 0), pair.ctype.first),
                TypedValue(self.builder.extract_value(pair.value, 1), pair.ctype.second))

    def constructVec(self, target: CType, node: CastExpression) -> TypedValue | None:
        # vec<T>() is empty, vec<T>(n) has n default elements, vec<T>(n, x) has n copies of x
        if node.targetType.name == "arr":
            if node.arguments:
                self.error("arr<T, N>() already has its size; it doesn't take arguments", node)
                return None
            return TypedValue(self.defaultValue(target, node.targetType), target)

        if len(node.arguments) > 2:
            self.error(f"{target}(...) takes at most a size and a value", node)
            return None
        if len(node.arguments) == 0:
            return TypedValue(self.defaultValue(target, node.targetType), target)

        size: TypedValue | None = self.visitExpression(node.arguments[0])
        if size is None:
            return None
        if not size.ctype.isInteger:
            self.error(f"the size of a vector must be an integer, not {size.ctype}", node.arguments[0])
            return None
        length: ir.Value = self.convert(size, LL, node, "")

        if len(node.arguments) == 1:
            return TypedValue(self.newVec(target.elem, length, node.targetType.arguments[0]), target)

        if target.elem.isContainer:
            self.error(f"vec<{target.elem}>(n, x) would share one {target.elem} between all elements; use vec<{target.elem}>(n) instead", node)
            return None
        fill: TypedValue | None = self.visitExpression(node.arguments[1])
        if fill is None:
            return None
        fillValue: ir.Value | None = self.convert(fill, target.elem, node.arguments[1], "the fill value")
        if fillValue is None:
            return None

        vec: ir.Value = self.callRuntime("cpl_vec_new", [ir.Constant(I64, self.elementSize(target.elem)), length])
        self.fillVec(vec, target.elem, lambda: fillValue)
        return TypedValue(vec, target)

    def toString(self, source: TypedValue, node: Node) -> TypedValue | None:
        value: ir.Value = source.value
        ctype: CType = source.ctype
        match ctype.kind:
            case "string":
                return source
            case "char":
                return TypedValue(self.callRuntime("cpl_str_from_char", [value]), ST)
            case "bool":
                return TypedValue(self.callRuntime("cpl_str_from_bool", [self.builder.zext(value, I8)]), ST)
            case "float":
                return TypedValue(self.callRuntime("cpl_str_from_f64", [value]), ST)
            case "int":
                if ctype.signed:
                    wide: ir.Value = value if ctype.bits == 64 else self.builder.sext(value, I64)
                    return TypedValue(self.callRuntime("cpl_str_from_i64", [wide]), ST)
                wide = value if ctype.bits == 64 else self.builder.zext(value, I64)
                return TypedValue(self.callRuntime("cpl_str_from_u64", [wide]), ST)

        self.error(f"can't convert a {ctype} to a string", node)
        return None

    def convert(self, source: TypedValue, target: CType, node: Node, context: str, explicit: bool = False) -> ir.Value | None:
        # implicit conversions: between integer types, integers to du, and nil to structs;
        # explicit ones (it(x), du(x), ...) also allow du to integers and booleans to and from numbers
        sourceType: CType = source.ctype
        value: ir.Value = source.value

        if sourceType == target:
            return value

        if sourceType.kind == "nil" and target.kind == "struct":
            return ir.Constant(target.irType, None)

        if sourceType.kind == "pair" and target.kind == "pair":
            # half by half, so pr(0, 1) can become a pr<ll, ll>
            first, second = self.pairHalves(source)
            where: str = f"{context}, " if context else ""
            firstValue: ir.Value | None = self.convert(first, target.first, node, f"{where}first half", explicit)
            secondValue: ir.Value | None = self.convert(second, target.second, node, f"{where}second half", explicit)
            if firstValue is None or secondValue is None:
                return None
            return self.makePair(target, firstValue, secondValue)

        if sourceType.isInteger and target.isInteger:
            if sourceType.bits == target.bits:
                return value
            if sourceType.bits > target.bits:
                return self.builder.trunc(value, target.irType)
            if sourceType.kind == "int" and sourceType.signed:
                return self.builder.sext(value, target.irType)
            return self.builder.zext(value, target.irType)

        if sourceType.isInteger and target.kind == "float":
            if sourceType.kind == "int" and sourceType.signed:
                return self.builder.sitofp(value, DOUBLE)
            return self.builder.uitofp(value, DOUBLE)

        # whole number literals like 1e18 or 2,0 may become integers, as in 'll infinity = 1e18'
        if sourceType.kind == "float" and target.isInteger and source.literal is not None and float(source.literal).is_integer():
            number: int = int(source.literal)
            low: int = -(2 ** (target.bits - 1)) if target.kind == "int" and target.signed else 0
            high: int = 2 ** (target.bits - 1) if target.kind == "int" and target.signed else 2 ** target.bits
            if low <= number < high:
                return ir.Constant(target.irType, number)

        if explicit:
            if sourceType.kind == "float" and target.isInteger:
                if target.kind == "int" and target.signed:
                    return self.builder.fptosi(value, target.irType)
                return self.builder.fptoui(value, target.irType)
            if sourceType.kind == "bool" and target.isNumeric:
                if target.kind == "float":
                    return self.builder.uitofp(value, DOUBLE)
                return self.builder.zext(value, target.irType)
            if sourceType.isNumeric and target.kind == "bool":
                if sourceType.kind == "float":
                    return self.builder.fcmp_unordered("!=", value, ir.Constant(DOUBLE, 0.0))
                return self.builder.icmp_unsigned("!=", value, ir.Constant(sourceType.irType, 0))

        hint: str = ""
        if sourceType.kind == "float" and target.isInteger:
            hint = f"; use {target}(x) to cut off the decimals"
        elif sourceType.kind == "bool" and target.isNumeric:
            hint = f"; use {target}(x) to turn it into 0 or 1"
        elif target.kind == "string" and sourceType.kind in ["int", "char", "float", "bool"]:
            hint = "; use st(x) to turn it into a string"
        where: str = f" in {context}" if context else ""
        self.error(f"can't convert {sourceType} to {target}{where}{hint}", node)
        return None
    # endregion

    # region helpers
    def invariantLoad(self, pointer: ir.Value, tag: str) -> ir.Value:
        # strings never change after they're made, so LLVM may hoist and merge these loads freely
        load: ir.Instruction = self.tagged(self.builder.load(pointer), tag)
        if self.invariantNode is None:
            self.invariantNode = self.module.add_metadata([])
        load.set_metadata("invariant.load", self.invariantNode)
        return load

    def stringHeader(self, string: ir.Value) -> ir.Value:
        return self.builder.bitcast(string, ir.LiteralStructType([I64, BYTE_POINTER]).as_pointer())

    def stringLength(self, string: ir.Value) -> ir.Value:
        # a nil string is empty; bit 62 of the stored length is the runtime's "growable" flag
        isNil: ir.Value = self.builder.icmp_unsigned("==", string, ir.Constant(BYTE_POINTER, None))
        before: ir.Block = self.builder.block
        function: ir.Function = self.builder.function
        loadBlock: ir.Block = function.append_basic_block("string_length")
        doneBlock: ir.Block = function.append_basic_block("string_length_done")
        self.builder.cbranch(isNil, doneBlock, loadBlock)

        self.builder.position_at_end(loadBlock)
        field: ir.Value = self.builder.gep(self.stringHeader(string), [ir.Constant(I32, 0), ir.Constant(I32, 0)], inbounds=True)
        stored: ir.Value = self.invariantLoad(field, "string header")
        length: ir.Value = self.builder.and_(stored, ir.Constant(I64, (1 << 62) - 1))
        self.builder.branch(doneBlock)

        self.builder.position_at_end(doneBlock)
        result: ir.PhiInstr = self.builder.phi(I64)
        result.add_incoming(ir.Constant(I64, 0), before)
        result.add_incoming(length, loadBlock)
        return result

    def stringByte(self, string: ir.Value, index: ir.Value, checked: bool = True) -> ir.Value:
        if checked:
            length: ir.Value = self.stringLength(string)
            with self.builder.if_then(self.builder.icmp_unsigned(">=", index, length), likely=False):
                self.callRuntime("cpl_panic_index", [index, length])
                self.builder.unreachable()
        field: ir.Value = self.builder.gep(self.stringHeader(string), [ir.Constant(I32, 0), ir.Constant(I32, 1)], inbounds=True)
        data: ir.Value = self.invariantLoad(field, "string header")
        return self.invariantLoad(self.builder.gep(data, [index], inbounds=True), "string bytes")

    def tbaaTag(self, name: str) -> ir.Value:
        if name not in self.tbaaTags:
            typeNode = self.module.add_metadata([name, self.tbaaRoot, ir.Constant(I64, 0)])
            self.tbaaTags[name] = self.module.add_metadata([typeNode, typeNode, ir.Constant(I64, 0)])
        return self.tbaaTags[name]

    def tagged(self, instruction: ir.Instruction, name: str | None) -> ir.Instruction:
        if name is not None:
            instruction.set_metadata("tbaa", self.tbaaTag(name))
        return instruction

    def elementTag(self, elem: CType) -> str:
        return f"vec element {elem.irType}"

    def load(self, pointer: ir.Value) -> ir.Value:
        # loads through an address that may carry an alias class (see pointerTags)
        return self.tagged(self.builder.load(pointer), self.pointerTags.get(pointer))

    def store(self, value: ir.Value, pointer: ir.Value) -> None:
        self.tagged(self.builder.store(value, pointer), self.pointerTags.get(pointer))

    def withTag(self, pointer: ir.Value, name: str) -> ir.Value:
        self.pointerTags[pointer] = name
        return pointer

    def currentBlockTerminated(self) -> bool:
        block = self.builder.block
        return block is not None and block.is_terminated
    # endregion


def walk(value):
    # every node under value, depth first
    if isinstance(value, list) or isinstance(value, tuple):
        for item in value:
            yield from walk(item)
        return
    if not isinstance(value, Node):
        return
    yield value
    for child in vars(value).values():
        yield from walk(child)


def declaredNames(body) -> set[str]:
    names: set[str] = set()
    for node in walk(body):
        if node.type() in [NodeType.ShallStatement, NodeType.ForEachStatement]:
            names.update(node.names)
    return names


def assignedNames(program) -> set[str]:
    # every name that something assigns to, reads input into or swaps, anywhere in the program
    names: set[str] = set()

    def visit(value) -> None:
        if isinstance(value, list) or isinstance(value, tuple):
            for item in value:
                visit(item)
            return
        if not isinstance(value, Node):
            return
        match value.type():
            case NodeType.AssignStatement:
                if value.target.type() == NodeType.IdentifierLiteral:
                    names.add(value.target.value)
            case NodeType.InputStatement:
                names.update(target.value for target in value.targets if target.type() == NodeType.IdentifierLiteral)
            case NodeType.CallExpression:
                if value.function.type() == NodeType.IdentifierLiteral and value.function.value == "swap":
                    names.update(argument.value for argument in value.arguments if argument.type() == NodeType.IdentifierLiteral)
        for child in vars(value).values():
            visit(child)

    visit(program.statements if isinstance(program, Program) else program)
    return names


# region builtin functions
def numericArguments(compiler: Compiler, node: CallExpression, count: int) -> list[TypedValue]:
    if len(node.arguments) != count:
        compiler.error(f"{node.function.value}() takes {count} argument{'s' if count != 1 else ''} but got {len(node.arguments)}", node)
        raise CompileError()

    values: list[TypedValue] = []
    for argument in node.arguments:
        resolved: TypedValue | None = compiler.visitExpression(argument)
        if resolved is None:
            raise CompileError()
        if not resolved.ctype.isNumeric:
            compiler.error(f"{node.function.value}() needs numbers, not {resolved.ctype}", argument)
            raise CompileError()
        values.append(resolved)
    return values


def builtinMinMax(compiler: Compiler, node: CallExpression) -> TypedValue | None:
    left, right = numericArguments(compiler, node, 2)
    operator: str = "<" if node.function.value == "min" else ">"
    commonType: CType = compiler.commonNumericType(left.ctype, right.ctype)
    leftValue: ir.Value = compiler.convert(left, commonType, node, "", explicit=True)
    rightValue: ir.Value = compiler.convert(right, commonType, node, "", explicit=True)
    isBetter: TypedValue = compiler.binaryOperation(operator, TypedValue(leftValue, commonType), TypedValue(rightValue, commonType), node)
    return TypedValue(compiler.builder.select(isBetter.value, leftValue, rightValue), commonType)


def builtinAbs(compiler: Compiler, node: CallExpression) -> TypedValue | None:
    (value,) = numericArguments(compiler, node, 1)
    if value.ctype.kind == "float":
        return TypedValue(compiler.builder.call(compiler.intrinsic("fabs"), [value.value]), DU)
    if value.ctype.kind == "char" or not value.ctype.signed:
        return value
    isNegative: ir.Value = compiler.builder.icmp_signed("<", value.value, ir.Constant(value.ctype.irType, 0))
    return TypedValue(compiler.builder.select(isNegative, compiler.builder.neg(value.value), value.value), value.ctype)


def builtinFloatFunction(compiler: Compiler, node: CallExpression) -> TypedValue | None:
    (value,) = numericArguments(compiler, node, 1)
    converted: ir.Value = compiler.convert(value, DU, node, "")
    return TypedValue(compiler.builder.call(compiler.intrinsic(node.function.value), [converted]), DU)


def builtinPrec(compiler: Compiler, node: CallExpression) -> TypedValue | None:
    value, digits = numericArguments(compiler, node, 2)
    number: ir.Value = compiler.expect(value, DU, node, "prec()")
    if not digits.ctype.isInteger:
        compiler.error("the number of digits for prec() must be an integer", node)
        raise CompileError()
    count: ir.Value = compiler.expect(digits, LL, node, "the digits of prec()")
    return TypedValue(compiler.callRuntime("cpl_str_prec", [number, count]), ST)


def builtinEof(compiler: Compiler, node: CallExpression) -> TypedValue | None:
    numericArguments(compiler, node, 0)
    ended: ir.Value = compiler.callRuntime("cpl_eof", [])
    return TypedValue(compiler.builder.icmp_unsigned("!=", ended, ir.Constant(I8, 0)), BO)


def builtinGetline(compiler: Compiler, node: CallExpression) -> TypedValue | None:
    numericArguments(compiler, node, 0)
    return TypedValue(compiler.callRuntime("cpl_read_line", []), ST)


def integerArgument(compiler: Compiler, node: CallExpression) -> TypedValue:
    (value,) = numericArguments(compiler, node, 1)
    if not value.ctype.isInteger:
        compiler.error(f"{node.function.value}() needs an integer, not {value.ctype}", node)
        raise CompileError()
    return value if value.ctype.kind == "int" else TypedValue(compiler.builder.zext(value.value, I32), IT)


def builtinBitCount(compiler: Compiler, node: CallExpression) -> TypedValue | None:
    # pc(x): set bits, ctz(x): trailing zeros, clz(x): leading zeros, like __builtin_popcount and friends
    value: TypedValue = integerArgument(compiler, node)
    irType: ir.IntType = value.ctype.irType
    name: str = {"pc": "ctpop", "ctz": "cttz", "clz": "ctlz"}[node.function.value]
    arguments: list[ir.Value] = [value.value] if name == "ctpop" else [value.value, ir.Constant(I1, 0)]
    # declared by hand: llvmlite's declare_intrinsic gives cttz and ctlz one parameter instead of two
    fullName: str = f"llvm.{name}.i{value.ctype.bits}"
    if fullName not in compiler.intrinsics:
        parameterTypes: list[ir.Type] = [irType] if name == "ctpop" else [irType, I1]
        compiler.intrinsics[fullName] = ir.Function(compiler.module, ir.FunctionType(irType, parameterTypes), name=fullName)
    intrinsic: ir.Function = compiler.intrinsics[fullName]
    result: ir.Value = compiler.builder.call(intrinsic, arguments)
    return TypedValue(result if value.ctype.bits == 32 else compiler.builder.trunc(result, I32), IT)


def builtinGcd(compiler: Compiler, node: CallExpression) -> TypedValue | None:
    # gcd(a, b) and lcm(a, b) on the common integer type, with Euclid's loop; gcd(0, 0) is 0
    left, right = numericArguments(compiler, node, 2)
    if not left.ctype.isInteger or not right.ctype.isInteger:
        compiler.error(f"{node.function.value}() needs integers", node)
        raise CompileError()
    ctype: CType = compiler.commonNumericType(left.ctype, right.ctype)
    builder: ir.IRBuilder = compiler.builder
    a: ir.Value = compiler.convert(left, ctype, node, "", explicit=True)
    b: ir.Value = compiler.convert(right, ctype, node, "", explicit=True)
    if ctype.signed:
        a = builder.select(builder.icmp_signed("<", a, ir.Constant(ctype.irType, 0)), builder.neg(a), a)
        b = builder.select(builder.icmp_signed("<", b, ir.Constant(ctype.irType, 0)), builder.neg(b), b)

    x: ir.Value = compiler.allocate(ctype.irType, "gcd_a")
    y: ir.Value = compiler.allocate(ctype.irType, "gcd_b")
    builder.store(a, x)
    builder.store(b, y)
    function: ir.Function = builder.function
    conditionBlock: ir.Block = function.append_basic_block("gcd_condition")
    bodyBlock: ir.Block = function.append_basic_block("gcd_body")
    endBlock: ir.Block = function.append_basic_block("gcd_end")
    builder.branch(conditionBlock)
    builder.position_at_end(conditionBlock)
    builder.cbranch(builder.icmp_unsigned("!=", builder.load(y), ir.Constant(ctype.irType, 0)), bodyBlock, endBlock)
    builder.position_at_end(bodyBlock)
    remainder: ir.Value = builder.urem(builder.load(x), builder.load(y))
    builder.store(builder.load(y), x)
    builder.store(remainder, y)
    builder.branch(conditionBlock)
    builder.position_at_end(endBlock)
    divisor: ir.Value = builder.load(x)

    if node.function.value == "gcd":
        return TypedValue(divisor, ctype)
    # lcm(a, b) = a / gcd * b, and 0 when either is 0
    isZero: ir.Value = builder.icmp_unsigned("==", divisor, ir.Constant(ctype.irType, 0))
    safeDivisor: ir.Value = builder.select(isZero, ir.Constant(ctype.irType, 1), divisor)
    return TypedValue(builder.mul(builder.udiv(a, safeDivisor), b), ctype)


def guardedBuiltin(function: callable) -> callable:
    def run(compiler: Compiler, node: CallExpression) -> TypedValue | None:
        try:
            return function(compiler, node)
        except CompileError:
            return None
    return run


def builtinSwap(compiler: Compiler, node: CallExpression) -> TypedValue | None:
    # swap(a, b) exchanges two variables, elements or fields of the same type
    if len(node.arguments) != 2:
        compiler.error(f"swap() takes 2 arguments but got {len(node.arguments)}", node)
        raise CompileError()
    a, b = node.arguments

    countBefore: int = compiler.mapSlotCount
    first = compiler.visitAddress(a)
    firstUsesMap: bool = compiler.mapSlotCount != countBefore
    countBetween: int = compiler.mapSlotCount
    second = compiler.visitAddress(b)
    secondUsesMap: bool = compiler.mapSlotCount != countBetween
    if first is None or second is None:
        raise CompileError()
    if first[1] != second[1]:
        compiler.error(f"swap() needs two things of the same type, not {first[1]} and {second[1]}", node)
        raise CompileError()

    # finding b in a map may have added a key and moved a's value, so look a up again (it exists now,
    # so this lookup can't move anything)
    if firstUsesMap and secondUsesMap:
        first = compiler.visitAddress(a)

    firstValue: ir.Value = compiler.load(first[0])
    secondValue: ir.Value = compiler.load(second[0])
    compiler.store(secondValue, first[0])
    compiler.store(firstValue, second[0])
    return TypedValue(None, VO)


BUILTINS: dict[str, callable] = {
    "swap": guardedBuiltin(builtinSwap),
    "pc": guardedBuiltin(builtinBitCount),
    "ctz": guardedBuiltin(builtinBitCount),
    "clz": guardedBuiltin(builtinBitCount),
    "gcd": guardedBuiltin(builtinGcd),
    "lcm": guardedBuiltin(builtinGcd),
    "min": guardedBuiltin(builtinMinMax),
    "max": guardedBuiltin(builtinMinMax),
    "abs": guardedBuiltin(builtinAbs),
    "sqrt": guardedBuiltin(builtinFloatFunction),
    "floor": guardedBuiltin(builtinFloatFunction),
    "ceil": guardedBuiltin(builtinFloatFunction),
    "log": guardedBuiltin(builtinFloatFunction),
    "exp": guardedBuiltin(builtinFloatFunction),
    "prec": guardedBuiltin(builtinPrec),
    "eof": guardedBuiltin(builtinEof),
    "gl": guardedBuiltin(builtinGetline),
    "getline": guardedBuiltin(builtinGetline),
}
# endregion


# region methods
# each method gets (compiler, object, call node, *arguments); the argument count comes from the signature
def vecPushBack(compiler: Compiler, target: TypedValue, node: Node, value: TypedValue) -> TypedValue:
    element: ir.Value = compiler.expect(value, target.ctype.elem, node, "pb()")
    vec: ir.Value = target.value

    # the common case is inlined: there's room, so store and bump the length; otherwise grow first
    length: ir.Value = compiler.vecLength(vec)
    capacity: ir.Value = compiler.load(compiler.vecField(vec, 1))
    isFull: ir.Value = compiler.builder.icmp_unsigned("==", length, capacity)
    with compiler.builder.if_then(isFull, likely=False):
        compiler.callRuntime("cpl_vec_grow", [vec])

    compiler.store(element, compiler.vecSlot(vec, target.ctype.elem, length))
    compiler.store(compiler.builder.add(length, ir.Constant(I64, 1)), compiler.vecField(vec, 0))
    return TypedValue(None, VO)


def vecPopBack(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    compiler.callRuntime("cpl_vec_pop", [target.value])
    return TypedValue(None, VO)


def vecSize(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    return TypedValue(compiler.vecLength(target.value), LL)


def vecEmpty(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    return TypedValue(compiler.builder.icmp_signed("==", compiler.vecLength(target.value), ir.Constant(I64, 0)), BO)


def vecBack(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    length: ir.Value = compiler.vecLength(target.value)
    isEmpty: ir.Value = compiler.builder.icmp_signed("==", length, ir.Constant(I64, 0))
    with compiler.builder.if_then(isEmpty, likely=False):
        compiler.callRuntime("cpl_panic_empty", [])
        compiler.builder.unreachable()
    last: ir.Value = compiler.builder.sub(length, ir.Constant(I64, 1))
    return TypedValue(compiler.load(compiler.vecSlot(target.value, target.ctype.elem, last)), target.ctype.elem)


def vecClear(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    compiler.callRuntime("cpl_vec_clear", [target.value])
    return TypedValue(None, VO)


def vecSort(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    elem: CType = target.ctype.elem
    if elem.sortKind is not None:
        compiler.callRuntime("cpl_vec_sort", [target.value, ir.Constant(I32, elem.sortKind)])
    elif elem.isOrderable:
        compiler.sortVec(target.value, elem, node)
    else:
        compiler.error(f"a {target.ctype} has no natural order; sort it with a function: v.srt(before)", node)
        raise CompileError()
    return TypedValue(None, VO)


def binarySearch(compiler: Compiler, target: TypedValue, node: Node, value: TypedValue, upper: bool) -> TypedValue:
    # lb: the first index whose element isn't less than x; ub: the first index whose element is greater
    elem: CType = target.ctype.elem
    if not elem.isOrderable:
        compiler.error(f"can't binary search a {target.ctype}; its elements have no order", node)
        raise CompileError()
    needle: TypedValue = TypedValue(compiler.expect(value, elem, node, "the value to search for"), elem)
    builder: ir.IRBuilder = compiler.builder

    low: ir.Value = compiler.allocate(I64, "low")
    high: ir.Value = compiler.allocate(I64, "high")
    builder.store(ir.Constant(I64, 0), low)
    builder.store(compiler.vecLength(target.value), high)

    function: ir.Function = builder.function
    conditionBlock: ir.Block = function.append_basic_block("search_condition")
    bodyBlock: ir.Block = function.append_basic_block("search_body")
    endBlock: ir.Block = function.append_basic_block("search_end")
    builder.branch(conditionBlock)

    builder.position_at_end(conditionBlock)
    builder.cbranch(builder.icmp_signed("<", builder.load(low), builder.load(high)), bodyBlock, endBlock)

    builder.position_at_end(bodyBlock)
    lowValue: ir.Value = builder.load(low)
    highValue: ir.Value = builder.load(high)
    middle: ir.Value = builder.add(lowValue, builder.lshr(builder.sub(highValue, lowValue), ir.Constant(I64, 1)))
    element: TypedValue = TypedValue(compiler.load(compiler.vecSlot(target.value, elem, middle)), elem)
    if upper:
        goRight: ir.Value = builder.not_(compiler.lessThan(needle, element, node))
    else:
        goRight = compiler.lessThan(element, needle, node)
    afterMiddle: ir.Value = builder.add(middle, ir.Constant(I64, 1))
    builder.store(builder.select(goRight, afterMiddle, lowValue), low)
    builder.store(builder.select(goRight, highValue, middle), high)
    builder.branch(conditionBlock)

    builder.position_at_end(endBlock)
    return TypedValue(builder.load(low), LL)


def vecLowerBound(compiler: Compiler, target: TypedValue, node: Node, value: TypedValue) -> TypedValue:
    return binarySearch(compiler, target, node, value, upper=False)


def vecUpperBound(compiler: Compiler, target: TypedValue, node: Node, value: TypedValue) -> TypedValue:
    return binarySearch(compiler, target, node, value, upper=True)


# region priority queues
# a pq is a vector kept in binary heap order; push and pop are generated per element type
def heapFirst(compiler: Compiler, ctype: CType, a: TypedValue, b: TypedValue, node: Node) -> ir.Value:
    # whether a belongs closer to the top than b
    return compiler.lessThan(a, b, node) if ctype.minFirst else compiler.lessThan(b, a, node)


def pqPushFunction(compiler: Compiler, ctype: CType, node: Node) -> ir.Function:
    elem: CType = ctype.elem

    def generate(function: ir.Function) -> None:
        vec, value = function.args
        builder: ir.IRBuilder = compiler.builder
        item: TypedValue = TypedValue(value, elem)

        # make room at the end, then move the hole up until the parent should stay above the new item
        length: ir.Value = compiler.vecLength(vec)
        capacity: ir.Value = compiler.load(compiler.vecField(vec, 1))
        with builder.if_then(builder.icmp_unsigned("==", length, capacity), likely=False):
            compiler.callRuntime("cpl_vec_grow", [vec])
        compiler.store(builder.add(length, ir.Constant(I64, 1)), compiler.vecField(vec, 0))

        hole: ir.Value = compiler.allocate(I64, "hole")
        builder.store(length, hole)
        conditionBlock: ir.Block = function.append_basic_block("up_condition")
        compareBlock: ir.Block = function.append_basic_block("up_compare")
        moveBlock: ir.Block = function.append_basic_block("up_move")
        doneBlock: ir.Block = function.append_basic_block("up_done")
        builder.branch(conditionBlock)

        builder.position_at_end(conditionBlock)
        builder.cbranch(builder.icmp_unsigned(">", builder.load(hole), ir.Constant(I64, 0)), compareBlock, doneBlock)

        builder.position_at_end(compareBlock)
        index: ir.Value = builder.load(hole)
        parent: ir.Value = builder.lshr(builder.sub(index, ir.Constant(I64, 1)), ir.Constant(I64, 1))
        parentValue: TypedValue = TypedValue(compiler.load(compiler.vecSlot(vec, elem, parent)), elem)
        builder.cbranch(heapFirst(compiler, ctype, item, parentValue, node), moveBlock, doneBlock)

        builder.position_at_end(moveBlock)
        compiler.store(parentValue.value, compiler.vecSlot(vec, elem, index))
        builder.store(parent, hole)
        builder.branch(conditionBlock)

        builder.position_at_end(doneBlock)
        compiler.store(value, compiler.vecSlot(vec, elem, builder.load(hole)))
        builder.ret_void()

    return compiler.helperFunction(f"cpl.{ctype}.push", ir.FunctionType(VOID, [compiler.vecPointer, elem.irType]), generate)


def pqPopFunction(compiler: Compiler, ctype: CType, node: Node) -> ir.Function:
    elem: CType = ctype.elem

    def generate(function: ir.Function) -> None:
        (vec,) = function.args
        builder: ir.IRBuilder = compiler.builder

        length: ir.Value = compiler.vecLength(vec)
        with builder.if_then(builder.icmp_unsigned("==", length, ir.Constant(I64, 0)), likely=False):
            compiler.callRuntime("cpl_panic_empty", [])
            builder.unreachable()

        # take the last item out, then move the hole at the top down until the last item fits there
        size: ir.Value = builder.sub(length, ir.Constant(I64, 1))
        compiler.store(size, compiler.vecField(vec, 0))
        last: TypedValue = TypedValue(compiler.load(compiler.vecSlot(vec, elem, size)), elem)

        hole: ir.Value = compiler.allocate(I64, "hole")
        builder.store(ir.Constant(I64, 0), hole)
        conditionBlock: ir.Block = function.append_basic_block("down_condition")
        pickBlock: ir.Block = function.append_basic_block("down_pick")
        moveBlock: ir.Block = function.append_basic_block("down_move")
        doneBlock: ir.Block = function.append_basic_block("down_done")
        builder.branch(conditionBlock)

        builder.position_at_end(conditionBlock)
        index: ir.Value = builder.load(hole)
        left: ir.Value = builder.add(builder.shl(index, ir.Constant(I64, 1)), ir.Constant(I64, 1))
        builder.cbranch(builder.icmp_unsigned("<", left, size), pickBlock, doneBlock)

        builder.position_at_end(pickBlock)
        right: ir.Value = builder.add(left, ir.Constant(I64, 1))
        leftValue: TypedValue = TypedValue(compiler.load(compiler.vecSlot(vec, elem, left)), elem)
        # the right child only counts when it exists; read it from the left slot otherwise
        hasRight: ir.Value = builder.icmp_unsigned("<", right, size)
        rightValue: TypedValue = TypedValue(compiler.load(compiler.vecSlot(vec, elem, builder.select(hasRight, right, left))), elem)
        takeRight: ir.Value = builder.and_(hasRight, heapFirst(compiler, ctype, rightValue, leftValue, node))
        child: ir.Value = builder.select(takeRight, right, left)
        childValue: ir.Value = builder.select(takeRight, rightValue.value, leftValue.value)
        builder.cbranch(heapFirst(compiler, ctype, TypedValue(childValue, elem), last, node), moveBlock, doneBlock)

        builder.position_at_end(moveBlock)
        compiler.store(childValue, compiler.vecSlot(vec, elem, index))
        builder.store(child, hole)
        builder.branch(conditionBlock)

        builder.position_at_end(doneBlock)
        with builder.if_then(builder.icmp_unsigned("<", builder.load(hole), size)):
            compiler.store(last.value, compiler.vecSlot(vec, elem, builder.load(hole)))
        builder.ret_void()

    return compiler.helperFunction(f"cpl.{ctype}.pop", ir.FunctionType(VOID, [compiler.vecPointer]), generate)


def pqPush(compiler: Compiler, target: TypedValue, node: Node, value: TypedValue) -> TypedValue:
    item: ir.Value = compiler.expect(value, target.ctype.elem, node, "ps()")
    compiler.builder.call(pqPushFunction(compiler, target.ctype, node), [target.value, item])
    return TypedValue(None, VO)


def pqPop(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    compiler.builder.call(pqPopFunction(compiler, target.ctype, node), [target.value])
    return TypedValue(None, VO)


def pqTop(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    isEmpty: ir.Value = compiler.builder.icmp_unsigned("==", compiler.vecLength(target.value), ir.Constant(I64, 0))
    with compiler.builder.if_then(isEmpty, likely=False):
        compiler.callRuntime("cpl_panic_empty", [])
        compiler.builder.unreachable()
    return TypedValue(compiler.load(compiler.vecSlot(target.value, target.ctype.elem, ir.Constant(I64, 0))), target.ctype.elem)
# endregion


def vecReverse(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    compiler.callRuntime("cpl_vec_reverse", [target.value])
    return TypedValue(None, VO)


def stringSize(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    return TypedValue(compiler.stringLength(target.value), LL)


def stringEmpty(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    length: ir.Value = compiler.stringLength(target.value)
    return TypedValue(compiler.builder.icmp_signed("==", length, ir.Constant(I64, 0)), BO)


def stringSub(compiler: Compiler, target: TypedValue, node: Node, start: TypedValue, count: TypedValue) -> TypedValue:
    startValue: ir.Value = compiler.expect(start, LL, node, "the start of sub()")
    countValue: ir.Value = compiler.expect(count, LL, node, "the length of sub()")
    return TypedValue(compiler.callRuntime("cpl_str_sub", [target.value, startValue, countValue]), ST)


def mapHas(compiler: Compiler, target: TypedValue, node: Node, key: TypedValue) -> TypedValue:
    keyValue: ir.Value = compiler.expect(key, target.ctype.key, node, "the map key")
    found: ir.Value = compiler.callRuntime("cpl_map_has", [target.value, compiler.mapKey(keyValue, target.ctype.key)])
    return TypedValue(compiler.builder.icmp_unsigned("!=", found, ir.Constant(I8, 0)), BO)


def mapDelete(compiler: Compiler, target: TypedValue, node: Node, key: TypedValue) -> TypedValue:
    keyValue: ir.Value = compiler.expect(key, target.ctype.key, node, "the map key")
    compiler.callRuntime("cpl_map_del", [target.value, compiler.mapKey(keyValue, target.ctype.key)])
    return TypedValue(None, VO)


def mapSize(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    return TypedValue(compiler.callRuntime("cpl_map_size", [target.value]), LL)


def mapEmpty(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    size: ir.Value = compiler.callRuntime("cpl_map_size", [target.value])
    return TypedValue(compiler.builder.icmp_signed("==", size, ir.Constant(I64, 0)), BO)


def mapKeys(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    keyType: CType = target.ctype.key
    if keyType.kind != "pair":
        keys: ir.Value = compiler.callRuntime("cpl_map_keys", [target.value, ir.Constant(I64, compiler.elementSize(keyType))])
        return TypedValue(keys, compiler.vecType(keyType))

    # pair keys come back packed into 64 bits; unpack them into a vector of pairs
    packed: ir.Value = compiler.callRuntime("cpl_map_keys", [target.value, ir.Constant(I64, 8)])
    count: ir.Value = compiler.vecLength(packed)
    keys = compiler.newVec(keyType, count)
    compiler.countedLoop(count, lambda index: compiler.store(
        compiler.unpackMapKey(compiler.load(compiler.vecSlot(packed, ULL, index)), keyType),
        compiler.vecSlot(keys, keyType, index)))
    return TypedValue(keys, compiler.vecType(keyType))


def mapClear(compiler: Compiler, target: TypedValue, node: Node) -> TypedValue:
    compiler.callRuntime("cpl_map_clear", [target.value])
    return TypedValue(None, VO)


PAIR_FIELDS: dict[str, int] = {"f": 0, "first": 0, "s": 1, "second": 1}

METHODS: dict[str, dict[str, callable]] = {
    "vec": {
        "pb": vecPushBack, "pp": vecPopBack, "sz": vecSize, "emp": vecEmpty, "bk": vecBack,
        "clr": vecClear, "srt": vecSort, "rev": vecReverse, "lb": vecLowerBound, "ub": vecUpperBound,
    },
    "pq": {"ps": pqPush, "pp": pqPop, "tp": pqTop, "sz": vecSize, "emp": vecEmpty, "clr": vecClear},
    "string": {"sz": stringSize, "emp": stringEmpty, "sub": stringSub},
    "map": {"has": mapHas, "del": mapDelete, "sz": mapSize, "emp": mapEmpty, "keys": mapKeys, "clr": mapClear},
}
# endregion
