from . import luaparse
from .luaparse import node2
from .luaast import unk, unparse, stmtstr

class env2(dict):
    pass

def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if isinstance(v, int) else v
    return None

def constval(e, env):
    k = e.kind
    if k == 'num':
        return e.val
    if k == 'str':
        return e.val
    if k == 'true':
        return True
    if k == 'false':
        return False
    if k == 'nil':
        return None
    if k == 'name':
        return env.get(e.name, unk)
    if k == 'paren':
        return constval(e.expr, env)
    if k == 'unop':
        v = constval(e.expr, env)
        if v is unk:
            return unk
        if e.op == '-':
            n = num(v)
            return unk if n is None else -n
        if e.op == '#':
            if isinstance(v, str):
                return float(len(v))
            return unk
        if e.op == 'not':
            return not truthy(v)
        return unk
    if k == 'binop':
        if e.op == 'and':
            lv = constval(e.left, env)
            if lv is unk:
                return unk
            return constval(e.right, env) if truthy(lv) else lv
        if e.op == 'or':
            lv = constval(e.left, env)
            if lv is unk:
                return unk
            return lv if truthy(lv) else constval(e.right, env)
        lv = constval(e.left, env)
        rv = constval(e.right, env)
        if lv is unk or rv is unk:
            return unk
        ln = num(lv)
        rn = num(rv)
        op = e.op
        if op in ('==', '~='):
            if (ln is None) != (rn is None) and not (isinstance(lv, str) and isinstance(rv, str)):
                if (ln is not None or rn is not None) and not (isinstance(lv, bool) or isinstance(rv, bool)):
                    return unk
            eq = lv == rv
            return eq if op == '==' else (not eq)
        if op in ('<', '>', '<=', '>='):
            if ln is None or rn is None:
                return unk
            return {'<': ln < rn, '>': ln > rn, '<=': ln <= rn, '>=': ln >= rn}[op]
        if op == '..':
            if isinstance(lv, str) and isinstance(rv, str):
                return lv + rv
            return unk
        if ln is None or rn is None:
            return unk
        try:
            if op == '+':
                return ln + rn
            if op == '-':
                return ln - rn
            if op == '*':
                return ln * rn
            if op == '/':
                return ln / rn
            if op == '%':
                return float(int(ln) % int(rn)) if rn else unk
            if op == '^':
                return float(ln) ** rn
        except Exception:
            return unk
        return unk
    if k == 'call':
        fn = e.func
        if fn.kind == 'paren':
            fn = fn.expr
        if fn.kind == 'function' and not e.args:
            body = fn.body
            if len(body) == 1 and body[0].kind == 'return' and len(body[0].exprs) == 1:
                return constval(body[0].exprs[0], env)
            if len(body) == 1 and body[0].kind == 'return' and not body[0].exprs:
                return None
            if not body:
                return None
        return unk
    return unk

def truthy(v):
    return not (v is None or v is False)

def mkconst(v):
    if v is None:
        return node2('nil')
    if v is True:
        return node2('true')
    if v is False:
        return node2('false')
    if isinstance(v, str):
        return node2('str', val=v)
    return node2('num', val=float(v))

def resolve(e, env):
    v = constval(e, env)
    if v is not unk:
        return mkconst(v)
    k = e.kind
    if k == 'paren':
        return resolve(e.expr, env)
    if k == 'unop':
        return node2('unop', op=e.op, expr=resolve(e.expr, env))
    if k == 'binop':
        return node2('binop', op=e.op, left=resolve(e.left, env), right=resolve(e.right, env))
    if k == 'index':
        return node2('index', obj=resolve(e.obj, env), key=resolve(e.key, env))
    if k == 'call':
        fn = resolve(e.func, env)
        if fn.kind == 'function' and not e.args and len(fn.body) == 1 and fn.body[0].kind == 'return':
            if len(fn.body[0].exprs) == 1:
                return resolve(fn.body[0].exprs[0], env)
        return node2('call', func=fn, args=[resolve(a, env) for a in e.args], method=getattr(e, 'method', None))
    if k == 'table':
        return node2('table', items=[resolve(it.key, env) if False else it for it in e.items])
    return e

maxloop = 64

def reduceblock(stmts, env, depth=0, soft=False):
    out = []
    brk = False
    for s in stmts:
        if brk:
            break
        k = s.kind
        if k == 'local':
            vals = []
            for e in s.exprs:
                cv = constval(e, env)
                vals.append(cv)
            for i, nm in enumerate(s.names):
                cv = vals[i] if i < len(vals) else None
                if i < len(vals) and cv is not unk:
                    env[nm] = cv
                else:
                    env.pop(nm, None)
                    if i < len(s.exprs):
                        out.append(node2('local', names=[nm], exprs=[resolve(s.exprs[i], env)]))
        elif k == 'assign':
            exprs = [resolve(e, env) for e in s.exprs]
            cvs = [constval(e, env) for e in s.exprs]
            for i, t in enumerate(s.targets):
                cv = cvs[i] if i < len(cvs) else None
                if t.kind == 'name' and i < len(cvs) and cv is not unk:
                    env[t.name] = cv
                    continue
                if t.kind == 'name' and i < len(cvs) and cv is unk:
                    env.pop(t.name, None)
            if any(t.kind != 'name' or (i < len(cvs) and cvs[i] is unk) for i, t in enumerate(s.targets)):
                keept = [resolve(t, env) for i, t in enumerate(s.targets) if t.kind != 'name' or (i < len(cvs) and cvs[i] is unk)]
                keepe = []
                idx = 0
                for i, t in enumerate(s.targets):
                    if t.kind != 'name' or (i < len(cvs) and cvs[i] is unk):
                        keepe.append(exprs[i] if i < len(exprs) else node2('nil'))
                out.append(node2('assign', targets=keept, exprs=keepe))
        elif k == 'callstat':
            out.append(node2('callstat', call=resolve(s.call, env)))
        elif k == 'return':
            out.append(node2('return', exprs=[resolve(e, env) for e in s.exprs]))
            brk = not soft
            if soft:
                continue
        elif k == 'break':
            brk = not soft
            out.append(node2('brkx'))
            if not soft:
                break
        elif k == 'do':
            sub, b2 = reduceblock(s.body, env, depth + 1)
            out.extend(sub)
            if b2:
                brk = True
                break
        elif k == 'if':
            picked = None
            for i, (cond, body) in enumerate(s.clauses):
                cv = constval(cond, env)
                if cv is unk:
                    picked = i
                    break
                if truthy(cv):
                    sub, b2 = reduceblock(body, env, depth + 1, soft)
                    out.extend(sub)
                    if b2:
                        return out, True
                    picked = -1
                    break
            if picked == -1:
                continue
            if picked is None:
                if s.orelse:
                    sub, b2 = reduceblock(s.orelse, env, depth + 1, soft)
                    out.extend(sub)
                    if b2:
                        return out, True
                continue
            node = node2('ifx', cond=resolve(s.clauses[picked][0], env),
                        then=reduceblock(s.clauses[picked][1], dict(env), depth + 1)[0],
                        orelse=None)
            rest = s.clauses[picked + 1:]
            if rest:
                chain = node2('if', clauses=rest, orelse=s.orelse)
                node.orelse = reduceblock([chain], env, depth + 1, soft)[0]
            elif s.orelse:
                node.orelse = reduceblock(s.orelse, env, depth + 1, soft)[0]
            out.append(node)
        elif k == 'while':
            cv = constval(s.cond, env)
            if cv is not unk and not truthy(cv):
                continue
            broke = False
            for unused in range(6):
                nenv = dict(env)
                sub, b2 = reduceblock(s.body, nenv, depth + 1, soft)
                out.extend(sub)
                changed = any(nenv.get(k2) != env.get(k2) for k2 in nenv)
                env.update(nenv)
                if b2:
                    broke = True
                    break
                if not changed:
                    break
            else:
                out.append(node2('while', cond=s.cond, body=s.body))
            if not broke and constval(s.cond, env) is unk:
                pass
        elif k == 'repeat':
            sub, b2 = reduceblock(s.body, dict(env), depth + 1)
            out.extend(sub)
            if b2:
                brk = True
                break
        elif k == 'localfunc':
            out.append(node2('local', names=[s.name], exprs=[s.func]))
            env.pop(s.name, None)
        elif k == 'fornum' or k == 'forin':
            node = node2(s.kind, **{f: getattr(s, f) for f in ('var', 'start', 'stop', 'step', 'names', 'exprs') if hasattr(s, f)})
            node.body = s.body
            out.append(node)
        elif k == 'label':
            out.append(s)
    return out, brk

if __name__ == '__main__':
    import sys
    src = open(sys.argv[1], encoding='utf-8', errors='replace').read()
    body = luaparse.parse(src)
    flat, b = reduceblock(body, {})
    for s in flat:
        print(stmtstr(s))
