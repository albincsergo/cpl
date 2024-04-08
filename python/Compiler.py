from llvmlite import ir

from AST import Node, NodeType, Program, Expression, ExpressionStatement, InfixExpression, IntegerLiteral, DoubleLiteral, ShallStatement, IdentifierLiteral, BlockStatement, FunctionStatement, ReturnStatement

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

            # expressions
            case NodeType.InfixExpression:
                self.visitInfixExpression(node)

    # region visit methods
    def visitProgram(self, node: Program) -> None:
        for statement in node.statements:
            self.compile(statement)

    def visitExpressionStatement(self, node: ExpressionStatement) -> None:
        self.compile(node.expression)


    def visitInfixExpression(self, node: InfixExpression) -> None:
        operator: str = node.operator
        leftValue, leftType = self.resolveValue(node.leftNode)
        rightValue, rightType = self.resolveValue(node.rightNode)

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

        return value, Type
    
    def visitShallStatement(self, node: ShallStatement) -> None:
        name: str = node.name.value
        value: Expression = node.value
        valueType: str = node.valueType

        value, Type = self.resolveValue(node=value)

        if self.environment.lookup(name) is None:
            pointer = self.builder.alloca(Type)

            self.builder.store(value, pointer)

            self.environment.define(name, pointer, Type)
        else: 
            pointer, _ = self.environment.lookup(name)
            self.builder.store(value, pointer)

    def visitBlockStatement(self, node: BlockStatement) -> None:
        for statement in node.statements:
            self.compile(statement)

    def visitReturnStatement(self, node: ReturnStatement) -> None:
        value: Expression = node.returnValue
        value, Type = self.resolveValue(value)

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

        self.compile(body)

        self.environment = previousEnvironment
        self.environment.define(name, func, returnType)

        self.builder = previousBuilder
    # endregion
        
    # region helpers
    def resolveValue(self, node: Expression) -> tuple[ir.Value, ir.Type]:
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
                pointer, Type = self.environment.lookup(node.value)
                return self.builder.load(pointer), Type

            # expression values
            case NodeType.InfixExpression:
                return self.visitInfixExpression(node)
    # endregion