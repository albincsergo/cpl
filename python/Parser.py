from Lexer import Lexer
from Token import TokenType, Token
from enum import Enum, auto

from AST import Statement, Program, Expression, InfixExpression, IntegerLiteral, DoubleLiteral, ExpressionStatement
from AST import IdentifierLiteral, ShallStatement, FunctionStatement, ReturnStatement, BlockStatement, AssignStatement
from AST import IfStatement, BooleanLiteral, StringLiteral, CharLiteral, NilLiteral, PrefixExpression, CallExpression
from AST import IndexExpression, MemberExpression, CastExpression, WhileStatement, ForStatement, BreakStatement
from AST import ContinueStatement, InputStatement, OutputStatement, StructStatement, TypeExpression, Node


# precedence types
class PrecedenceType(Enum):
    P_LOWEST = 0
    P_OR = auto()
    P_AND = auto()
    P_BITOR = auto()
    P_BITXOR = auto()
    P_BITAND = auto()
    P_EQUALS = auto()
    P_LESSGREATER = auto()
    P_SHIFT = auto()
    P_SUM = auto()
    P_PRODUCT = auto()
    P_PREFIX = auto()
    P_EXPONENT = auto()
    P_CALL = auto()


# precedence table
PRECEDENCES: dict[TokenType, PrecedenceType] = {
    TokenType.OR: PrecedenceType.P_OR,
    TokenType.AND: PrecedenceType.P_AND,
    TokenType.BITOR: PrecedenceType.P_BITOR,
    TokenType.BITXOR: PrecedenceType.P_BITXOR,
    TokenType.BITAND: PrecedenceType.P_BITAND,
    TokenType.EQEQ: PrecedenceType.P_EQUALS,
    TokenType.NOTEQ: PrecedenceType.P_EQUALS,
    TokenType.LESS: PrecedenceType.P_LESSGREATER,
    TokenType.GREATER: PrecedenceType.P_LESSGREATER,
    TokenType.LESSEQ: PrecedenceType.P_LESSGREATER,
    TokenType.GREATEREQ: PrecedenceType.P_LESSGREATER,
    TokenType.SHIFTLEFT: PrecedenceType.P_SHIFT,
    TokenType.SHIFTRIGHT: PrecedenceType.P_SHIFT,
    TokenType.PLUS: PrecedenceType.P_SUM,
    TokenType.MINUS: PrecedenceType.P_SUM,
    TokenType.MULTIPLY: PrecedenceType.P_PRODUCT,
    TokenType.DIVIDE: PrecedenceType.P_PRODUCT,
    TokenType.MODULUS: PrecedenceType.P_PRODUCT,
    TokenType.POWER: PrecedenceType.P_EXPONENT,
    TokenType.LPAREN: PrecedenceType.P_CALL,
    TokenType.LBRACKET: PrecedenceType.P_CALL,
    TokenType.MEMBER: PrecedenceType.P_CALL,
}

# assignment operators and the binary operator they apply ('=' is plain assignment)
ASSIGN_OPERATORS: dict[TokenType, str] = {
    TokenType.EQUALS: "=",
    TokenType.PLUSEQ: "+",
    TokenType.MINUSEQ: "-",
    TokenType.MULTIPLYEQ: "*",
    TokenType.DIVIDEEQ: "/",
    TokenType.MODULUSEQ: "%",
    TokenType.POWEREQ: "^",
    TokenType.BITANDEQ: "&",
    TokenType.BITOREQ: "|",
    TokenType.BITXOREQ: "^^",
    TokenType.SHIFTLEFTEQ: "<<",
    TokenType.SHIFTRIGHTEQ: ">>",
}

# when a type ends in '>>' (vec<vec<it>>) the lexer can't know it isn't a shift, so we split it
ANGLE_SPLITS: dict[TokenType, TokenType] = {
    TokenType.SHIFTRIGHT: TokenType.GREATER,
    TokenType.GREATEREQ: TokenType.EQUALS,
    TokenType.SHIFTRIGHTEQ: TokenType.GREATEREQ,
}

# token types whose name reads fine without quotes in "expected ..." messages
UNQUOTED_TYPES: set[TokenType] = {
    TokenType.IDENTIFIER, TokenType.TYPE, TokenType.INT, TokenType.DOUBLE, TokenType.STRING, TokenType.CHAR, TokenType.EOF
}

MAX_ERRORS: int = 20


class Parser:
    def __init__(self, lexer: Lexer) -> None:
        self.lexer: Lexer = lexer

        self.errors: list[str] = []
        self.errorLines: set[int] = set()

        self.currentToken: Token = None
        self.peekToken: Token = None
        self.pendingTokens: list[Token] = []

        self.prefixParseFns: dict[TokenType, callable] = {
            TokenType.IDENTIFIER: self.parseIdentifier,
            TokenType.INT: self.parseIntegerLiteral,
            TokenType.DOUBLE: self.parseDoubleLiteral,
            TokenType.STRING: self.parseStringLiteral,
            TokenType.CHAR: self.parseCharLiteral,
            TokenType.ENDL: self.parseEndlLiteral,
            TokenType.TRUE: self.parseBooleanLiteral,
            TokenType.FALSE: self.parseBooleanLiteral,
            TokenType.NIL: self.parseNilLiteral,
            TokenType.LPAREN: self.parseGroupedExpression,
            TokenType.MINUS: self.parsePrefixExpression,
            TokenType.BANG: self.parsePrefixExpression,
            TokenType.BITNOT: self.parsePrefixExpression,
            TokenType.TYPE: self.parseCastExpression,
        }

        self.infixParseFns: dict[TokenType, callable] = {
            tokenType: self.parseInfixExpression
            for tokenType in PRECEDENCES
            if tokenType not in [TokenType.LPAREN, TokenType.LBRACKET, TokenType.MEMBER]
        }
        self.infixParseFns[TokenType.LPAREN] = self.parseCallExpression
        self.infixParseFns[TokenType.LBRACKET] = self.parseIndexExpression
        self.infixParseFns[TokenType.MEMBER] = self.parseMemberExpression

        self.nextToken()
        self.nextToken()

    # region parse helpers
    def nextToken(self) -> None:
        self.currentToken = self.peekToken
        if self.pendingTokens:
            self.peekToken = self.pendingTokens.pop(0)
        else:
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

    def describeType(self, tokenType: TokenType) -> str:
        if tokenType in UNQUOTED_TYPES:
            return tokenType.value
        return f"'{tokenType.value}'"

    def error(self, message: str, token: Token) -> None:
        # one error per line is plenty, the rest are usually follow-up noise
        if token.lineNumber in self.errorLines or len(self.errors) >= MAX_ERRORS:
            return
        self.errorLines.add(token.lineNumber)
        self.errors.append(f"~~~ SYNTAX ERROR (line {token.lineNumber}): {message}")

    def peekError(self, tokenType: TokenType) -> None:
        message: str = f"expected {self.describeType(tokenType)} but found {self.describeToken(self.peekToken)}"
        found: Token = self.peekToken
        if tokenType == TokenType.IDENTIFIER and isinstance(found.literal, str) and found.literal.isidentifier():
            # someone tried to name a variable 'r', 'f', 'in', 'it', ...
            if found.type == TokenType.TYPE:
                message += f"; '{found.literal}' is a type name and can't be used as a name"
            elif found.type not in [TokenType.IDENTIFIER, TokenType.INT, TokenType.DOUBLE, TokenType.STRING, TokenType.CHAR]:
                meaning: str = "" if found.literal == found.type.value else f" (short for '{found.type.value}')"
                message += f"; '{found.literal}' is a keyword{meaning} and can't be used as a name"
        self.error(message, found)

    def describeToken(self, token: Token) -> str:
        if token.type == TokenType.ILLEGAL:
            if token.literal == "unterminated string":
                return "an unterminated string"
            if token.literal == "bad character literal":
                return "a bad character literal (it must hold exactly one character)"
            return f"invalid input '{token.literal}'"
        return token.describe()

    def noPrefixParseFnError(self, token: Token) -> None:
        self.error(f"expected an expression but found {self.describeToken(token)}", token)

    def currentPrecedence(self) -> PrecedenceType:
        return PRECEDENCES.get(self.currentToken.type, PrecedenceType.P_LOWEST)

    def peekPrecedence(self) -> PrecedenceType:
        return PRECEDENCES.get(self.peekToken.type, PrecedenceType.P_LOWEST)

    def at(self, node: Node, token: Token) -> Node:
        # remembers the source line of a node for error messages
        if node is not None:
            node.line = token.lineNumber
        return node

    def synchronize(self) -> None:
        # after an error, skip to the end of the broken statement
        while not self.currentTokenIs(TokenType.EOF) and not self.currentTokenIs(TokenType.DOT) \
                and not self.peekTokenIs(TokenType.RBRACE) and not self.peekTokenIs(TokenType.EOF):
            self.nextToken()
    # endregion

    def parseProgram(self) -> Program:
        program: Program = Program()

        while not self.currentTokenIs(TokenType.EOF):
            if self.currentTokenIs(TokenType.DOT):
                self.nextToken()
                continue

            statement: Statement = self.parseStatement()
            if statement is not None:
                program.statements.append(statement)
            else:
                self.synchronize()

            self.nextToken()

        return program

    # region statement helpers
    def parseStatement(self) -> Statement:
        token: Token = self.currentToken
        statement: Statement | None

        match token.type:
            case TokenType.FUNC:
                statement = self.parseFunctionStatement()
            case TokenType.STRUCT:
                statement = self.parseStructStatement()
            case TokenType.RET:
                statement = self.parseReturnStatement()
            case TokenType.IF:
                statement = self.parseIfStatement()
            case TokenType.WHILE:
                statement = self.parseWhileStatement()
            case TokenType.FOR:
                statement = self.parseForStatement()
            case TokenType.BREAK:
                statement = BreakStatement() if self.expectPeek(TokenType.DOT) else None
            case TokenType.CONTINUE:
                statement = ContinueStatement() if self.expectPeek(TokenType.DOT) else None
            case TokenType.IN:
                statement = self.parseInputStatement()
            case TokenType.OUT:
                statement = self.parseOutputStatement()
            case TokenType.LBRACE:
                statement = self.parseBlockStatement()
            case _:
                statement = self.parseSimpleStatement(terminated=True)

        return self.at(statement, token)

    def parseSimpleStatement(self, terminated: bool) -> Statement | None:
        # declarations, assignments, ++/-- and expression statements: the things allowed in a for header
        token: Token = self.currentToken
        statement: Statement | None

        if self.currentTokenIs(TokenType.SHALL):
            return self.parseShallStatement(terminated)

        if self.currentToken.type in [TokenType.INCREMENT, TokenType.DECREMENT]:
            operator: str = "+" if self.currentTokenIs(TokenType.INCREMENT) else "-"
            self.nextToken()
            target: Expression = self.parseExpression(PrecedenceType.P_PREFIX)
            if target is None:
                return None
            statement = AssignStatement(target, operator, self.at(IntegerLiteral(1), token))
        else:
            expression: Expression = self.parseExpression(PrecedenceType.P_LOWEST)
            if expression is None:
                return None

            if self.peekToken.type in ASSIGN_OPERATORS:
                self.nextToken()
                operator = ASSIGN_OPERATORS[self.currentToken.type]
                self.nextToken()
                value: Expression = self.parseExpression(PrecedenceType.P_LOWEST)
                if value is None:
                    return None
                statement = AssignStatement(expression, operator, value)
            elif self.peekToken.type in [TokenType.INCREMENT, TokenType.DECREMENT]:
                self.nextToken()
                operator = "+" if self.currentTokenIs(TokenType.INCREMENT) else "-"
                statement = AssignStatement(expression, operator, self.at(IntegerLiteral(1), token))
            else:
                statement = ExpressionStatement(expression=expression)

        if terminated and not self.expectPeek(TokenType.DOT):
            return None

        return self.at(statement, token)

    def parseShallStatement(self, terminated: bool) -> ShallStatement | None:
        # _ a: int = 137.    _ a, b, c: ll.
        token: Token = self.currentToken
        statement: ShallStatement = ShallStatement()

        if not self.expectPeek(TokenType.IDENTIFIER):
            return None
        statement.names.append(self.currentToken.literal)

        while self.peekTokenIs(TokenType.COMMA):
            self.nextToken()
            if not self.expectPeek(TokenType.IDENTIFIER):
                return None
            statement.names.append(self.currentToken.literal)

        if not self.expectPeek(TokenType.COLON):
            return None

        self.nextToken()
        statement.valueType = self.parseType()
        if statement.valueType is None:
            return None

        if self.peekTokenIs(TokenType.EQUALS):
            self.nextToken()
            self.nextToken()
            statement.value = self.parseExpression(PrecedenceType.P_LOWEST)
            if statement.value is None:
                return None

        if terminated and not self.expectPeek(TokenType.DOT):
            return None

        return self.at(statement, token)

    def parseType(self) -> TypeExpression | None:
        # it, ll, MyStruct, vec<it>, arr<ll, 100>, map<st, vec<it>>
        token: Token = self.currentToken
        if token.type not in [TokenType.TYPE, TokenType.IDENTIFIER]:
            self.error(f"expected a type but found {self.describeToken(token)}", token)
            return None

        typeExpression: TypeExpression = TypeExpression(token.literal, line=token.lineNumber)
        if not self.peekTokenIs(TokenType.LESS):
            return typeExpression

        self.nextToken()
        while True:
            self.nextToken()
            if self.currentTokenIs(TokenType.INT):
                typeExpression.arguments.append(self.currentToken.literal)
            else:
                argument: TypeExpression | None = self.parseType()
                if argument is None:
                    return None
                typeExpression.arguments.append(argument)

            if self.peekTokenIs(TokenType.COMMA):
                self.nextToken()
                continue
            break

        self.splitClosingAngle()
        if not self.expectPeek(TokenType.GREATER):
            return None

        return typeExpression

    def splitClosingAngle(self) -> None:
        rest: TokenType | None = ANGLE_SPLITS.get(self.peekToken.type)
        if rest is None:
            return

        peek: Token = self.peekToken
        self.pendingTokens.insert(0, Token(rest, peek.literal[1:], peek.lineNumber, peek.position + 1))
        self.peekToken = Token(TokenType.GREATER, ">", peek.lineNumber, peek.position)

    def parseFunctionStatement(self) -> FunctionStatement | None:
        # f name(a: it, b: ll) -> ll { r a + b. }
        statement: FunctionStatement = FunctionStatement()

        if not self.expectPeek(TokenType.IDENTIFIER):
            return None
        statement.name = self.currentToken.literal

        if not self.expectPeek(TokenType.LPAREN):
            return None

        if self.peekTokenIs(TokenType.RPAREN):
            self.nextToken()
        else:
            while True:
                if not self.expectPeek(TokenType.IDENTIFIER):
                    return None
                name: str = self.currentToken.literal

                if not self.expectPeek(TokenType.COLON):
                    return None
                self.nextToken()
                parameterType: TypeExpression | None = self.parseType()
                if parameterType is None:
                    return None
                statement.parameters.append((name, parameterType))

                if self.peekTokenIs(TokenType.COMMA):
                    self.nextToken()
                    continue
                if not self.expectPeek(TokenType.RPAREN):
                    return None
                break

        # no arrow means the function returns nothing
        if self.peekTokenIs(TokenType.ARROW):
            self.nextToken()
            self.nextToken()
            statement.returnType = self.parseType()
            if statement.returnType is None:
                return None

        if not self.expectPeek(TokenType.LBRACE):
            return None

        statement.body = self.parseBlockStatement()
        if statement.body is None:
            return None

        return statement

    def parseStructStatement(self) -> StructStatement | None:
        # struct Point { x: it. y: it. }
        statement: StructStatement = StructStatement()

        if not self.expectPeek(TokenType.IDENTIFIER):
            return None
        statement.name = self.currentToken.literal

        if not self.expectPeek(TokenType.LBRACE):
            return None

        while not self.peekTokenIs(TokenType.RBRACE):
            if not self.expectPeek(TokenType.IDENTIFIER):
                return None
            name: str = self.currentToken.literal

            if not self.expectPeek(TokenType.COLON):
                return None
            self.nextToken()
            fieldType: TypeExpression | None = self.parseType()
            if fieldType is None:
                return None
            statement.fields.append((name, fieldType))

            if self.peekTokenIs(TokenType.COMMA):
                self.nextToken()
            elif not self.expectPeek(TokenType.DOT):
                return None

        self.nextToken()
        return statement

    def parseReturnStatement(self) -> ReturnStatement | None:
        statement: ReturnStatement = ReturnStatement()

        if self.peekTokenIs(TokenType.DOT):
            self.nextToken()
            return statement

        self.nextToken()

        statement.returnValue = self.parseExpression(PrecedenceType.P_LOWEST)
        if statement.returnValue is None:
            return None

        if not self.expectPeek(TokenType.DOT):
            return None

        return statement

    def parseBlockStatement(self) -> BlockStatement | None:
        blockStatement: BlockStatement = self.at(BlockStatement(), self.currentToken)

        self.nextToken()

        while not self.currentTokenIs(TokenType.RBRACE) and not self.currentTokenIs(TokenType.EOF):
            if self.currentTokenIs(TokenType.DOT):
                self.nextToken()
                continue

            statement: Statement = self.parseStatement()
            if statement is not None:
                blockStatement.statements.append(statement)
            else:
                self.synchronize()

            self.nextToken()

        if self.currentTokenIs(TokenType.EOF):
            self.error("expected '}' but reached the end of the file", self.currentToken)
            return None

        return blockStatement

    def parseIfStatement(self) -> IfStatement | None:
        # if cond { ... } else if cond { ... } else { ... }
        self.nextToken()

        condition: Expression = self.parseExpression(PrecedenceType.P_LOWEST)
        if condition is None:
            return None

        if not self.expectPeek(TokenType.LBRACE):
            return None

        consequence: BlockStatement | None = self.parseBlockStatement()
        if consequence is None:
            return None

        alternative: Statement | None = None
        if self.peekTokenIs(TokenType.ELSE):
            self.nextToken()

            if self.peekTokenIs(TokenType.IF):
                self.nextToken()
                ifToken: Token = self.currentToken
                alternative = self.at(self.parseIfStatement(), ifToken)
            elif self.expectPeek(TokenType.LBRACE):
                alternative = self.parseBlockStatement()

            if alternative is None:
                return None

        return IfStatement(condition, consequence, alternative)

    def parseWhileStatement(self) -> WhileStatement | None:
        self.nextToken()

        condition: Expression = self.parseExpression(PrecedenceType.P_LOWEST)
        if condition is None:
            return None

        if not self.expectPeek(TokenType.LBRACE):
            return None

        body: BlockStatement | None = self.parseBlockStatement()
        if body is None:
            return None

        return WhileStatement(condition, body)

    def parseForStatement(self) -> ForStatement | None:
        # for (_ i: it = 0. i < n. ++i) { ... }   - any of the three parts may be left out
        statement: ForStatement = ForStatement()

        if not self.expectPeek(TokenType.LPAREN):
            return None
        self.nextToken()

        if not self.currentTokenIs(TokenType.DOT):
            statement.initializer = self.parseSimpleStatement(terminated=True)
            if statement.initializer is None:
                return None
        self.nextToken()

        if not self.currentTokenIs(TokenType.DOT):
            statement.condition = self.parseExpression(PrecedenceType.P_LOWEST)
            if statement.condition is None or not self.expectPeek(TokenType.DOT):
                return None
        self.nextToken()

        if not self.currentTokenIs(TokenType.RPAREN):
            statement.step = self.parseSimpleStatement(terminated=False)
            if statement.step is None or not self.expectPeek(TokenType.RPAREN):
                return None

        if not self.expectPeek(TokenType.LBRACE):
            return None

        statement.body = self.parseBlockStatement()
        if statement.body is None:
            return None

        return statement

    def parseInputStatement(self) -> InputStatement | None:
        # in @ a @ b.
        statement: InputStatement = InputStatement()

        if not self.peekTokenIs(TokenType.INPUT):
            self.peekError(TokenType.INPUT)
            return None

        while self.peekTokenIs(TokenType.INPUT):
            self.nextToken()
            self.nextToken()
            target: Expression = self.parseExpression(PrecedenceType.P_LOWEST)
            if target is None:
                return None
            statement.targets.append(target)

        if not self.expectPeek(TokenType.DOT):
            return None

        return statement

    def parseOutputStatement(self) -> OutputStatement | None:
        # ou @@ a @@ " " @@ b @@ el.
        statement: OutputStatement = OutputStatement()

        if not self.peekTokenIs(TokenType.OUTPUT):
            self.peekError(TokenType.OUTPUT)
            return None

        while self.peekTokenIs(TokenType.OUTPUT):
            self.nextToken()
            self.nextToken()
            value: Expression = self.parseExpression(PrecedenceType.P_LOWEST)
            if value is None:
                return None
            statement.values.append(value)

        if not self.expectPeek(TokenType.DOT):
            return None

        return statement
    # endregion

    # region expression helpers
    def parseExpression(self, precedence: PrecedenceType) -> Expression | None:
        prefixFunction: callable | None = self.prefixParseFns.get(self.currentToken.type)
        if prefixFunction is None:
            self.noPrefixParseFnError(self.currentToken)
            return None

        token: Token = self.currentToken
        leftExpression: Expression | None = self.at(prefixFunction(), token)
        if leftExpression is None:
            return None

        while precedence.value < self.peekPrecedence().value:
            infixFunction: callable | None = self.infixParseFns.get(self.peekToken.type)
            if infixFunction is None:
                return leftExpression

            self.nextToken()

            token = self.currentToken
            leftExpression = self.at(infixFunction(leftExpression), token)
            if leftExpression is None:
                return None

        return leftExpression

    def parseInfixExpression(self, leftNode: Expression) -> Expression | None:
        infixExpression: InfixExpression = InfixExpression(leftNode=leftNode, operator=self.currentToken.literal)

        precedence = self.currentPrecedence()

        # '^' is right-associative: 2 ^ 3 ^ 2 == 2 ^ (3 ^ 2)
        if self.currentTokenIs(TokenType.POWER):
            precedence = PrecedenceType(precedence.value - 1)

        self.nextToken()

        infixExpression.rightNode = self.parseExpression(precedence)
        if infixExpression.rightNode is None:
            return None

        return infixExpression

    def parsePrefixExpression(self) -> Expression | None:
        prefixExpression: PrefixExpression = PrefixExpression(operator=self.currentToken.literal)

        self.nextToken()

        prefixExpression.rightNode = self.parseExpression(PrecedenceType.P_PREFIX)
        if prefixExpression.rightNode is None:
            return None

        return prefixExpression

    def parseGroupedExpression(self) -> Expression | None:
        self.nextToken()

        expression: Expression = self.parseExpression(PrecedenceType.P_LOWEST)

        if expression is None or not self.expectPeek(TokenType.RPAREN):
            return None

        return expression

    def parseExpressionList(self, end: TokenType) -> list[Expression] | None:
        expressions: list[Expression] = []

        if self.peekTokenIs(end):
            self.nextToken()
            return expressions

        self.nextToken()
        expression: Expression = self.parseExpression(PrecedenceType.P_LOWEST)
        if expression is None:
            return None
        expressions.append(expression)

        while self.peekTokenIs(TokenType.COMMA):
            self.nextToken()
            self.nextToken()
            expression = self.parseExpression(PrecedenceType.P_LOWEST)
            if expression is None:
                return None
            expressions.append(expression)

        if not self.expectPeek(end):
            return None

        return expressions

    def parseCallExpression(self, function: Expression) -> Expression | None:
        arguments: list[Expression] | None = self.parseExpressionList(TokenType.RPAREN)
        if arguments is None:
            return None
        return CallExpression(function, arguments)

    def parseIndexExpression(self, leftNode: Expression) -> Expression | None:
        self.nextToken()

        index: Expression = self.parseExpression(PrecedenceType.P_LOWEST)
        if index is None or not self.expectPeek(TokenType.RBRACKET):
            return None

        return IndexExpression(leftNode, index)

    def parseMemberExpression(self, leftNode: Expression) -> Expression:
        return MemberExpression(leftNode, self.currentToken.literal)

    def parseCastExpression(self) -> Expression | None:
        # it(x), st(42), vec<it>(n), map<st, it>()
        targetType: TypeExpression | None = self.parseType()
        if targetType is None:
            return None

        if not self.expectPeek(TokenType.LPAREN):
            return None

        arguments: list[Expression] | None = self.parseExpressionList(TokenType.RPAREN)
        if arguments is None:
            return None

        return CastExpression(targetType, arguments)
    # endregion

    # region prefix helpers
    def parseIntegerLiteral(self) -> Expression:
        return IntegerLiteral(value=int(self.currentToken.literal))

    def parseDoubleLiteral(self) -> Expression:
        return DoubleLiteral(value=float(self.currentToken.literal))

    def parseStringLiteral(self) -> Expression:
        return StringLiteral(value=self.currentToken.literal)

    def parseCharLiteral(self) -> Expression:
        return CharLiteral(value=self.currentToken.literal)

    def parseEndlLiteral(self) -> Expression:
        # el is endl: a newline character
        return CharLiteral(value="\n")

    def parseIdentifier(self) -> IdentifierLiteral:
        return IdentifierLiteral(value=self.currentToken.literal)

    def parseBooleanLiteral(self) -> BooleanLiteral:
        return BooleanLiteral(value=self.currentTokenIs(TokenType.TRUE))

    def parseNilLiteral(self) -> NilLiteral:
        return NilLiteral()
    # endregion
