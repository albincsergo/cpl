from enum import Enum
from typing import Any


class TokenType(Enum):
    # the values double as the human readable names used in error messages

    # special tokens
    EOF = "end of file"
    ILLEGAL = "illegal character"

    # literals
    INT = "integer"
    DOUBLE = "double"
    STRING = "string"
    CHAR = "character"
    IDENTIFIER = "identifier"

    # arithmetic operators
    PLUS = "+"
    MINUS = "-"
    MULTIPLY = "*"
    DIVIDE = "/"
    POWER = "^"
    MODULUS = "%"

    # bitwise and logical operators
    BITAND = "&"
    BITOR = "|"
    BITXOR = "^^"
    BITNOT = "~"
    SHIFTLEFT = "<<"
    SHIFTRIGHT = ">>"
    AND = "&&"
    OR = "||"
    BANG = "!"

    # comparison symbols
    LESS = "<"
    GREATER = ">"
    EQEQ = "=="
    NOTEQ = "!="
    LESSEQ = "<="
    GREATEREQ = ">="

    # assignment
    EQUALS = "="
    PLUSEQ = "+="
    MINUSEQ = "-="
    MULTIPLYEQ = "*="
    DIVIDEEQ = "/="
    MODULUSEQ = "%="
    POWEREQ = "^="
    BITANDEQ = "&="
    BITOREQ = "|="
    BITXOREQ = "^^="
    SHIFTLEFTEQ = "<<="
    SHIFTRIGHTEQ = ">>="
    INCREMENT = "++"
    DECREMENT = "--"

    # symbols
    DOT = "."
    MEMBER = "member access"
    COMMA = ","
    COLON = ":"
    ARROW = "->"
    LPAREN = "("
    RPAREN = ")"
    LBRACE = "{"
    RBRACE = "}"
    LBRACKET = "["
    RBRACKET = "]"
    INPUT = "@"
    OUTPUT = "@@"
    QUESTION = "?"

    # keywords
    SHALL = "shall"
    FUNC = "func"
    RET = "ret"
    IF = "if"
    ELSE = "else"
    WHILE = "while"
    FOR = "for"
    BREAK = "break"
    CONTINUE = "continue"
    STRUCT = "struct"
    IN = "in"
    OUT = "ou"
    TRUE = "true"
    FALSE = "false"
    NIL = "nil"
    ENDL = "el"

    # typing
    TYPE = "type name"


class Token:
    def __init__(self, type: TokenType, literal: Any, lineNumber: int, position: int) -> None:
        self.type = type
        self.literal = literal
        self.lineNumber = lineNumber
        self.position = position

    def __str__(self) -> str:
        return f"Token[{self.type} : {self.literal!r}, line {self.lineNumber}, position {self.position}]"

    def __repr__(self) -> str:
        return str(self)

    def describe(self) -> str:
        # how the token is shown in error messages
        match self.type:
            case TokenType.EOF:
                return "end of file"
            case TokenType.STRING:
                return f'string "{self.literal}"'
            case TokenType.CHAR:
                return f"character {self.literal!r}"
            case TokenType.MEMBER:
                return f"'.{self.literal}'"
        return f"'{self.literal}'"


KEYWORDS: dict[str, TokenType] = {
    "shall": TokenType.SHALL,
    "func": TokenType.FUNC,
    "ret": TokenType.RET,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "for": TokenType.FOR,
    "break": TokenType.BREAK,
    "continue": TokenType.CONTINUE,
    "struct": TokenType.STRUCT,
    "in": TokenType.IN,
    "ou": TokenType.OUT,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    "nil": TokenType.NIL,
    "el": TokenType.ENDL,
}

# the competitive programmer spellings
ALTERNATIVE_KEYWORDS: dict[str, TokenType] = {
    "eq": TokenType.EQUALS,
    "_": TokenType.SHALL,
    "els": TokenType.ELSE,
    "wh": TokenType.WHILE,
    "brk": TokenType.BREAK,
    "cont": TokenType.CONTINUE,
    "stc": TokenType.STRUCT,
}

TYPE_KEYWORDS: list[str] = [
    "it", "int",
    "ll", "long",
    "ui", "uint",
    "ull", "ulong",
    "du", "double",
    "bo", "bool",
    "ch", "char",
    "st", "string",
    "vo", "void",
    "vec", "arr", "map",
    "pr", "pq", "minpq",
]


# 'f' and 'r' are also the most common variable names in competitive programming (l and r!), so the
# lexer gives them to the parser as identifiers and the parser decides from context: see
# CONTEXTUAL_KEYWORDS in Parser.py
CONTEXTUAL_KEYWORDS: dict[str, TokenType] = {"f": TokenType.FUNC, "r": TokenType.RET}


def lookupIdentifier(identifier: str) -> TokenType:
    tokenType: TokenType | None = KEYWORDS.get(identifier)
    if tokenType is not None:
        return tokenType

    tokenType = ALTERNATIVE_KEYWORDS.get(identifier)
    if tokenType is not None:
        return tokenType

    if identifier in TYPE_KEYWORDS:
        return TokenType.TYPE

    return TokenType.IDENTIFIER
