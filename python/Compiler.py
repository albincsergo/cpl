from llvmlite import ir

from AST import Node, NodeType, Program, Expression, ExpressionStatement, InfixExpression, IntegerLiteral, DoubleLiteral
from AST import ShallStatement, IdentifierLiteral, BlockStatement, FunctionStatement, ReturnStatement, AssignStatement

from Environment import Environment

class Compiler:
    def __init__(self) -> None:
        self.typeMap: dict[str, ir.Type] = {
            "int": ir.IntType(32),
            "double": ir.DoubleType()
        }

        self.module: ir.Module = ir.Module("main")

        self.builder: ir.IRBuilder = ir.IRBuilder()

        self.environment: Environment = Environment()

        # temporary error implementation
        self.errors: list[str] = []

    def compile(self, node: Node) -> None:
        match node.type():
            case NodeType.Program:
                self.visitProgram(node)

            # statements
            case NodeType.ExpressionStatement:
                self.visitExpressionStatement(node)
            case NodeType.ShallStatement:
                self.visitShallStatement(node)
            case NodeType.FunctionStatement:
                self.visitFunctionStatement(node)
            case NodeType.BlockStatement:
                self.visitBlockStatement(node)
            case NodeType.ReturnStatement:
                self.visitReturnStatement(node)
            case NodeType.AssignStatement:
                self.visitAssignStatement(node)

            # expressions
            case NodeType.InfixExpression:
                self.visitInfixExpression(node)

    # region visit methods
    def visitProgram(self, node: Program) -> None:
        for statement in node.statements:
            self.compile(statement)

    def visitExpressionStatement(self, node: ExpressionStatement) -> None:
        if self.insideFunction("Expression"):
            self.compile(node.expression)


    def visitInfixExpression(self, node: InfixExpression) -> tuple[ir.Value, ir.Type] | None:
        operator: str = node.operator
        left = self.resolveValue(node.leftNode)
        right = self.resolveValue(node.rightNode)
        if left is None or right is None:
            return None

        leftValue, leftType = left
        rightValue, rightType = right

        # mixing ints and doubles promotes the int side to double
        if isinstance(leftType, ir.IntType) and isinstance(rightType, ir.DoubleType):
            leftValue, leftType = self.builder.sitofp(leftValue, rightType), rightType
        elif isinstance(leftType, ir.DoubleType) and isinstance(rightType, ir.IntType):
            rightValue, rightType = self.builder.sitofp(rightValue, leftType), leftType

        if operator == "^":
            return self.power(leftValue, rightValue, leftType)

        value = None
        Type = None

        if (isinstance(leftType, ir.IntType) and isinstance(rightType, ir.IntType)):
            Type = self.typeMap["int"]
            match operator:
                case "+":
                    value = self.builder.add(leftValue, rightValue)
                case "-":
                    value = self.builder.sub(leftValue, rightValue)
                case "*":
                    value = self.builder.mul(leftValue, rightValue)
                case "/":
                    value = self.builder.sdiv(leftValue, rightValue)
                case "%":
                    value = self.builder.srem(leftValue, rightValue)

        elif (isinstance(leftType, ir.DoubleType) and isinstance(rightType, ir.DoubleType)):
            Type = self.typeMap["double"]
            match operator:
                case "+":
                    value = self.builder.fadd(leftValue, rightValue)
                case "-":
                    value = self.builder.fsub(leftValue, rightValue)
                case "*":
                    value = self.builder.fmul(leftValue, rightValue)
                case "/":
                    value = self.builder.fdiv(leftValue, rightValue)
                case "%":
                    value = self.builder.frem(leftValue, rightValue)

        if value is None:
            self.errors.append(f"~~~ COMPILE ERROR: Operator {operator} isn't supported for types {leftType} and {rightType}.")
            return None

        return value, Type

    def visitShallStatement(self, node: ShallStatement) -> None:
        name: str = node.name.value
        declaredType: ir.Type = self.typeMap[node.valueType]

        if not self.insideFunction(f"Declaration of {name}"):
            return

        if name in self.environment.records:
            self.errors.append(f"~~~ COMPILE ERROR: Identifier {name} was already declared in this scope.")
            return

        resolved = self.resolveValue(node=node.value)
        if resolved is None:
            return

        value = self.convert(*resolved, declaredType, context=f"declaration of {name}")
        if value is None:
            return

        pointer = self.builder.alloca(declaredType)
        self.builder.store(value, pointer)
        self.environment.define(name, pointer, declaredType)

    def visitBlockStatement(self, node: BlockStatement) -> None:
        for statement in node.statements:
            if self.builder.block is not None and self.builder.block.is_terminated:
                self.errors.append("~~~ COMPILE ERROR: Unreachable code after return statement.")
                return
            self.compile(statement)

    def visitReturnStatement(self, node: ReturnStatement) -> None:
        if not self.insideFunction("Return statement"):
            return

        resolved = self.resolveValue(node.returnValue)
        if resolved is None:
            return

        returnType: ir.Type = self.builder.function.function_type.return_type
        value = self.convert(*resolved, returnType, context="return statement")
        if value is None:
            return

        self.builder.ret(value)

    def visitFunctionStatement(self, node: FunctionStatement) -> None:
        name: str = node.name.value
        body: BlockStatement = node.body
        params: list[IdentifierLiteral] = node.parameters

        paramNames: list[str] = [par.value for par in params]
        paramTypes: list[ir.Type] = []
        returnType: ir.Type = self.typeMap[node.returnType]

        funcType: ir.FunctionType = ir.FunctionType(returnType, paramTypes)
        func: ir.Function = ir.Function(self.module, funcType, name=name)

        block: ir.Block = func.append_basic_block(f'{name}_entry')

        previousBuilder = self.builder

        self.builder = ir.IRBuilder(block)

        previousEnvironment = self.environment

        self.environment = Environment(parent=self.environment)
        self.environment.define(name, func, returnType)

        errorCount: int = len(self.errors)
        self.compile(body)

        # only report a missing return if the body itself compiled cleanly
        if not self.builder.block.is_terminated and len(self.errors) == errorCount:
            self.errors.append(f"~~~ COMPILE ERROR: Function {name} doesn't return a value.")

        self.environment = previousEnvironment
        self.environment.define(name, func, returnType)

        self.builder = previousBuilder

    def visitAssignStatement(self, node: AssignStatement) -> None:
        name: str = node.ident.value

        if not self.insideFunction(f"Assignment to {name}"):
            return

        record = self.environment.lookup(name)
        if record is None:
            self.errors.append(f"~~~ COMPILE ERROR: Identifier {name} wasn't declared previously.")
            return

        pointer, Type = record
        if isinstance(pointer, ir.Function):
            self.errors.append(f"~~~ COMPILE ERROR: Can't assign to function {name}.")
            return

        resolved = self.resolveValue(node.rightValue)
        if resolved is None:
            return

        value = self.convert(*resolved, Type, context=f"assignment to {name}")
        if value is None:
            return

        self.builder.store(value, pointer)
    # endregion

    # region helpers
    def resolveValue(self, node: Expression) -> tuple[ir.Value, ir.Type] | None:
        match node.type():
            case NodeType.IntegerLiteral:
                node: IntegerLiteral = node
                value, Type = node.value, self.typeMap["int"]
                return ir.Constant(Type, value), Type
            case NodeType.DoubleLiteral:
                node: DoubleLiteral = node
                value, Type = node.value, self.typeMap["double"]
                return ir.Constant(Type, value), Type
            case NodeType.IdentifierLiteral:
                node: IdentifierLiteral = node
                record = self.environment.lookup(node.value)
                if record is None:
                    self.errors.append(f"~~~ COMPILE ERROR: Identifier {node.value} wasn't declared previously.")
                    return None

                pointer, Type = record
                if isinstance(pointer, ir.Function):
                    self.errors.append(f"~~~ COMPILE ERROR: Function {node.value} can't be used as a value.")
                    return None

                return self.builder.load(pointer), Type

            # expression values
            case NodeType.InfixExpression:
                return self.visitInfixExpression(node)

        self.errors.append(f"~~~ COMPILE ERROR: Can't compile expression of type {node.type().value}.")
        return None

    def convert(self, value: ir.Value, fromType: ir.Type, toType: ir.Type, context: str) -> ir.Value | None:
        if fromType == toType:
            return value

        if isinstance(fromType, ir.IntType) and isinstance(toType, ir.DoubleType):
            return self.builder.sitofp(value, toType)

        self.errors.append(f"~~~ COMPILE ERROR: Can't convert {fromType} to {toType} in {context}.")
        return None

    def power(self, base: ir.Value, exponent: ir.Value, Type: ir.Type) -> tuple[ir.Value, ir.Type]:
        doubleType: ir.Type = self.typeMap["double"]
        powFunction = self.module.declare_intrinsic("llvm.pow", [doubleType])

        if isinstance(Type, ir.IntType):
            base = self.builder.sitofp(base, doubleType)
            exponent = self.builder.sitofp(exponent, doubleType)
            result = self.builder.call(powFunction, [base, exponent])
            return self.builder.fptosi(result, Type), Type

        return self.builder.call(powFunction, [base, exponent]), Type

    def insideFunction(self, what: str) -> bool:
        if self.builder.block is None:
            self.errors.append(f"~~~ COMPILE ERROR: {what} must be inside a function.")
            return False
        return True
    # endregion
