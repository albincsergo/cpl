from Lexer import Lexer
from Token import TokenType, Token
from typing import Any
from enum import Enum, auto

from AST import Statement, Program, Expression, InfixExpression, IntegerLiteral, DoubleLiteral, ExpressionStatement, IdentifierLiteral, ShallStatement

# precedence types
class PrecedenceType(Enum):
    P_LOWEST = 0
    P_EQUALS = auto()
    P_LESSGREATER = auto()
    P_SUM = auto()
    P_PRODUCT = auto()
    P_PREFIX = auto()
    P_EXPONENT = auto()
    P_CALL = auto()
    P_INDEX = auto()
    
# precedence table
PRECEDENCES: dict[TokenType, PrecedenceType] = {
    TokenType.PLUS: PrecedenceType.P_SUM,
    TokenType.MINUS: PrecedenceType.P_SUM,
    TokenType.MULTIPLY: PrecedenceType.P_PRODUCT,
    TokenType.DIVIDE: PrecedenceType.P_PRODUCT,
    TokenType.MODULUS: PrecedenceType.P_PRODUCT,
    TokenType.POWER: PrecedenceType.P_EXPONENT
}

class Parser:
    def __init__(self, lexer: Lexer) -> None:
        self.lexer: Lexer = lexer
        
        self.errors: list[str] = []

        self.currentToken: Token = None
        self.peekToken: Token = None

        self.prefixParseFns: dict[TokenType, callable] = {
            TokenType.INT: self.parseIntegerLiteral,
            TokenType.DOUBLE: self.parseDoubleLiteral,
            TokenType.LPAREN: self.parseGroupedExpression
        }

        self.infixParseFns: dict[TokenType, callable] = {
            TokenType.PLUS: self.parseInfixExpression,
            TokenType.MINUS: self.parseInfixExpression,
            TokenType.MULTIPLY: self.parseInfixExpression,
            TokenType.DIVIDE: self.parseInfixExpression,
            TokenType.MODULUS: self.parseInfixExpression,
            TokenType.POWER: self.parseInfixExpression
        }

        self.nextToken()
        self.nextToken()

    # region parse helpers
    def nextToken(self) -> None:
        self.currentToken = self.peekToken
        self.peekToken = self.lexer.nextToken()

    def currentTokenIs(self, tokenType: TokenType) -> bool:
        return self.currentToken.type == tokenType

    def peekTokenIs(self, tokenType: TokenType) -> bool:
        return self.peekToken.type == tokenType
    
    def expectPeek(self, tokenType: TokenType) -> bool:
        if self.peekTokenIs(tokenType):
            self.nextToken()
            return True
        else:
            self.peekError(tokenType)
            return False
        
    def peekError(self, tokenType: TokenType) -> None:
        self.errors.append(f"Expected next token to be {tokenType}, got {self.peekToken.type} instead")

    def noPrefixParseFnError(self, tokenType: TokenType) -> None:
        self.errors.append(f"No prefix parse function for {tokenType} found")

    def currentPrecedence(self) -> PrecedenceType:
        precedence: int | None = PRECEDENCES.get(self.currentToken.type)
        if precedence is None:
            return PrecedenceType.P_LOWEST
        return precedence
    
    def peekPrecedence(self) -> PrecedenceType:
        precedence: int | None = PRECEDENCES.get(self.peekToken.type)
        if precedence is None:
            return PrecedenceType.P_LOWEST
        return precedence
    # endregion

    def parseProgram(self) -> None:
        program: Program = Program()

        while self.currentToken.type != TokenType.EOF:
            statement: Statement = self.parseStatement()
            if statement is not None:
                program.statements.append(statement)
            
            self.nextToken()

        return program
    
    # region statement helpers
    def parseStatement(self) -> Statement:
        match self.currentToken.type:
            case TokenType.SHALL:
                return self.parseShallStatement()
            case _:
                return self.parseExpressionStatement()
            
    def parseShallStatement(self) -> ShallStatement:
        # shall a: int = 137
        statement: ShallStatement = ShallStatement()

        if not self.expectPeek(TokenType.IDENTIFIER):
            return None
       
        statement.name = IdentifierLiteral(value=self.currentToken.literal)

        if not self.expectPeek(TokenType.COLON):
            return None
        
        if not self.expectPeek(TokenType.TYPE):
            return None
        
        statement.valueType = self.currentToken.literal

        if not self.expectPeek(TokenType.EQUALS):
            return None
        
        self.nextToken()
        
        statement.value = self.parseExpression(PrecedenceType.P_LOWEST)

        while not self.currentTokenIs(TokenType.DOT) and not self.currentTokenIs(TokenType.EOF):
            self.nextToken()

        return statement
    
    def parseExpressionStatement(self) -> ExpressionStatement:
        expression = self.parseExpression(PrecedenceType.P_LOWEST)

        if self.peekTokenIs(TokenType.DOT):
            self.nextToken()
        
        statement: ExpressionStatement = ExpressionStatement(expression=expression)
        return statement
    # endregion

    # region expression helpers
    def parseExpression(self, precedence: PrecedenceType) -> Expression:
        prefixFunction: callable | None = self.prefixParseFns.get(self.currentToken.type)
        if prefixFunction is None:
            self.noPrefixParseFnError(self.currentToken.type)
            return None
        
        leftExpression: Expression = prefixFunction()
        while not self.peekTokenIs(TokenType.DOT) and precedence.value < self.peekPrecedence().value:
            infixFunction: callable | None = self.infixParseFns.get(self.peekToken.type)
            if infixFunction is None:
                return leftExpression
            
            self.nextToken()

            leftExpression = infixFunction(leftExpression)

        return leftExpression

    def parseInfixExpression(self, leftNode: Expression) -> Expression:
        infixExpression: InfixExpression = InfixExpression(leftNode=leftNode, operator=self.currentToken.literal)

        precedence = self.currentPrecedence()
        
        self.nextToken()

        infixExpression.rightNode = self.parseExpression(precedence)

        return infixExpression
    
    def parseGroupedExpression(self) -> Expression:
        self.nextToken()

        expression: Expression = self.parseExpression(PrecedenceType.P_LOWEST)

        if not self.expectPeek(TokenType.RPAREN):
            return None
        
        return expression
    # endregion

    # region prefix helpers
    def parseIntegerLiteral(self) -> Expression:
        integerLiteral: IntegerLiteral = IntegerLiteral(value=int(self.currentToken.literal))
    
        return integerLiteral

    def parseDoubleLiteral(self) -> Expression:
        doubleLiteral: DoubleLiteral = DoubleLiteral(value=float(self.currentToken.literal))

        return doubleLiteral
    # endregion 