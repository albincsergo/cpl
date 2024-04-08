from abc import ABC, abstractmethod
from enum import Enum

class NodeType(Enum):
    Program = "Program"

    # statements
    ExpressionStatement = "ExpressionStatement"
    ShallStatement = "ShallStatement"
    FunctionStatement = "FunctionStatement"
    ReturnStatement = "ReturnStatement"
    BlockStatement = "BlockStatement"
    AssignStatement = "AssignStatement"


    # expressions
    InfixExpression = "InfixExpression"

    # literals
    IntegerLiteral = "IntegerLiteral"
    DoubleLiteral = "DoubleLiteral"
    IdentifierLiteral = "IdentifierLiteral"

class Node(ABC):
    @abstractmethod
    def type(self) -> NodeType:
        pass

    @abstractmethod
    def json(self) -> dict:
        pass

class Statement(Node):
    pass

class Expression(Node):
    pass

class Program(Node):
    def __init__(self) -> None:
        self.statements: list[Statement] = []

    def type(self) -> NodeType:
        return NodeType.Program

    def json(self) -> dict:
        return {
            "type": self.type().value,
            "statements": [{statement.type().value: statement.json()} for statement in self.statements]
        }
    
# region statements
class ExpressionStatement(Statement):
    def __init__(self, expression: Expression = None) -> None:
        self.expression: Expression = expression

    def type(self) -> NodeType:
        return NodeType.ExpressionStatement

    def json(self) -> dict:
        return {
            "type": self.type().value,
            "expression": self.expression.json()
        }

class ShallStatement(Statement):
    def __init__(self, name: Expression = None, value: Expression = None, valueType: str = None) -> None:
        self.name = name
        self.value = value
        self.valueType = valueType

    def type(self) -> NodeType:
        return NodeType.ShallStatement
    
    def json(self) -> dict:
        return {
            "type": self.type().value,
            "name": self.name.json(),
            "value": self.value.json(),
            "valueType": self.valueType
        }

class BlockStatement(Statement):
    def __init__(self, statements: list[Statement] = None) -> None:
        self.statements = statements if statements is not None else []
    
    def type(self) -> NodeType:
        return NodeType.BlockStatement
    
    def json(self) -> dict:
        return {
            "type": self.type().value,
            "statements": [statement.json() for statement in self.statements]
        }
    
class ReturnStatement(Statement):
    def __init__(self, returnValue: Expression = None) -> None:
        self.returnValue = returnValue

    def type(self) -> NodeType:
        return NodeType.ReturnStatement
    
    def json(self) -> dict:
        return {
            "type": self.type().value,
            "returnValue": self.returnValue.json()
        }
    
class FunctionStatement(Statement):
    def __init__(self, parameters: list = [], body: BlockStatement = None, name = None, returnType: str = None) -> None:
        self.parameters = parameters
        self.body = body
        self.name = name
        self.returnType = returnType

    def type(self) -> NodeType:
        return NodeType.FunctionStatement
    
    def json(self) -> dict:
        return {
            "type": self.type().value,
            "name": self.name.json(),
            "returnType": self.returnType,
            "parameters": [par.json() for par in self.parameters],
            "body": self.body.json()
        }
    
class AssignStatement(Statement):
    def __init__(self, ident: Expression = None, rightValue: Expression = None) -> None:
        self.ident = ident
        self.rightValue = rightValue

    def type(self) -> NodeType:
        return NodeType.AssignStatement
    
    def json(self) -> dict:
        return {
            "type": self.type().value,
            "ident": self.ident.json(),
            "rigthValue": self.rightValue.json
        }
# endregion

# region expressions
class InfixExpression(Expression):
    def __init__(self, leftNode: Expression, operator: str, rightNode: Expression = None) -> None:
        self.leftNode: Expression = leftNode
        self.operator: str = operator
        self.rightNode: Expression = rightNode

    def type(self) -> NodeType:
        return NodeType.InfixExpression
    
    def json(self) -> dict:
        return {
            "type": self.type().value,
            "leftNode": self.leftNode.json(),
            "operator": self.operator,
            "rightNode": self.rightNode.json()
        }   
# endregion

# region literals
class IntegerLiteral(Expression):
    def __init__(self, value: int) -> None:
        self.value: int = value

    def type(self) -> NodeType:
        return NodeType.IntegerLiteral

    def json(self) -> dict:
        return {
            "type": self.type().value,
            "value": self.value
        }

class DoubleLiteral(Expression):
    def __init__(self, value: float) -> None:
        self.value: float = value

    def type(self) -> NodeType:
        return NodeType.DoubleLiteral

    def json(self) -> dict:
        return {
            "type": self.type().value,
            "value": self.value
        }
    
class IdentifierLiteral(Expression):
    def __init__(self, value: str) -> None:
        self.value: str = value

    def type(self) -> NodeType:
        return NodeType.IdentifierLiteral

    def json(self) -> dict:
        return {
            "type": self.type().value,
            "value": self.value
        }
# endregion