from dataclasses import dataclass


@dataclass
class Program:
    imports: list  # [path string]
    funcs: list


@dataclass
class FuncDef:
    name: str
    params: list
    ret: str
    body: object
    line: int
    col: int


@dataclass
class Block:
    stmts: list


@dataclass
class Let:
    name: str
    mutable: bool
    ann: object
    expr: object
    line: int
    col: int


@dataclass
class Assign:
    name: str
    expr: object
    line: int
    col: int


@dataclass
class IndexAssign:
    base: object  # Index node whose base is a Var
    expr: object
    line: int
    col: int


@dataclass
class If:
    cond: object
    then: object
    els: object
    line: int
    col: int


@dataclass
class While:
    cond: object
    body: object
    line: int
    col: int


@dataclass
class For:
    name: str
    expr: object
    body: object
    line: int
    col: int


@dataclass
class Return:
    expr: object
    line: int
    col: int


@dataclass
class ExprStmt:
    expr: object
    line: int
    col: int


@dataclass
class IntLit:
    value: int
    line: int
    col: int


@dataclass
class FloatLit:
    value: float
    line: int
    col: int


@dataclass
class StrLit:
    value: str
    line: int
    col: int


@dataclass
class BoolLit:
    value: bool
    line: int
    col: int


@dataclass
class ArrayLit:
    elems: list
    line: int
    col: int


@dataclass
class Var:
    name: str
    line: int
    col: int


@dataclass
class Call:
    name: str
    args: list
    line: int
    col: int


@dataclass
class Index:
    base: object
    index: object
    line: int
    col: int


@dataclass
class Cast:
    expr: object
    target: str
    line: int
    col: int


@dataclass
class BinOp:
    op: str
    left: object
    right: object
    line: int
    col: int


@dataclass
class UnaryOp:
    op: str
    expr: object
    line: int
    col: int
