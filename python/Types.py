from llvmlite import ir


# kinds understood by the runtime for sorting and map keys (see runtime/cpl_runtime.c)
SORT_SIGNED: int = 0
SORT_UNSIGNED: int = 1
SORT_DOUBLE: int = 2
SORT_STRING: int = 3

BYTE_POINTER: ir.PointerType = ir.IntType(8).as_pointer()


class CType:
    # a CPL type: the language-level information (signedness, element types, ...) next to its LLVM type
    def __init__(self, kind: str, name: str, irType: ir.Type, bits: int = 0, signed: bool = False,
                 elem: "CType" = None, key: "CType" = None, value: "CType" = None, struct: "StructInfo" = None,
                 first: "CType" = None, second: "CType" = None, minFirst: bool = False) -> None:
        self.kind = kind
        self.name = name
        self.irType = irType
        self.bits = bits
        self.signed = signed
        # vec and pq elements
        self.elem = elem
        # map keys and values
        self.key = key
        self.value = value
        self.struct = struct
        # the two halves of a pair
        self.first = first
        self.second = second
        # minpq instead of pq
        self.minFirst = minFirst

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"CType({self.name})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CType) or self.kind != other.kind:
            return False
        match self.kind:
            case "vec":
                return self.elem == other.elem
            case "map":
                return self.key == other.key and self.value == other.value
            case "pair":
                return self.first == other.first and self.second == other.second
            case "pq":
                return self.minFirst == other.minFirst and self.elem == other.elem
        return self.name == other.name

    def __hash__(self) -> int:
        return hash(str(self))

    # region classification
    @property
    def isInteger(self) -> bool:
        return self.kind in ["int", "char"]

    @property
    def isNumeric(self) -> bool:
        return self.kind in ["int", "char", "float"]

    @property
    def isReference(self) -> bool:
        return self.kind in ["string", "vec", "map", "struct", "pq"]

    @property
    def isContainer(self) -> bool:
        # needs a real object as its default value, not zeroed memory
        return self.kind in ["vec", "map", "struct", "pq"]

    @property
    def isOrderable(self) -> bool:
        # has <, so it can be sorted, binary searched and kept in a priority queue
        if self.kind == "pair":
            return self.first.isOrderable and self.second.isOrderable
        return self.kind in ["int", "char", "float", "bool", "string"]

    @property
    def isPackableKey(self) -> bool:
        # small enough to be packed into a 64-bit map key together with another one
        return self.kind in ["int", "char", "bool"] and self.bits <= 32

    @property
    def sortKind(self) -> int | None:
        # how the runtime compares values of this type, or None if they can't be sorted
        if self.kind == "int":
            return SORT_SIGNED if self.signed else SORT_UNSIGNED
        if self.kind in ["char", "bool"]:
            return SORT_UNSIGNED
        if self.kind == "float":
            return SORT_DOUBLE
        if self.kind == "string":
            return SORT_STRING
        return None
    # endregion


class StructInfo:
    def __init__(self, name: str, irType: ir.IdentifiedStructType) -> None:
        self.name = name
        self.irType = irType
        self.fields: list[tuple[str, CType]] = []
        self.fieldsResolved: bool = False

    def fieldIndex(self, name: str) -> int | None:
        for index, (fieldName, _) in enumerate(self.fields):
            if fieldName == name:
                return index
        return None


IT = CType("int", "it", ir.IntType(32), 32, True)
LL = CType("int", "ll", ir.IntType(64), 64, True)
UI = CType("int", "ui", ir.IntType(32), 32, False)
ULL = CType("int", "ull", ir.IntType(64), 64, False)
CH = CType("char", "ch", ir.IntType(8), 8, False)
DU = CType("float", "du", ir.DoubleType(), 64)
BO = CType("bool", "bo", ir.IntType(1), 1)
ST = CType("string", "st", BYTE_POINTER)
VO = CType("void", "vo", ir.VoidType())
NIL = CType("nil", "nil", BYTE_POINTER)

PRIMITIVES: dict[str, CType] = {
    "it": IT, "int": IT,
    "ll": LL, "long": LL,
    "ui": UI, "uint": UI,
    "ull": ULL, "ulong": ULL,
    "ch": CH, "char": CH,
    "du": DU, "double": DU,
    "bo": BO, "bool": BO,
    "st": ST, "string": ST,
    "vo": VO, "void": VO,
}


def integerFor(bits: int, signed: bool) -> CType:
    if bits <= 32:
        return IT if signed else UI
    return LL if signed else ULL
