from deobf.lua.luaparse import node2
from deobf.lua.luaast import unk
from deobf.lua import fold as rd

def strip(e):
    while e.kind == 'paren':
        e = e.expr
    return e

def walkall(node, out):
    if isinstance(node, node2):
        out.append(node)
        for v in node.__dict__.values():
            walkall(v, out)
    elif isinstance(node, (list, tuple)):
        for x in node:
            walkall(x, out)
    return out

def neg(e):
    return node2('unop', op='not', expr=node2('paren', expr=e))

def isnum(e):
    return isinstance(rd.constval(e, {}), float)

def candidatetests(e, names):
    e = strip(e)
    if e.kind == 'binop' and e.op in ('==', '~=', '<=', '>=', '<', '>'):
        l = strip(e.left)
        r = strip(e.right)
        if l.kind == 'name' and isnum(r):
            names[l.name] = names.get(l.name, 0) + 1
        if r.kind == 'name' and isnum(l):
            names[r.name] = names.get(r.name, 0) + 1
    if e.kind == 'binop' and e.op in ('and', 'or'):
        candidatetests(e.left, names)
        candidatetests(e.right, names)

def findispatch(body):
    best = None
    nodes = walkall(body, [])
    for n in nodes:
        if n.kind != 'while':
            continue
        c = strip(n.cond)
        if c.kind != 'true':
            continue
        names = {}
        for sub in walkall(n.body, []):
            candidatetests(sub, names)
        if not names:
            continue
        nm = max(names, key=names.get)
        if names[nm] >= 6 and (best is None or names[nm] > best[2]):
            best = (n, nm, names[nm])
    return best

def mentions(e, name):
    for n in walkall(e, []):
        if n.kind == 'name' and n.name == name:
            return True
    return False

def pickifx(flat, opname):
    for s in reversed(flat):
        if s.kind == 'ifx' and mentions(s.cond, opname):
            return s
    return None

def splitcond(e, negated, out):
    e2 = strip(e)
    cv = rd.constval(e2, {})
    if cv is not unk:
        if rd.truthy(cv) == negated:
            out.append(('unsat',))
        return
    if e2.kind == 'binop' and e2.op == 'and':
        if negated:
            lv = rd.constval(e2.left, {})
            rv = rd.constval(e2.right, {})
            if lv is not unk and rd.truthy(lv):
                splitcond(e2.right, True, out)
                return
            if rv is not unk and rd.truthy(rv):
                splitcond(e2.left, True, out)
                return
            out.append(('unknown',))
            return
        splitcond(e2.left, False, out)
        splitcond(e2.right, False, out)
        return
    if e2.kind == 'binop' and e2.op == 'or':
        lv = rd.constval(e2.left, {})
        rv = rd.constval(e2.right, {})
        if lv is not unk:
            if rd.truthy(lv):
                if negated:
                    out.append(('unsat',))
                return
            splitcond(e2.right, negated, out)
            return
        if rv is not unk:
            if rd.truthy(rv):
                if negated:
                    out.append(('unsat',))
                return
            splitcond(e2.left, negated, out)
            return
        out.append(('unknown',))
        return
    if e2.kind == 'unop' and e2.op == 'not':
        splitcond(e2.expr, not negated, out)
        return
    if e2.kind == 'binop' and e2.op in ('==', '~=', '<=', '>=', '<', '>'):
        out.append(('cmp', e2.op, e2.left, e2.right, negated))
        return
    out.append(('unknown',))

flip2 = {'<': '>', '>': '<', '<=': '>=', '>=': '<=', '==': '==', '~=': '~='}
neg2 = {'<': '>=', '>': '<=', '<=': '>', '>=': '<', '==': '~=', '~=': '=='}

def solve(constraints, opname):
    parts = []
    for c in constraints:
        splitcond(c, False, parts)
    lo, hi = 0, 4096
    eqs, nes = [], []
    for p in parts:
        if p[0] == 'unsat':
            return None
        if p[0] != 'cmp':
            return None
        unused, op, l, r, negated = p
        l = strip(l)
        r = strip(r)
        flip = False
        if l.kind == 'name' and l.name == opname:
            v = rd.constval(r, {})
        elif r.kind == 'name' and r.name == opname:
            v = rd.constval(l, {})
            flip = True
        else:
            return None
        if v is unk:
            return None
        if flip:
            op = flip2[op]
        if negated:
            op = neg2[op]
        if op == '<=':
            hi = min(hi, v)
        elif op == '>=':
            lo = max(lo, v)
        elif op == '<':
            hi = min(hi, v - 1)
        elif op == '>':
            lo = max(lo, v + 1)
        elif op == '==':
            eqs.append(v)
        elif op == '~=':
            nes.append(v)
    if hi == 4096 and lo > 0:
        hi = lo
    if eqs:
        vals = set(int(v) for v in eqs)
    elif hi < 4096:
        vals = set(range(int(lo), int(hi) + 1))
    else:
        return None
    vals = set(v for v in vals if lo <= v <= hi)
    for v in nes:
        vals.discard(int(v))
    if not vals and nes:
        vals = {max(int(lo), max(int(v) for v in nes) + 1)}
    return sorted(vals)

def leaves(root, opname):
    out = []

    def process(flat, cons):
        node = pickifx(flat, opname)
        if node is None:
            out.append((cons, flat))
            return
        walkifx(node, cons)

    def walkifx(node, cons):
        sub = cons + [node.cond]
        nxt = pickifx(node.then, opname)
        if nxt is not None:
            walkifx(nxt, sub)
        else:
            out.append((sub, node.then))
        if node.orelse:
            ocons = cons + [neg(node.cond)]
            nxt2 = pickifx(node.orelse, opname)
            if nxt2 is not None:
                walkifx(nxt2, ocons)
            else:
                out.append((ocons, node.orelse))

    flat, unused = rd.reduceblock([root], {}, soft=True)
    nxt = pickifx(flat, opname)
    if nxt is None:
        return out
    walkifx(nxt, [])
    return out
