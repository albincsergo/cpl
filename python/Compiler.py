from llvmlite import ir

from AST import (
    AssignStatement,
    BlockStatement,
    BooleanLiteral,
    DoubleLiteral,
    Expression,
    ExpressionStatement,
    FunctionStatement,
    IdentifierLiteral,
    IfStatement,
    InfixExpression,
    IntegerLiteral,
    Node,
    NodeType,
    Program,
    ReturnStatement,
    ShallStatement,
)
from Environment import Environment


class Compiler:
    def __init__(self) -> None:
        self.typeMap: dict[str, ir.Type] = {
            "int": ir.IntType(32),
            "double": ir.DoubleType(),
        }
        self.boolType: ir.IntType = ir.IntType(1)

        self.module: ir.Module = ir.Module("main")
        self.builder: ir.IRBuilder = ir.IRBuilder()
        self.environment: Environment = Environment()

        # Temporary error collection used by main.py.
        self.errors: list[str] = []

    def compile(self, node: Node) -> None:
        if node is None:
            return

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
            case NodeType.IfStatement:
                self.visitIfStatement(node)

            # expressions
            case NodeType.InfixExpression:
                self.visitInfixExpression(node)

    # region visit methods
    def visitProgram(self, node: Program) -> None:
        for statement in node.statements:
            self.compile(statement)

    def visitExpressionStatement(self, node: ExpressionStatement) -> None:
        self.compile(node.expression)

    def visitInfixExpression(self, node: InfixExpression) -> tuple[ir.Value | None, ir.Type | None]:
        operator: str = node.operator
        leftValue, leftType = self.resolveValue(node.leftNode)
        rightValue, rightType = self.resolveValue(node.rightNode)

        if leftValue is None or rightValue is None or leftType is None or rightType is None:
            return None, None

        if leftType != rightType:
            self.errors.append(
                f"~~~ COMPILE ERROR: Type mismatch in infix expression ({leftType} {operator} {rightType})."
            )
            return None, None

        value: ir.Value | None = None
        Type: ir.Type | None = None
        isComparison = operator in ["==", "!=", "<", ">", "<=", ">="]

        if isinstance(leftType, ir.IntType) and isinstance(rightType, ir.IntType):
            if isComparison:
                Type = self.boolType
                value = self.builder.icmp_signed(operator, leftValue, rightValue)
            else:
                Type = leftType
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

        elif isinstance(leftType, ir.DoubleType) and isinstance(rightType, ir.DoubleType):
            if isComparison:
                Type = self.boolType
                value = self.builder.fcmp_ordered(operator, leftValue, rightValue)
            else:
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

        if value is None or Type is None:
            self.errors.append(f"~~~ COMPILE ERROR: Unsupported infix operator '{operator}' for type {leftType}.")

        return value, Type

    def visitShallStatement(self, node: ShallStatement) -> None:
        name: str = node.name.value
        valueNode: Expression = node.value

        value, valueType = self.resolveValue(node=valueNode)
        if value is None or valueType is None:
            return

        declaredType = self.typeMap.get(node.valueType)
        if declaredType is None:
            self.errors.append(f"~~~ COMPILE ERROR: Unknown declared type '{node.valueType}' for '{name}'.")
            return

        if declaredType != valueType:
            self.errors.append(
                f"~~~ COMPILE ERROR: Cannot initialize '{name}' of type {declaredType} with value of type {valueType}."
            )
            return

        existing = self.environment.lookup(name)
        if existing is None:
            pointer = self.builder.alloca(declaredType)
            self.builder.store(value, pointer)
            self.environment.define(name, pointer, declaredType)
            return

        pointer, _ = existing
        self.builder.store(value, pointer)

    def visitBlockStatement(self, node: BlockStatement) -> None:
        for statement in node.statements:
            self.compile(statement)
            if self._currentBlockTerminated():
                break

    def visitReturnStatement(self, node: ReturnStatement) -> None:
        valueNode: Expression = node.returnValue
        value, Type = self.resolveValue(valueNode)
        if value is None or Type is None:
            return

        self.builder.ret(value)

    def visitFunctionStatement(self, node: FunctionStatement) -> None:
        name: str = node.name.value
        body: BlockStatement = node.body
        params: list[IdentifierLiteral] = node.parameters

        paramTypes: list[ir.Type] = []
        if len(params) > 0:
            self.errors.append("~~~ COMPILE ERROR: Function parameters are not supported yet.")
            return

        returnType: ir.Type = self.typeMap[node.returnType]

        funcType: ir.FunctionType = ir.FunctionType(returnType, paramTypes)
        func: ir.Function = ir.Function(self.module, funcType, name=name)

        block: ir.Block = func.append_basic_block(f"{name}_entry")

        previousBuilder = self.builder
        previousEnvironment = self.environment

        self.builder = ir.IRBuilder(block)
        self.environment = Environment(parent=previousEnvironment)
        self.environment.define(name, func, returnType)

        self.compile(body)

        self.environment = previousEnvironment
        self.environment.define(name, func, returnType)
        self.builder = previousBuilder

    def visitAssignStatement(self, node: AssignStatement) -> None:
        name: str = node.ident.value
        valueNode: Expression = node.rightValue

        value, valueType = self.resolveValue(valueNode)
        if value is None or valueType is None:
            return

        resolved = self.environment.lookup(name)
        if resolved is None:
            self.errors.append(f"~~~ COMPILE ERROR: Identifier {name} wasn't declared previously.")
            return

        pointer, declaredType = resolved
        if declaredType != valueType:
            self.errors.append(
                f"~~~ COMPILE ERROR: Cannot assign value of type {valueType} to '{name}' of type {declaredType}."
            )
            return

        self.builder.store(value, pointer)

    def visitIfStatement(self, node: IfStatement) -> None:
        if self._currentBlockTerminated():
            return

        conditionValue, conditionType = self.resolveValue(node.condition)
        if conditionValue is None or conditionType is None:
            return

        condition = self.resolveCondition(conditionValue, conditionType)
        if condition is None:
            return

        function = self.builder.function
        thenBlock = function.append_basic_block("if_then")
        mergeBlock = function.append_basic_block("if_end")
        elseBlock = function.append_basic_block("if_else") if node.alternative is not None else mergeBlock

        self.builder.cbranch(condition, thenBlock, elseBlock)

        self.builder.position_at_end(thenBlock)
        self.visitBlockStatement(node.consequence)
        if not self._currentBlockTerminated():
            self.builder.branch(mergeBlock)

        if node.alternative is not None:
            self.builder.position_at_end(elseBlock)
            self.visitBlockStatement(node.alternative)
            if not self._currentBlockTerminated():
                self.builder.branch(mergeBlock)

        self.builder.position_at_end(mergeBlock)

    # endregion

    # region helpers
    def _currentBlockTerminated(self) -> bool:
        block = getattr(self.builder, "block", None)
        return block is not None and block.terminator is not None

    def resolveCondition(self, value: ir.Value, Type: ir.Type) -> ir.Value | None:
        if isinstance(Type, ir.IntType):
            if Type.width == 1:
                return value
            return self.builder.icmp_signed("!=", value, ir.Constant(Type, 0))

        if isinstance(Type, ir.DoubleType):
            return self.builder.fcmp_ordered("!=", value, ir.Constant(Type, 0.0))

        self.errors.append(f"~~~ COMPILE ERROR: Unsupported condition type {Type}.")
        return None

    def resolveValue(self, node: Expression) -> tuple[ir.Value | None, ir.Type | None]:
        if node is None:
            self.errors.append("~~~ COMPILE ERROR: Missing expression.")
            return None, None

        match node.type():
            case NodeType.IntegerLiteral:
                node = node  # type: IntegerLiteral
                value, Type = node.value, self.typeMap["int"]
                return ir.Constant(Type, value), Type
            case NodeType.DoubleLiteral:
                node = node  # type: DoubleLiteral
                value, Type = node.value, self.typeMap["double"]
                return ir.Constant(Type, value), Type
            case NodeType.BooleanLiteral:
                node = node  # type: BooleanLiteral
                return ir.Constant(self.boolType, int(node.value)), self.boolType
            case NodeType.IdentifierLiteral:
                node = node  # type: IdentifierLiteral
                resolved = self.environment.lookup(node.value)
                if resolved is None:
                    self.errors.append(f"~~~ COMPILE ERROR: Identifier {node.value} wasn't declared previously.")
                    return None, None

                pointer, Type = resolved
                return self.builder.load(pointer), Type
            case NodeType.InfixExpression:
                return self.visitInfixExpression(node)

        self.errors.append(f"~~~ COMPILE ERROR: Unsupported expression node {node.type()}.")
        return None, None

    # endregion
