from llvmlite import ir

from AST import Node, NodeType, Program, Expression, Statement, ExpressionStatement, InfixExpression, IntegerLiteral, DoubleLiteral

class Compiler:
    def __init__(self) -> None:
        self.typeMap: dict[str, ir.Type] = {
            "int": ir.IntType(32),
            "double": ir.DoubleType()
        }
    
        self.module: ir.Module = ir.Module("main")

        self.builder: ir.IRBuilder = ir.IRBuilder()
    
    def compile(self, node: Node) -> None:
        match node.type():
            case NodeType.Program:
                self.visitProgram(node)

            # statements
            case NodeType.ExpressionStatement:
                self.visitExpressionStatement(node)
            
            # expressions
            case NodeType.InfixExpression:
                self.visitInfixExpression(node)

    # region visit methods
    def visitProgram(self, node: Program) -> None:
        functionName: str = "mn"
        paramTypes: list[ir.Type] = []
        returnType: ir.Type = ir.VoidType()

        functionType = ir.FunctionType(returnType, paramTypes)
        function = ir.Function(self.module, functionType, name=functionName)

        block = function.append_basic_block(f"{functionName}_entry")
        
        self.builder = ir.IRBuilder(block)

        for statement in node.statements:
            self.compile(statement)

        returnValue: ir.Constant = ir.Constant(self.typeMap["int"], 69)
        self.builder.ret(returnValue)

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
    # endregion
        
    # region helpers
    def resolveValue(self, node: Expression, valueType: str = None) -> tuple[ir.Value, ir.Type]:
        match node.type():
            case NodeType.IntegerLiteral:
                node: IntegerLiteral = node
                value, Type = node.value, self.typeMap["int"]
                return ir.Constant(Type, value), Type
            case NodeType.DoubleLiteral:
                node: DoubleLiteral = node
                value, Type = node.value, self.typeMap["double"]
                return ir.Constant(Type, value), Type
            
            case NodeType.InfixExpression:
                return self.visitInfixExpression(node)
    # endregion