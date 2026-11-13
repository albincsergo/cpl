import llvmlite.binding as llvm


_initialized: bool = False


def initializeLLVM() -> None:
    global _initialized
    if _initialized:
        return
    # newer llvmlite versions initialize LLVM automatically and raise if this is called
    try:
        llvm.initialize()
    except RuntimeError:
        pass
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    _initialized = True


def targetMachine(optLevel: int = 2) -> llvm.TargetMachine:
    initializeLLVM()
    return llvm.Target.from_default_triple().create_target_machine(opt=optLevel, reloc="pic", codemodel="default")
