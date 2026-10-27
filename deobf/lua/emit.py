from .luaast import numfmt, escstr

prec = {'+': 1, '-': 1, '*': 2, '/': 2, '%': 2, '^': 3, '..': 4,
        '==': 5, '~=': 5, '<': 5, '>': 5, '<=': 5, '>=': 5,
        'and': 6, 'or': 7}
word2 = {'and', 'or', 'not'}
hoist = []
counter2 = [0]

def fresh():
    name = 'f%d' % counter2[0]
    counter2[0] += 1
    hoist.append(name)
    return name

def sub(body, depth):
    return pad(block(body, depth), 1)

def decltarget(t):
    if t.kind == 'index' and getattr(t, 'method', False):
        return expr(t.obj) + ':' + t.key.val
    return expr(t)

def key(text, isname):
    if isname:
        return '.' + text
    return '[' + text + ']'

def expr(e, lvl=0):
    k = e.kind
    if k == 'num':
        return numfmt(e.val)
    if k == 'str':
        return escstr(e.val)
    if k in ('nil', 'true', 'false'):
        return k
    if k == 'vararg':
        return '...'
    if k == 'name':
        return e.name
    if k == 'paren':
        return '(' + expr(e.expr) + ')'
    if k == 'index':
        obj = expr(e.obj, 9)
        if e.key.kind == 'str' and e.key.val.isidentifier() and not e.key.val.iskeyword() if hasattr(str, 'iskeyword') else e.key.kind == 'str' and e.key.val.isidentifier():
            return obj + '.' + e.key.val
        return obj + '[' + expr(e.key) + ']'
    if k == 'call':
        args = ', '.join(expr(a) for a in e.args)
        method = getattr(e, 'method', None)
        if method and e.func.kind == 'index':
            return expr(e.func.obj, 9) + ':' + method + '(' + args + ')'
        if method:
            return expr(e.func, 9) + ':' + method + '(' + args + ')'
        return expr(e.func, 9) + '(' + args + ')'
    if k == 'table':
        parts = []
        for it in e.items:
            if it.kind == 'kv':
                if it.key.kind == 'str' and it.key.val.isidentifier():
                    parts.append(it.key.val + ' = ' + expr(it.val))
                else:
                    parts.append('[' + expr(it.key) + '] = ' + expr(it.val))
            else:
                parts.append(expr(it))
        return '{' + ', '.join(parts) + '}'
    if k == 'binop':
        p = prec.get(e.op, 1)
        left = expr(e.left, p)
        right = expr(e.right, p + 1 if e.op not in ('^', '..') else p)
        sep = ' %s ' % e.op
        text = left + sep + right
        return text if p >= lvl else '(' + text + ')'
    if k == 'unop':
        op = e.op
        inner = expr(e.expr, 8 if op == 'not' else 8)
        sep = ' ' if op in word2 else ''
        text = op + sep + inner
        return text if 8 >= lvl else '(' + text + ')'
    if k == 'function':
        name = fresh()
        funcs2[name] = e
        return name
    return 'nil'

funcs2 = {}

def params(fn):
    names = list(fn.params)
    if getattr(fn, 'vararg', False):
        names.append('...')
    return ', '.join(names)

def pad(lines, depth):
    p = '  ' * depth
    return [p + line if line else line for line in lines]

def block(body, depth):
    out = []
    for st in body:
        out.extend(stmts(st, depth))
    return out

def fnblock(fn, head, depth):
    return [head] + sub(fn.body, depth) + ['end']

def fninline(e):
    hoist.clear()
    funcs2.clear()
    text = expr(e)
    pending = []
    for name in hoist:
        pending.extend(fnblock(funcs2[name], 'local ' + name + ' = function(' + params(funcs2[name]) + ')', 0))
    return text, pending

def stmts(s, depth):
    k = s.kind
    if k == 'local':
        hoist.clear()
        funcs2.clear()
        vals = [expr(e) for e in s.exprs] if s.exprs else []
        pre = []
        for name in hoist:
            pre.extend(fnblock(funcs2[name], 'local ' + name + ' = function(' + params(funcs2[name]) + ')', depth))
        if not vals:
            return pre + ['local ' + ', '.join(s.names)]
        return pre + ['local ' + ', '.join(s.names) + ' = ' + ', '.join(vals)]
    if k == 'localfunc':
        return fnblock(s.func, 'local function ' + s.name + '(' + params(s.func) + ')', depth)
    if k == 'assign':
        if len(s.exprs) == 1 and s.exprs[0].kind == 'function':
            fn = s.exprs[0]
            methods = [t for t in s.targets if t.kind == 'index' and getattr(t, 'method', False)]
            if methods and len(s.targets) == 1:
                head = 'function ' + decltarget(s.targets[0]) + '(' + params(fn) + ')'
                return fnblock(fn, head, depth)
            return fnblock(fn, ', '.join(decltarget(t) for t in s.targets) + ' = function(' + params(fn) + ')', depth)
        hoist.clear()
        funcs2.clear()
        vals = [expr(e) for e in s.exprs]
        pre = []
        for name in hoist:
            pre.extend(fnblock(funcs2[name], 'local ' + name + ' = function(' + params(funcs2[name]) + ')', depth))
        return pre + [', '.join(expr(t) for t in s.targets) + ' = ' + ', '.join(vals)]
    if k == 'callstat':
        hoist.clear()
        funcs2.clear()
        text = expr(s.call)
        pre = []
        for name in hoist:
            pre.extend(fnblock(funcs2[name], 'local ' + name + ' = function(' + params(funcs2[name]) + ')', depth))
        return pre + [text]
    if k == 'return':
        hoist.clear()
        funcs2.clear()
        vals = [expr(e) for e in s.exprs] if s.exprs else []
        pre = []
        for name in hoist:
            pre.extend(fnblock(funcs2[name], 'local ' + name + ' = function(' + params(funcs2[name]) + ')', depth))
        return pre + (['return ' + ', '.join(vals)] if vals else ['return'])
    if k == 'break':
        return ['break']
    if k == 'label':
        return ['::' + s.name + '::']
    if k == 'do':
        return ['do'] + sub(s.body, depth) + ['end']
    if k == 'while':
        return ['while ' + expr(s.cond) + ' do'] + sub(s.body, depth) + ['end']
    if k == 'repeat':
        return ['repeat'] + sub(s.body, depth) + ['until ' + expr(s.cond)]
    if k == 'fornum':
        head = 'for %s = %s, %s' % (s.var, expr(s.start), expr(s.stop))
        if getattr(s, 'step', None) is not None:
            head += ', ' + expr(s.step)
        return [head + ' do'] + sub(s.body, depth) + ['end']
    if k == 'forin':
        head = 'for ' + ', '.join(s.names) + ' in ' + ', '.join(expr(e) for e in s.exprs)
        return [head + ' do'] + sub(s.body, depth) + ['end']
    if k in ('if', 'ifx'):
        if k == 'if':
            clauses = list(s.clauses)
            orelse = getattr(s, 'orelse', None)
        else:
            clauses = [(s.cond, s.then)]
            orelse = getattr(s, 'orelse', None)
        out = []
        for i, (cond, body) in enumerate(clauses):
            out.append(('if ' if i == 0 else 'elseif ') + expr(cond) + ' then')
            out.extend(sub(body, depth))
        if orelse:
            out.append('else')
            out.extend(sub(orelse, depth))
        out.append('end')
        return out
    return ['-- ' + k]

def render(body):
    return '\n'.join(block(body, 0))
