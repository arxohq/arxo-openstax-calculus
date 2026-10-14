"""Input syntax and serialization only; no mathematical answer generation.

Adapted from the retained native limit-solver parser. Numeric Fraction is used
only to serialize a literal. DAG deduplication is structural. A fixed carrier
pool names polynomial nodes; the Arxo models calculate all coefficients.
"""
from fractions import Fraction
import re,json
FUNCTIONS = ("sin", "cos", "exp", "ln", "sqrt")


class ParseError(Exception):
    pass


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c.isdigit() or (c == "." and i + 1 < len(text) and text[i + 1].isdigit()):
            j = i
            while j < len(text) and (text[j].isdigit() or text[j] == "."):
                j += 1
            if j < len(text) and text[j] == "/" and j + 1 < len(text) and text[j+1].isdigit():
                j += 1
                while j < len(text) and text[j].isdigit():
                    j += 1
            out.append(text[i:j])
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < len(text) and (text[j].isalnum() or text[j] == "_"):
                j += 1
            out.append(text[i:j])
            i = j
            continue
        if c in "+-*/^()":
            out.append(c)
            i += 1
            continue
        raise ParseError(f"недопустимый символ {c!r} в позиции {i}")
    return out


class Parser:
    """Рекурсивный спуск по объявленной грамматике §7 DECISION-0198."""

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> str:
        tok = self.peek()
        if tok is None:
            raise ParseError("запись оборвана")
        self.pos += 1
        return tok

    def expect(self, tok: str) -> None:
        got = self.take()
        if got != tok:
            raise ParseError(f"ожидалось {tok!r}, встретилось {got!r}")

    def parse(self):
        node = self.expr()
        if self.peek() is not None:
            raise ParseError(f"лишний текст с {self.peek()!r}")
        return node

    def expr(self):
        node = self.term()
        while self.peek() in ("+", "-"):
            op = self.take()
            node = ("add" if op == "+" else "sub", node, self.term())
        return node

    def term(self):
        node = self.factor()
        while self.peek() in ("*", "/"):
            op = self.take()
            node = ("mul" if op == "*" else "div", node, self.factor())
        return node

    def factor(self):
        if self.peek() == "-":
            self.take()
            return ("neg", self.factor())
        node = self.atom()
        if self.peek() == "^":
            self.take()
            exponent = self.take()
            if not re.fullmatch(r"\d+", exponent):
                raise ParseError("exponent must be a nonnegative integer")
            node = ("pow", node, ("const", Fraction(int(exponent))))
        return node

    def atom(self):
        tok = self.take()
        if tok == "(":
            node = self.expr()
            self.expect(")")
            return node
        if re.fullmatch(r"\d+(\.\d+)?(?:/\d+)?", tok):
            return ("const", Fraction(tok))
        if re.fullmatch(r"[A-Za-z_]\w*", tok):
            if tok in FUNCTIONS:
                self.expect("(")
                arg = self.expr()
                self.expect(")")
                return (tok, arg)
            return ("var", tok)
        raise ParseError(f"неожиданный знак {tok!r}")


REQUEST = re.compile(
    r"^\s*lim\s+([A-Za-z_]\w*)\s*->\s*([^\s]+)\s+(.*)$", re.DOTALL)


def parse_request(text: str) -> tuple[str, str, Fraction, str, tuple]:
    m = REQUEST.match(text)
    if not m:
        raise ParseError(
            "ожидается запись вида `lim x->1 (x^2-1)/(x-1)`; "
            "точка — рациональное число с необязательным знаком стороны + либо −, "
            "либо +inf / -inf")
    variable, point, body = m.group(1), m.group(2), m.group(3)
    side = "both"
    if point in ("+inf", "inf", "+infinity"):
        approach, value = "plus_inf", Fraction(0)
    elif point in ("-inf", "-infinity"):
        approach, value = "minus_inf", Fraction(0)
    else:
        approach = "at"
        if point.endswith("+"):
            side, point = "right", point[:-1]
        elif point.endswith("-") and len(point) > 1 and not point[:-1].endswith("-"):
            side, point = "left", point[:-1]
        try:
            value = Fraction(point)
        except ValueError as exc:
            raise ParseError(f"точка {point!r} не является рациональным числом") from exc
    tree = Parser(tokenize(body)).parse()
    return variable, approach, value, side, tree


# ── Дерево в узлы ──────────────────────────────────────────────────────────

def flatten(tree) -> tuple[list[tuple], int]:
    """Пронумеровать узлы 1 … N в порядке обхода, разделяя одинаковые поддеревья.

    Разделение СТРУКТУРНОЕ и синтаксическое: одинаковая запись получает один
    номер. Никакого упрощения здесь нет — `x + 0` и `x` остаются разными.
    """
    nodes: list[tuple] = []
    index: dict[tuple, int] = {}

    def visit(node) -> int:
        tag = node[0]
        if tag == "const":
            key = ("const", "", str(node[1]), 0, 0)
        elif tag == "var":
            key = ("var", node[1], "0", 0, 0)
        elif tag in ("neg", "sin", "cos", "exp", "ln", "sqrt"):
            key = (tag, "", "0", visit(node[1]), 0)
        elif tag == "pow":
            key = (tag, "", "0", visit(node[1]), visit(node[2]))
        else:
            key = (tag, "", "0", visit(node[1]), visit(node[2]))
        if key in index:
            return index[key]
        ident = len(nodes) + 1
        index[key] = ident
        nodes.append((ident,) + key)
        return ident

    root = visit(tree)
    return nodes, root




def expression_nodes(text):
    return flatten(Parser(tokenize(text)).parse())

def _ref(urn):return 'entity_ref('+json.dumps(urn)+')'
def _r(value):
    q=Fraction(value);return str(q.numerator)+' / '+str(q.denominator)
def case_body(operation,text,variable='x',point='0',approach='at',side='both',constant='0',bounds=None,cap=32):
    nodes,root=expression_nodes(text);task=_ref('urn:example:calculus:task');e=_ref('urn:example:calculus:nodes');lines=[]
    def fact(call):lines.append('assert "input-'+str(len(lines)+1)+'": '+call+' { origin case_input; }')
    if operation=='limit':
        pkg='openstax.calculus_limits';base='calc.limit_solver::'
        fact(pkg+'::automatic_limit_task('+task+')')
        for pred,arg in [('task_nodes',e),('task_function',str(root)),('task_variable',json.dumps(variable)),('task_approach',json.dumps(approach)),('task_point',_r(point)),('task_side',json.dumps(side))]:fact(base+pred+'('+task+','+arg+')')
        for ident,tag,name,value,left,right in nodes:fact(base+'input_node('+','.join([task,str(ident),json.dumps(tag),json.dumps(name),_r(value),str(left),str(right)])+')')
        fact(base+'task_closed('+task+')')
    else:
        pkg='openstax.calculus_derivatives' if operation=='differentiate' else 'openstax.calculus_integrals';result=_ref('urn:example:calculus:result')
        for ident,tag,name,value,left,right in nodes:fact('calc.expressions::node('+','.join([e,str(ident),json.dumps(tag),json.dumps(name),_r(value),str(left),str(right)])+')')
        fact('calc.expressions::closed('+e+')');fact('calc.polynomials_q::polynomial_variable('+e+','+json.dumps(variable)+')');fact('calc.polynomials_q::degree_cap('+str(cap)+')')
        # The same 255 carrier identities for every request; no contents/answers.
        for ident in range(1,256):fact('calc.polynomials_q::node_polynomial('+e+','+str(ident)+','+_ref('urn:example:calculus:carrier/'+str(ident))+')')
        fact(pkg+'::polynomial_task('+','.join([task,e,str(root),json.dumps(variable),result])+')')
        if operation!='differentiate':
            fact(pkg+'::integration_constant('+task+','+_r(constant)+')')
            if bounds is not None:fact(pkg+'::integration_bounds('+task+','+_r(bounds[0])+','+_r(bounds[1])+')')
    return pkg,lines

def source_case(operation,text,**options):
    pkg,lines=case_body(operation,text,**options)
    return 'language "law.core" version "0.2";\npackage examples.calculus_input version "0.1.0";\nnamespace "urn:example:calculus:input";\ncase Problem {\n context { legal_time @2026-10-14; knowledge_time @2026-10-14T12:00:00Z; decision_time @2026-10-14T12:00:00Z; timezone "UTC"; }\n'+ '\n'.join(' '+line for line in lines)+'\n}\n',pkg
