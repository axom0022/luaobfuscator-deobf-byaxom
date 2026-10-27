from . import luaparse

unk = object()

class luastr(str):
    pass

def isnum(v):
    return isinstance(v, float) or isinstance(v, int)

def numfmt(v):
    if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return repr(v)

def escstr(s):
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        elif 32 <= o < 127:
            out.append(ch)
        else:
            out.append('\\%d' % o)
    out.append('"')
    return ''.join(out)

def unparse(e):
    k = e.kind
    if k == 'num':
        return numfmt(e.val)
    if k == 'str':
        return escstr(e.val)
    if k == 'nil':
        return 'nil'
    if k == 'true':
        return 'true'
    if k == 'false':
        return 'false'
    if k == 'vararg':
        return '...'
    if k == 'name':
        return e.name
    if k == 'paren':
        return '(' + unparse(e.expr) + ')'
    if k == 'index':
        if e.key.kind == 'str' and e.key.val.replace('_', 'a').isalnum() and e.key.val.isidentifier():
            return unparse(e.obj) + '.' + e.key.val
        return unparse(e.obj) + '[' + unparse(e.key) + ']'
    if k == 'call':
        inner = unparse(e.func)
        if getattr(e, 'method', None):
            return inner + '(' + ','.join(unparse(a) for a in e.args) + ')'
        return inner + '(' + ','.join(unparse(a) for a in e.args) + ')'
    if k == 'table':
        parts = []
        for it in e.items:
            if it.kind == 'kv':
                parts.append('[' + unparse(it.key) + ']=' + unparse(it.val))
            else:
                parts.append(unparse(it))
        return '{' + ','.join(parts) + '}'
    if k == 'binop':
        return '(' + unparse(e.left) + e.op + unparse(e.right) + ')'
    if k == 'unop':
        return '(' + e.op + unparse(e.expr) + ')'
    if k == 'function':
        return 'function(' + ','.join(e.params) + (',...' if e.vararg else '') + ') ... end'
    return '<%s>' % k

def stmtstr(s):
    k = s.kind
    if k == 'local':
        return 'local ' + ','.join(s.names) + ('=' + ','.join(unparse(e) for e in s.exprs) if s.exprs else '')
    if k == 'assign':
        return ','.join(unparse(t) for t in s.targets) + '=' + ','.join(unparse(e) for e in s.exprs)
    if k == 'callstat':
        return unparse(s.call)
    if k == 'return':
        return 'return ' + ','.join(unparse(e) for e in s.exprs)
    if k == 'break':
        return 'break'
    if k == 'do':
        return 'do ' + '; '.join(stmtstr(x) for x in s.body) + ' end'
    if k == 'ifx':
        txt = 'if ' + unparse(s.cond) + ' then ' + '; '.join(stmtstr(x) for x in s.then)
        orelse = getattr(s, 'orelse', None)
        if orelse:
            txt += ' else ' + '; '.join(stmtstr(x) for x in orelse)
        return txt + ' end'
    if k == 'brkx':
        return 'break'
    if k == 'while':
        return 'while ' + unparse(s.cond) + ' do ' + '; '.join(stmtstr(x) for x in s.body) + ' end'
    if k == 'localfunc':
        return 'localfunc ' + s.name
    return '<%s>' % k
