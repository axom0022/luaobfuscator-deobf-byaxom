import re
from deobf.lua import luaparse
from deobf.lua import fold
from . import dispatch
from deobf.lua.luaparse import node2

core2 = {'R': 1, 'pc': 1, 'TOP': 1, 'I': 1, 'G': 1, 'OP': 1}
words = ('local', 'then', 'else', 'elseif', 'end', 'if', 'for', 'do', 'in', 'return',
         'break', 'and', 'or', 'not', 'nil', 'true', 'false', 'function', 'while', 'repeat', 'until')

def strip(e):
    while e.kind == 'paren':
        e = e.expr
    return e

def assigned(stmts):
    out = {}
    for s in stmts:
        if s.kind == 'assign':
            for t in s.targets:
                if t.kind == 'name':
                    out[t.name] = out.get(t.name, 0) + 1
        elif s.kind == 'local':
            for nm in s.names:
                out[nm] = out.get(nm, 0) + 1
        elif s.kind == 'ifx':
            for k, v in assigned(s.then).items():
                out[k] = out.get(k, 0) + v
            if getattr(s, 'orelse', None):
                for k, v in assigned(s.orelse).items():
                    out[k] = out.get(k, 0) + v
    return out

def used(stmts):
    out = {}
    for s in stmts:
        for n in dispatch.walkall(s, []):
            if n.kind == 'name':
                out[n.name] = out.get(n.name, 0) + 1
    return out

def subst(e, mapping):
    if isinstance(e, node2):
        for k, v in list(e.__dict__.items()):
            if isinstance(v, node2):
                if v.kind == 'name' and v.name in mapping:
                    setattr(e, k, mapping[v.name])
                else:
                    e.__dict__[k] = subst(v, mapping)
            elif isinstance(v, (list, tuple)):
                setattr(e, k, subst(v, mapping))
        return e
    if isinstance(e, list):
        return [subst(x, mapping) for x in e]
    if isinstance(e, tuple):
        return tuple(subst(x, mapping) for x in e)
    return e

def inline(stmts, keep):
    stmts = list(stmts)
    for unused in range(24):
        counts = assigned(stmts)
        uses = used(stmts)
        done = True
        for i, s in enumerate(stmts):
            nm = None
            val = None
            if s.kind == 'local' and len(s.names) == 1 and len(s.exprs) == 1:
                nm, val = s.names[0], s.exprs[0]
            elif s.kind == 'assign' and len(s.targets) == 1 and len(s.exprs) == 1 and s.targets[0].kind == 'name':
                nm, val = s.targets[0].name, s.exprs[0]
            if nm is None or nm in keep:
                continue
            if counts.get(nm, 0) != 1 or uses.get(nm, 0) != 1:
                continue
            stmts = stmts[:i] + stmts[i + 1:]
            stmts = subst(stmts, {nm: val})
            done = False
            break
        if done:
            break
    return stmts

def text(e, roles):
    k = e.kind
    if k == 'name':
        return roles.get(e.name, e.name)
    if k == 'num':
        return str(int(e.val)) if e.val == int(e.val) else repr(e.val)
    if k == 'str':
        return '"' + e.val.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if k in ('nil', 'true', 'false'):
        return k
    if k == 'index':
        return text(e.obj, roles) + '[' + text(e.key, roles) + ']'
    if k == 'call':
        return text(e.func, roles) + '(' + ','.join(text(a, roles) for a in e.args) + ')'
    if k == 'binop':
        return '(' + text(e.left, roles) + e.op + text(e.right, roles) + ')'
    if k == 'unop':
        return '(' + e.op + ' ' + text(e.expr, roles) + ')'
    if k == 'table':
        return '{}' if not e.items else '{' + ','.join('e' for unused in e.items) + '}'
    if k == 'paren':
        return text(e.expr, roles)
    if k == 'function':
        return 'F'
    return 'q'

def stext(s, roles):
    k = s.kind
    if k == 'local':
        return 'local ' + ','.join(roles.get(n, n) for n in s.names) + '=' + ','.join(text(e, roles) for e in s.exprs)
    if k == 'assign':
        return ','.join(text(t, roles) for t in s.targets) + '=' + ','.join(text(e, roles) for e in s.exprs)
    if k == 'callstat':
        return text(s.call, roles)
    if k == 'return':
        return 'return ' + ','.join(text(e, roles) for e in s.exprs)
    if k == 'brkx':
        return 'break'
    if k == 'ifx':
        out = 'if ' + text(s.cond, roles) + ' then ' + ';'.join(stext(x, roles) for x in s.then)
        if getattr(s, 'orelse', None):
            out += ' else ' + ';'.join(stext(x, roles) for x in s.orelse)
        return out + ' end'
    if k == 'fornum':
        step = ',' + text(s.step, roles) if s.step is not None else ''
        return 'for ' + roles.get(s.var, s.var) + '=' + text(s.start, roles) + ',' + text(s.stop, roles) + step + ' do ' + ';'.join(stext(x, roles) for x in s.body) + ' end'
    if k == 'forin':
        return 'forin ' + ','.join(s.names) + ' do ... end'
    if k == 'while':
        return 'while ' + text(s.cond, roles) + ' do ... end'
    return 'q'

def arith(t):
    def num(m):
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        if op == '+':
            return str(a + b)
        if op == '-':
            return str(a - b)
        if op == '*':
            return str(a * b)
        if op == '%' and b:
            return str(a % b)
        return m.group(0)
    for unused in range(24):
        before = t
        t = re.sub(r'\((\d+)([+\-*%])(\d+)\)', num, t)
        t = re.sub(r'\(((?:X|R|I|G|TOP|pc|A|B|C|\d|[+\-*%\[\]()])+)\+0\)', r'(\1)', t)
        t = re.sub(r'\(0\+((?:X|R|I|G|TOP|pc|A|B|C|\d|[+\-*%\[\]()])+)\)', r'(\1)', t)
        t = re.sub(r'\(\(([A-Za-z0-9_\[\]]+)\+(\d+)\)\+(\d+)\)', lambda m: '(%s+%d)' % (m.group(1), int(m.group(2)) + int(m.group(3))), t)
        t = re.sub(r'\(([^()]*)\)', lambda m: m.group(0) if '(' in m.group(1) else m.group(0), t)
        t = re.sub(r'\(\(([^()]*)\)\)', r'(\1)', t)
        if t == before:
            break
    return t

def canon(stmts, roles, keep):
    stmts = inline(stmts, keep)
    raw = ' ;; '.join(stext(s, roles) for s in stmts)
    raw = raw.replace('I[2]', 'A').replace('I[3]', 'B').replace('I[4]', 'C')
    temp = {}
    out = []
    i = 0
    pattern = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
    while i < len(raw):
        m = pattern.match(raw, i)
        if m:
            word = m.group(0)
            if word in core2 or word in words:
                out.append(word)
            else:
                out.append('X')
            i += len(word)
            continue
        out.append(raw[i])
        i += 1
    return arith(re.sub(r'\s+', ' ', ''.join(out)).strip())

def helperroles(leaves, core):
    found = {}
    for op, sts in leaves.items():
        for s in sts:
            for n in dispatch.walkall(s, []):
                if n.kind != 'call':
                    continue
                fn = strip(n.func)
                if fn.kind != 'name' or fn.name in core:
                    continue
                args = n.args
                if len(args) == 3:
                    a0 = strip(args[0])
                    if a0.kind == 'name' and a0.name == core.get('R'):
                        found.setdefault(fn.name, 'U')
                    elif a0.kind == 'index':
                        found.setdefault(fn.name, 'C')
                elif len(args) == 2:
                    a0, a1 = strip(args[0]), strip(args[1])
                    if a0.kind == 'table' and a1.kind == 'table':
                        found.setdefault(fn.name, 'M')
                    elif a0.kind == 'name' and a1.kind == 'index':
                        found.setdefault(fn.name, 'N')
                elif len(args) == 1 and strip(args[0]).kind == 'call':
                    found.setdefault(fn.name, 'K')
    return found

def tables(leaves, iv):
    found = {}
    for op, sts in leaves.items():
        for s in sts:
            for n in dispatch.walkall(s, []):
                if n.kind == 'index':
                    obj = strip(n.obj)
                    key = strip(n.key)
                    if obj.kind == 'name' and key.kind == 'index':
                        inner = strip(key.obj)
                        ikey = strip(key.key)
                        if inner.kind == 'name' and inner.name == iv and ikey.kind == 'num':
                            found.setdefault(obj.name, 'G')
    return found

def findopvar(wh):
    names = {}
    for sub in dispatch.walkall(wh.body, []):
        dispatch.candidatetests(sub, names)
    if not names:
        return None
    return max(names, key=names.get)

def analyze(src):
    body = luaparse.parse(src)
    wh, opvar, cnt = dispatch.findispatch(body)
    if wh is None:
        return None
    idx = [i for i, s in enumerate(wh.body) if s.kind == 'if'][0]
    raw = dispatch.leaves(wh.body[idx], opvar)
    leaves = {}
    for cons, sts in raw:
        for v in (dispatch.solve(cons, opvar) or []):
            leaves[int(v)] = sts
    iv = None
    for s in wh.body:
        if s.kind == 'assign' and s.targets[0].kind == 'name' and s.targets[0].name == opvar:
            e = strip(s.exprs[0])
            if e.kind == 'index':
                iv = strip(e.obj).name
    counts = {}
    for op, sts in leaves.items():
        for n in dispatch.walkall(sts, []):
            if n.kind == 'index':
                obj = strip(n.obj)
                key = strip(n.key)
                if obj.kind == 'name' and key.kind == 'index':
                    inner = strip(key.obj)
                    ikey = strip(key.key)
                    if inner.kind == 'name' and inner.name == iv and ikey.kind == 'num' and ikey.val == 2:
                        counts[obj.name] = counts.get(obj.name, 0) + 1
    regs = max(counts, key=counts.get) if counts else None
    core = {'R': regs, 'I': iv}
    pcwrites = {}
    for op, sts in leaves.items():
        for s in sts:
            if s.kind == 'assign' and len(s.targets) == 1 and s.targets[0].kind == 'name':
                e = strip(s.exprs[0])
                if e.kind == 'index':
                    obj = strip(e.obj)
                    key = strip(e.key)
                    if obj.kind == 'name' and obj.name == iv and key.kind == 'num' and key.val == 3:
                        nm = s.targets[0].name
                        pcwrites[nm] = pcwrites.get(nm, 0) + 1
    pc = max(pcwrites, key=pcwrites.get) if pcwrites else None
    if pc is None:
        for s in reversed(wh.body):
            if s.kind == 'assign' and s.targets[0].kind == 'name':
                e = strip(s.exprs[0])
                if e.kind == 'binop' and e.op == '+':
                    l = strip(e.left)
                    if l.kind == 'name' and l.name == s.targets[0].name:
                        pc = s.targets[0].name
                        break
    core['pc'] = pc
    tcounts = {}
    for op, sts in leaves.items():
        for n in dispatch.walkall(sts, []):
            if n.kind == 'call' and len(n.args) == 3:
                a0, a2 = strip(n.args[0]), strip(n.args[2])
                if a0.kind == 'name' and a0.name == regs and a2.kind == 'name':
                    tcounts[a2.name] = tcounts.get(a2.name, 0) + 1
    top = max(tcounts, key=tcounts.get) if tcounts else None
    core['TOP'] = top
    roles = {}
    for tok, nm in core.items():
        if nm:
            roles[nm] = tok
    for nm, tok in tables(leaves, iv).items():
        roles.setdefault(nm, 'G')
    for nm, tok in helperroles(leaves, core).items():
        roles.setdefault(nm, tok)
    return {'leaves': leaves, 'roles': roles, 'core': core, 'body': body}
