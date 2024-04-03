from Token import Token, TokenType, lookupIdentifier
from typing import Any

class Lexer:
    def __init__(self, source: str) -> None:
        self.source = source

        self.position: int = -1
        self.readPosition: int = 0
        self.lineNumber: int = 1

        self.currentChar: str | None = None
        self.readChar()

    def readChar(self) -> None:
        if self.readPosition >= len(self.source):
            self.currentChar = None
        else:
            self.currentChar = self.source[self.readPosition]
        
        self.position = self.readPosition
        self.readPosition += 1

    def skipWhitespace(self) -> None:
        while self.currentChar in [' ', '\t', '\n', '\r']:
            if self.currentChar == '\n':
                self.lineNumber += 1
            
            self.readChar()

    def newToken(self, tokenType: TokenType, literal: Any) -> Token:
        return Token(type=tokenType, literal=literal, lineNumber=self.lineNumber, position=self.position)
    
    def readNumber(self) -> Token:
        startPosition: int = self.position
        decimalCounter: int = 0

        output: str = ""
        while self.currentChar.isdigit() or self.currentChar == ',':
            if self.currentChar == ',':
                decimalCounter += 1

            if decimalCounter > 1:
                print(f"Error: Invalid number format at line {self.lineNumber}, position {self.position}")
                return self.newToken(TokenType.ILLEGAL, self.source[startPosition:self.position])
            
            output += self.currentChar
            self.readChar()

            if self.currentChar is None:
                break
        
        if decimalCounter == 0:
            return self.newToken(TokenType.INT, int(output))
        else:
            return self.newToken(TokenType.DOUBLE, float(output.replace(',', '.')))
        
    def isLetter(self, char: str) -> Token:
        return 'a' <= char and char <= 'z' or 'A' <= char and char <= 'Z' or char == '_'

    def readIdentifier(self) -> str:
        position: int = self.position
        while self.currentChar is not None and (self.isLetter(self.currentChar) or self.currentChar.isalnum()):
            self.readChar()
        
        return self.source[position:self.position]

    def nextToken(self) -> Token:
        token: Token = None

        self.skipWhitespace()

        match self.currentChar:
            case '+':
                token = self.newToken(TokenType.PLUS, self.currentChar)
            case '-':
                token = self.newToken(TokenType.MINUS, self.currentChar)
            case '*':
                token = self.newToken(TokenType.MULTIPLY, self.currentChar)
            case '/':
                token = self.newToken(TokenType.DIVIDE, self.currentChar)
            case '^':
                token = self.newToken(TokenType.POWER, self.currentChar)
            case '%':
                token = self.newToken(TokenType.MODULUS, self.currentChar)
            case '.':
                token = self.newToken(TokenType.DOT, self.currentChar)
            case '(':
                token = self.newToken(TokenType.LPAREN, self.currentChar)
            case ')':
                token = self.newToken(TokenType.RPAREN, self.currentChar)
            case '=':
                token = self.newToken(TokenType.EQUALS, self.currentChar)
            case ':':
                token = self.newToken(TokenType.COLON, self.currentChar)
            case None:
                token = self.newToken(TokenType.EOF, "")
            case _:
                if self.isLetter(self.currentChar):
                    literal: str = self.readIdentifier()
                    tokenType: TokenType = lookupIdentifier(literal)
                    token = self.newToken(tokenType, literal)
                    return self.newToken(tokenType, literal)
                elif self.currentChar.isdigit():
                    token = self.readNumber()
                    return token
                else:
                    token = self.newToken(TokenType.ILLEGAL, self.currentChar)
        
        self.readChar()
        return token