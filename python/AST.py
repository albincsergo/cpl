from abc import ABC
from enum import Enum
from typing import Any


class NodeType(Enum):
    Program = "Program"

    # statements
    ExpressionStatement = "ExpressionStatement"
    ShallStatement = "ShallStatement"
    FunctionStatement = "FunctionStatement"
    StructStatement = "StructStatement"
    ReturnStatement = "ReturnStatement"
    BlockStatement = "BlockStatement"
    AssignStatement = "AssignStatement"
    IfStatement = "IfStatement"
    WhileStatement = "WhileStatement"
    ForStatement = "ForStatement"
    ForEachStatement = "ForEachStatement"
    BreakStatement = "BreakStatement"
    ContinueStatement = "ContinueStatement"
    InputStatement = "InputStatement"
    OutputStatement = "OutputStatement"

    # expressions
    InfixExpression = "InfixExpression"
    PrefixExpression = "PrefixExpression"
    CallExpression = "CallExpression"
    IndexExpression = "IndexExpression"
    MemberExpression = "MemberExpression"
    CastExpression = "CastExpression"

    # literals
    IntegerLiteral = "IntegerLiteral"
    DoubleLiteral = "DoubleLiteral"
    BooleanLiteral = "BooleanLiteral"
    StringLiteral = "StringLiteral"
    CharLiteral = "CharLiteral"
    NilLiteral = "NilLiteral"
    IdentifierLiteral = "IdentifierLiteral"


def toJson(value: Any) -> Any:
    if isinstance(value, Node) or isinstance(value, TypeExpression):
        return value.json()
    if isinstance(value, list) or isinstance(value, tuple):
        return [toJson(item) for item in value]
    return value


class TypeExpression:
    # a written type like 'it', 'vec<ll>' or 'arr<it, 100>'
    def __init__(self, name: str, arguments: list = None, line: int = 0) -> None:
        self.name = name
        self.arguments = arguments if arguments is not None else []
        self.line = line

    def __str__(self) -> str:
        if len(self.arguments) == 0:
            return self.name
        return f"{self.name}<{', '.join(str(argument) for argument in self.arguments)}>"

    def json(self) -> str:
        return str(self)


class Node(ABC):
    line: int = 0

    def type(self) -> NodeType:
        return NodeType(self.__class__.__name__)

    def json(self) -> dict:
        output: dict = {"type": self.type().value}
        for key, value in vars(self).items():
            output[key] = toJson(value)
        return output


class Statement(Node):
    pass


class Expression(Node):
    pass


class Program(Node):
    def __init__(self) -> None:
        self.statements: list[Statement] = []


# region statements
class ExpressionStatement(Statement):
    def __init__(self, expression: Expression = None) -> None:
        self.expression = expression


class ShallStatement(Statement):
    # _ name: type = value.
    def __init__(self, names: list[str] = None, valueType: TypeExpression = None, value: Expression = None) -> None:
        self.names = names if names is not None else []
        self.valueType = valueType
        self.value = value


class BlockStatement(Statement):
    def __init__(self, statements: list[Statement] = None) -> None:
        self.statements = statements if statements is not None else []


class ReturnStatement(Statement):
    def __init__(self, returnValue: Expression = None) -> None:
        self.returnValue = returnValue


class FunctionStatement(Statement):
    def __init__(self, name: str = None, parameters: list = None, returnType: TypeExpression = None, body: BlockStatement = None) -> None:
        self.name = name
        # list of (name, TypeExpression)
        self.parameters = parameters if parameters is not None else []
        self.returnType = returnType
        self.body = body


class StructStatement(Statement):
    def __init__(self, name: str = None, fields: list = None) -> None:
        self.name = name
        # list of (name, TypeExpression)
        self.fields = fields if fields is not None else []


class AssignStatement(Statement):
    # target op= value, where op is '=' for plain assignment
    def __init__(self, target: Expression = None, operator: str = "=", rightValue: Expression = None) -> None:
        self.target = target
        self.operator = operator
        self.rightValue = rightValue


class IfStatement(Statement):
    def __init__(self, condition: Expression = None, consequence: BlockStatement = None, alternative: Statement = None) -> None:
        self.condition = condition
        self.consequence = consequence
        # a BlockStatement, another IfStatement for 'else if', or None
        self.alternative = alternative


class WhileStatement(Statement):
    def __init__(self, condition: Expression = None, body: BlockStatement = None) -> None:
        self.condition = condition
        self.body = body


class ForStatement(Statement):
    def __init__(self, initializer: Statement = None, condition: Expression = None, step: Statement = None, body: BlockStatement = None) -> None:
        self.initializer = initializer
        self.condition = condition
        self.step = step
        self.body = body


class ForEachStatement(Statement):
    # for (x in v) { ... }   for (i, x in v) { ... }   for (i in rng(n)) { ... }
    def __init__(self, names: list[str] = None, iterable: Expression = None, body: BlockStatement = None) -> None:
        self.names = names if names is not None else []
        self.iterable = iterable
        self.body = body


class BreakStatement(Statement):
    pass


class ContinueStatement(Statement):
    pass


class InputStatement(Statement):
    # in @ a @ b.
    def __init__(self, targets: list[Expression] = None) -> None:
        self.targets = targets if targets is not None else []


class OutputStatement(Statement):
    # ou @@ a @@ b.
    def __init__(self, values: list[Expression] = None) -> None:
        self.values = values if values is not None else []
# endregion


# region expressions
class InfixExpression(Expression):
    def __init__(self, leftNode: Expression, operator: str, rightNode: Expression = None) -> None:
        self.leftNode = leftNode
        self.operator = operator
        self.rightNode = rightNode


class PrefixExpression(Expression):
    def __init__(self, operator: str, rightNode: Expression = None) -> None:
        self.operator = operator
        self.rightNode = rightNode


class CallExpression(Expression):
    # function(arguments) or object.method(arguments)
    def __init__(self, function: Expression, arguments: list[Expression] = None) -> None:
        self.function = function
        self.arguments = arguments if arguments is not None else []


class IndexExpression(Expression):
    def __init__(self, leftNode: Expression, index: Expression = None) -> None:
        self.leftNode = leftNode
        self.index = index


class MemberExpression(Expression):
    def __init__(self, leftNode: Expression, name: str) -> None:
        self.leftNode = leftNode
        self.name = name


class CastExpression(Expression):
    # it(x), st(42), vec<it>(n)
    def __init__(self, targetType: TypeExpression, arguments: list[Expression] = None) -> None:
        self.targetType = targetType
        self.arguments = arguments if arguments is not None else []
# endregion


# region literals
class IntegerLiteral(Expression):
    def __init__(self, value: int) -> None:
        self.value = value


class DoubleLiteral(Expression):
    def __init__(self, value: float) -> None:
        self.value = value


class BooleanLiteral(Expression):
    def __init__(self, value: bool) -> None:
        self.value = value


class StringLiteral(Expression):
    def __init__(self, value: str) -> None:
        self.value = value


class CharLiteral(Expression):
    def __init__(self, value: str) -> None:
        self.value = value


class NilLiteral(Expression):
    pass


class IdentifierLiteral(Expression):
    def __init__(self, value: str) -> None:
        self.value = value
# endregion
