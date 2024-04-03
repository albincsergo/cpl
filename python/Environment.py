from llvmlite import ir

class Environment:
    def __init__(self, records: dict[str, tuple[ir.Value, ir.Type]] = None, parent = None, name: str = "global") -> None:
        self.records: dict[str, tuple[ir.Value, ir.Type]] = records if records else {}
        self.parent: Environment | None = parent
        self.name: str = name

    def define(self, name: str, value: ir.Value, Type: ir.Type) -> None:
        self.records[name] = (value, Type)
        return value
    
    def resolve(self, name: str) -> tuple[ir.Value, ir.Type]:
        if name in self.records:
            return self.records[name]
        elif self.parent:
            return self.parent.resolve(name)
        else:
            return None
        
    def lookup(self, name: str) -> tuple[ir.Value, ir.Type]:
        return self.resolve(name)