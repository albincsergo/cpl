from Token import Token, TokenType, lookupIdentifier
from typing import Any


# operators, longest first so that e.g. '<<=' wins over '<<' and '<'
OPERATORS: list[tuple[str, TokenType]] = sorted([
    ("+", TokenType.PLUS), ("-", TokenType.MINUS), ("*", TokenType.MULTIPLY), ("/", TokenType.DIVIDE),
    ("^", TokenType.POWER), ("%", TokenType.MODULUS),
    ("&", TokenType.BITAND), ("|", TokenType.BITOR), ("^^", TokenType.BITXOR), ("~", TokenType.BITNOT),
    ("<<", TokenType.SHIFTLEFT), (">>", TokenType.SHIFTRIGHT),
    ("&&", TokenType.AND), ("||", TokenType.OR), ("!", TokenType.BANG),
    ("<", TokenType.LESS), (">", TokenType.GREATER), ("==", TokenType.EQEQ), ("!=", TokenType.NOTEQ),
    ("<=", TokenType.LESSEQ), (">=", TokenType.GREATEREQ),
    ("=", TokenType.EQUALS), ("+=", TokenType.PLUSEQ), ("-=", TokenType.MINUSEQ), ("*=", TokenType.MULTIPLYEQ),
    ("/=", TokenType.DIVIDEEQ), ("%=", TokenType.MODULUSEQ), ("^=", TokenType.POWEREQ),
    ("&=", TokenType.BITANDEQ), ("|=", TokenType.BITOREQ), ("^^=", TokenType.BITXOREQ),
    ("<<=", TokenType.SHIFTLEFTEQ), (">>=", TokenType.SHIFTRIGHTEQ),
    ("++", TokenType.INCREMENT), ("--", TokenType.DECREMENT),
    (",", TokenType.COMMA), (":", TokenType.COLON), ("->", TokenType.ARROW),
    ("(", TokenType.LPAREN), (")", TokenType.RPAREN), ("{", TokenType.LBRACE), ("}", TokenType.RBRACE),
    ("[", TokenType.LBRACKET), ("]", TokenType.RBRACKET),
    ("@", TokenType.INPUT), ("@@", TokenType.OUTPUT),
], key=lambda operator: -len(operator[0]))

ESCAPES: dict[str, str] = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", "'": "'", '"': '"'}

# a '.' directly after one of these, followed by a name, is member access instead of a statement end
MEMBER_OWNERS: set[TokenType] = {TokenType.IDENTIFIER, TokenType.MEMBER, TokenType.RPAREN, TokenType.RBRACKET, TokenType.STRING}


class Lexer:
    def __init__(self, source: str) -> None:
        self.source = source

        self.position: int = -1
        self.readPosition: int = 0
        self.lineNumber: int = 1

        self.currentChar: str | None = None
        self.previousType: TokenType | None = None
        self.readChar()

    def readChar(self) -> None:
        if self.readPosition >= len(self.source):
            self.currentChar = None
        else:
            self.currentChar = self.source[self.readPosition]

        self.position = self.readPosition
        self.readPosition += 1

    def peekChar(self, offset: int = 0) -> str | None:
        index: int = self.readPosition + offset
        if index >= len(self.source):
            return None
        return self.source[index]

    def skipWhitespace(self) -> bool:
        # skips whitespace and comments, returns whether anything was skipped
        startPosition: int = self.position
        while True:
            if self.currentChar in [' ', '\t', '\n', '\r']:
                if self.currentChar == '\n':
                    self.lineNumber += 1
                self.readChar()
            elif self.currentChar == '/' and self.peekChar() == '/':
                while self.currentChar is not None and self.currentChar != '\n':
                    self.readChar()
            elif self.currentChar == '/' and self.peekChar() == '*':
                self.readChar()
                self.readChar()
                while self.currentChar is not None and not (self.currentChar == '*' and self.peekChar() == '/'):
                    if self.currentChar == '\n':
                        self.lineNumber += 1
                    self.readChar()
                self.readChar()
                self.readChar()
            else:
                return self.position != startPosition

    def newToken(self, tokenType: TokenType, literal: Any, position: int | None = None, line: int | None = None) -> Token:
        position = self.position if position is None else position
        line = self.lineNumber if line is None else line
        return Token(type=tokenType, literal=literal, lineNumber=line, position=position)

    def isLetter(self, char: str | None) -> bool:
        return char is not None and ('a' <= char <= 'z' or 'A' <= char <= 'Z' or char == '_')

    def isDigit(self, char: str | None) -> bool:
        return char is not None and '0' <= char <= '9'

    def readNumber(self) -> Token:
        # decimals use a comma like a proper European: 2,5 - but only directly between digits,
        # so 'f(1, 2)' is two arguments while 'f(1,2)' is the double 1.2
        startPosition: int = self.position
        output: str = ""
        isDouble: bool = False

        while self.isDigit(self.currentChar) or (self.currentChar == '\'' and self.isDigit(self.peekChar())):
            # digit separators: 1'000'000
            if self.currentChar != '\'':
                output += self.currentChar
            self.readChar()

        if self.currentChar == ',' and self.isDigit(self.peekChar()):
            isDouble = True
            output += '.'
            self.readChar()
            while self.isDigit(self.currentChar):
                output += self.currentChar
                self.readChar()

        # scientific notation: 1e9, 2,5e-3
        if self.currentChar in ['e', 'E'] and (
            self.isDigit(self.peekChar()) or (self.peekChar() in ['+', '-'] and self.isDigit(self.peekChar(1)))
        ):
            isDouble = True
            output += 'e'
            self.readChar()
            if self.currentChar in ['+', '-']:
                output += self.currentChar
                self.readChar()
            while self.isDigit(self.currentChar):
                output += self.currentChar
                self.readChar()

        if self.isLetter(self.currentChar):
            while self.isLetter(self.currentChar) or self.isDigit(self.currentChar):
                self.readChar()
            return self.newToken(TokenType.ILLEGAL, self.source[startPosition:self.position], startPosition)

        if isDouble:
            return self.newToken(TokenType.DOUBLE, float(output), startPosition)
        return self.newToken(TokenType.INT, int(output), startPosition)

    def readIdentifier(self) -> str:
        position: int = self.position
        while self.isLetter(self.currentChar) or self.isDigit(self.currentChar):
            self.readChar()

        return self.source[position:self.position]

    def readEscaped(self, quote: str) -> str | None:
        # reads the characters of a string or char literal up to the closing quote
        output: str = ""
        self.readChar()
        while self.currentChar != quote:
            if self.currentChar is None or self.currentChar == '\n':
                return None
            if self.currentChar == '\\':
                self.readChar()
                if self.currentChar not in ESCAPES:
                    return None
                output += ESCAPES[self.currentChar]
            else:
                output += self.currentChar
            self.readChar()

        self.readChar()
        return output

    def nextToken(self) -> Token:
        token: Token = self.lexToken()
        self.previousType = token.type
        return token

    def lexToken(self) -> Token:
        hadWhitespace: bool = self.skipWhitespace()
        startPosition: int = self.position
        startLine: int = self.lineNumber

        if self.currentChar is None:
            return self.newToken(TokenType.EOF, "")

        if self.currentChar == '.':
            if not hadWhitespace and self.previousType in MEMBER_OWNERS and self.isLetter(self.peekChar()):
                self.readChar()
                return self.newToken(TokenType.MEMBER, self.readIdentifier(), startPosition)
            self.readChar()
            return self.newToken(TokenType.DOT, '.', startPosition)

        if self.isLetter(self.currentChar):
            literal: str = self.readIdentifier()
            return self.newToken(lookupIdentifier(literal), literal, startPosition)

        if self.isDigit(self.currentChar):
            return self.readNumber()

        if self.currentChar == '"':
            value: str | None = self.readEscaped('"')
            if value is None:
                return self.newToken(TokenType.ILLEGAL, "unterminated string", startPosition, startLine)
            return self.newToken(TokenType.STRING, value, startPosition, startLine)

        if self.currentChar == '\'':
            value = self.readEscaped('\'')
            if value is None or len(value) != 1:
                return self.newToken(TokenType.ILLEGAL, "bad character literal", startPosition, startLine)
            return self.newToken(TokenType.CHAR, value, startPosition, startLine)

        for symbol, tokenType in OPERATORS:
            if self.source.startswith(symbol, self.position):
                for _ in symbol:
                    self.readChar()
                return self.newToken(tokenType, symbol, startPosition)

        char: str = self.currentChar
        self.readChar()
        return self.newToken(TokenType.ILLEGAL, char, startPosition)
