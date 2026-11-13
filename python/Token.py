from enum import Enum
from typing import Any


class TokenType(Enum):
    # special tokens
    EOF = "EOF" # end of file
    ILLEGAL = "ILLEGAL" # lexer error

    # data types
    INT = "INT"
    DOUBLE = "DOUBLE" 
    IDENTIFIER = "IDENTIFIER"

    # arithmetic operators
    PLUS = "PLUS"
    MINUS = "MINUS"
    MULTIPLY = "MULTIPLY"
    DIVIDE = "DIVIDE"
    POWER = "POWER"
    MODULUS = "MODULUS"

    # symbols
    DOT = "DOT"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    LBRACE = "LBRACE"
    RBRACE = "RBRACE"
    COLON = "COLON"
    EQUALS = "EQUALS"
    ARROW = "ARROW"

    # comparison symbols
    LESS = '<'
    GREATER = '>'
    EQEQ = '=='
    NOTEQ = '!='
    LESSEQ = '<='
    GREATEREQ = '>='

    # keywords
    SHALL = "SHALL"
    FUNC = "FUNC"
    RET = "RET"
    IF = "IF"
    ELSE = "ELSE"
    TRUE = "TRUE"
    FALSE = "FALSE"

    # typing
    TYPE = "TYPE"

class Token:
    def __init__(self, type: TokenType, literal: Any, lineNumber: int, position: int) -> None:
        self.type = type
        self.literal = literal
        self.lineNumber = lineNumber
        self.position = position
    
    def __str__(self) -> str:
        return f"Token[{self.type} : {self.literal}, line {self.lineNumber}, position {self.position}]"
    
    def __repr__(self) -> str:
        return str(self)
    
KEYWORDS: dict[str, TokenType] = {
    "shall": TokenType.SHALL,
    "func": TokenType.FUNC,
    "ret": TokenType.RET,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
}

ALTERNATIVE_KEYWORDS: dict[str, TokenType] = {
    "eq": TokenType.EQUALS,
    "_": TokenType.SHALL,
    "f": TokenType.FUNC,
    "r": TokenType.RET,
    "els": TokenType.ELSE
}

TYPE_KEYWORDS: list[str] = ["int", "double"]


def lookupIdentifier(identifier: str) -> TokenType:
    tokenType: TokenType | None = KEYWORDS.get(identifier)
    if tokenType is not None:
        return tokenType
    
    tokenType: TokenType | None = ALTERNATIVE_KEYWORDS.get(identifier)

    if tokenType is not None:
        return tokenType
    
    if identifier in TYPE_KEYWORDS:
        return TokenType.TYPE
    
    return TokenType.IDENTIFIER
