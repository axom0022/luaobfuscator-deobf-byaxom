import re

class node2:
    def __init__(self, kind, **kw):
        self.kind = kind
        self.__dict__.update(kw)

    def __repr__(self):
        return 'node(' + self.kind + ')'

keywords = {
    'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for', 'function',
    'if', 'in', 'local', 'nil', 'not', 'or', 'repeat', 'return', 'then',
    'true', 'until', 'while',
}

ops = ['...', '..', '==', '~=', '<=', '>=', '<<', '>>', '//', '::',
       '+', '-', '*', '/', '%', '^', '#', '<', '>', '=', '(', ')', '{', '}',
       '[', ']', ';', ':', ',', '.']

esc = {'a': '\a', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t',
       'v': '\v', '\\': '\\', '"': '"', "'": "'", '\n': '\n'}

class tok2:
    def __init__(self, kind, val, pos):
        self.kind = kind
        self.val = val
        self.pos = pos

    def __repr__(self):
        return 'Tok(%s,%r)' % (self.kind, self.val)

def lex(src):
    i = 0
    n = len(src)
    out = []
    while i < n:
        c = src[i]
        if c in ' \t\r\n':
            i += 1
            continue
        if c == '-' and src.startswith('--', i):
            i += 2
            if src.startswith('[', i):
                m = re.match(r'\[(=*)\[', src[i:])
                if m:
                    close = ']' + m.group(1) + ']'
                    j = src.find(close, i + len(m.group(0)))
                    i = n if j < 0 else j + len(close)
                    continue
            j = src.find('\n', i)
            i = n if j < 0 else j + 1
            continue
        if c == '[':
            m = re.match(r'\[(=*)\[', src[i:])
            if m:
                close = ']' + m.group(1) + ']'
                start = i + len(m.group(0))
                j = src.find(close, start)
                if j < 0:
                    j = n
                val = src[start:j]
                if val.startswith('\n'):
                    val = val[1:]
                out.append(tok2('str', val, i))
                i = j + len(close)
                continue
        if c in '"\'':
            q = c
            i += 1
            buf = []
            while i < n:
                ch = src[i]
                if ch == '\\':
                    i += 1
                    if i >= n:
                        break
                    e = src[i]
                    if e.isdigit():
                        d = ''
                        while i < n and len(d) < 3 and src[i].isdigit():
                            d += src[i]
                            i += 1
                        buf.append(chr(int(d) % 256))
                        continue
                    if e == 'x':
                        h = src[i + 1:i + 3]
                        if re.fullmatch(r'[0-9a-fA-F]{2}', h or ''):
                            buf.append(chr(int(h, 16)))
                            i += 3
                            continue
                    buf.append(esc.get(e, e))
                    i += 1
                    continue
                if ch == q:
                    i += 1
                    break
                buf.append(ch)
                i += 1
            out.append(tok2('str', ''.join(buf), i))
            continue
        if c.isdigit() or (c == '.' and i + 1 < n and src[i + 1].isdigit()):
            m = re.match(r'0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?', src[i:])
            txt = m.group(0)
            out.append(tok2('num', float(int(txt, 16)) if txt[:2].lower() == '0x' else float(txt), i))
            i += len(txt)
            continue
        if c.isalpha() or c == '_':
            m = re.match(r'[A-Za-z_][A-Za-z0-9_]*', src[i:])
            w = m.group(0)
            out.append(tok2('kw' if w in keywords else 'name', w, i))
            i += len(w)
            continue
        for op in ops:
            if src.startswith(op, i):
                out.append(tok2('op', op, i))
                i += len(op)
                break
        else:
            raise SyntaxError('bad char %r at %d' % (c, i))
    out.append(tok2('eof', None, n))
    return out

binpri = {
    'or': (1, 1), 'and': (2, 2),
    '<': (3, 3), '>': (3, 3), '<=': (3, 3), '>=': (3, 3), '~=': (3, 3), '==': (3, 3),
    '..': (9, 8),
    '+': (6, 6), '-': (6, 6),
    '*': (7, 7), '/': (7, 7), '%': (7, 7),
    '^': (10, 9),
}
unarypri = 8

class parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self, k=0):
        return self.t[self.i + k]

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def check(self, val):
        tok = self.peek()
        return tok.val == val and tok.kind in ('op', 'kw')

    def accept(self, val):
        if self.check(val):
            return self.next()
        return None

    def expect(self, val):
        tok = self.peek()
        if tok.val != val:
            raise SyntaxError('expected %r got %r at %d' % (val, tok.val, tok.pos))
        return self.next()

    def name(self):
        tok = self.peek()
        if tok.kind != 'name':
            raise SyntaxError('expected name got %r at %d' % (tok.val, tok.pos))
        self.next()
        return tok.val

    def block(self):
        stmts = []
        while True:
            tok = self.peek()
            if tok.kind == 'eof' or (tok.kind == 'kw' and tok.val in ('end', 'else', 'elseif', 'until')):
                break
            if tok.kind == 'kw' and tok.val == 'return':
                self.next()
                exprs = []
                if not (self.peek().kind == 'eof' or (self.peek().kind == 'kw' and self.peek().val in ('end', 'else', 'elseif', 'until')) or self.check(';')):
                    exprs = self.exprlist()
                self.accept(';')
                stmts.append(node2('return', exprs=exprs))
                break
            st = self.statement()
            if st is not None:
                stmts.append(st)
        return stmts

    def statement(self):
        tok = self.peek()
        if tok.kind == 'op' and tok.val == ';':
            self.next()
            return None
        if tok.kind == 'op' and tok.val == '::':
            self.next()
            nm = self.name()
            self.expect('::')
            return node2('label', name=nm)
        if tok.kind == 'kw':
            if tok.val == 'break':
                self.next()
                return node2('break')
            if tok.val == 'do':
                self.next()
                body = self.block()
                self.expect('end')
                return node2('do', body=body)
            if tok.val == 'while':
                self.next()
                cond = self.expr()
                self.expect('do')
                body = self.block()
                self.expect('end')
                return node2('while', cond=cond, body=body)
            if tok.val == 'repeat':
                self.next()
                body = self.block()
                self.expect('until')
                cond = self.expr()
                return node2('repeat', body=body, cond=cond)
            if tok.val == 'if':
                self.next()
                clauses = []
                cond = self.expr()
                self.expect('then')
                clauses.append((cond, self.block()))
                orelse = None
                while True:
                    if self.check('elseif'):
                        self.next()
                        c2 = self.expr()
                        self.expect('then')
                        clauses.append((c2, self.block()))
                        continue
                    if self.check('else'):
                        self.next()
                        orelse = self.block()
                    break
                self.expect('end')
                return node2('if', clauses=clauses, orelse=orelse)
            if tok.val == 'for':
                self.next()
                first = self.name()
                if self.check('='):
                    self.next()
                    start = self.expr()
                    self.expect(',')
                    stop = self.expr()
                    step = None
                    if self.accept(','):
                        step = self.expr()
                    self.expect('do')
                    body = self.block()
                    self.expect('end')
                    return node2('fornum', var=first, start=start, stop=stop, step=step, body=body)
                names = [first]
                while self.accept(','):
                    names.append(self.name())
                self.expect('in')
                exprs = self.exprlist()
                self.expect('do')
                body = self.block()
                self.expect('end')
                return node2('forin', names=names, exprs=exprs, body=body)
            if tok.val == 'function':
                self.next()
                target = node2('name', name=self.name())
                while True:
                    if self.check('.'):
                        self.next()
                        target = node2('index', obj=target, key=node2('str', val=self.name()))
                        continue
                    if self.check(':'):
                        self.next()
                        target = node2('index', obj=target, key=node2('str', val=self.name()))
                        target.method = True
                        continue
                    break
                fn = self.funcbody()
                return node2('assign', targets=[target], exprs=[fn])
            if tok.val == 'local':
                self.next()
                if self.check('function'):
                    self.next()
                    nm = self.name()
                    fn = self.funcbody()
                    return node2('localfunc', name=nm, func=fn)
                names = [self.name()]
                while self.accept(','):
                    names.append(self.name())
                exprs = []
                if self.accept('='):
                    exprs = self.exprlist()
                return node2('local', names=names, exprs=exprs)
        return self.exprstat()

    def funcbody(self):
        self.expect('(')
        params = []
        vararg = False
        if not self.check(')'):
            while True:
                if self.check('...'):
                    self.next()
                    vararg = True
                    break
                params.append(self.name())
                if not self.accept(','):
                    break
        self.expect(')')
        body = self.block()
        self.expect('end')
        return node2('function', params=params, vararg=vararg, body=body)

    def primaryexp(self):
        tok = self.peek()
        if tok.kind == 'name':
            self.next()
            node = node2('name', name=tok.val)
        elif tok.val == '(':
            self.next()
            node = node2('paren', expr=self.expr())
            self.expect(')')
        else:
            raise SyntaxError('unexpected %r at %d' % (tok.val, tok.pos))
        while True:
            if self.check('.'):
                self.next()
                node = node2('index', obj=node, key=node2('str', val=self.name()))
                continue
            if self.check('['):
                self.next()
                k = self.expr()
                self.expect(']')
                node = node2('index', obj=node, key=k)
                continue
            if self.check(':'):
                self.next()
                nm = self.name()
                args = self.callargs()
                node = node2('call', func=node2('index', obj=node, key=node2('str', val=nm)), args=args, method=nm)
                continue
            if self.check('(') or self.check('{') or self.peek().kind == 'str':
                args = self.callargs()
                node = node2('call', func=node, args=args)
                continue
            break
        return node

    def callargs(self):
        if self.peek().kind == 'str':
            return [node2('str', val=self.next().val)]
        if self.check('{'):
            return [self.table()]
        self.expect('(')
        args = []
        if not self.check(')'):
            args = self.exprlist()
        self.expect(')')
        return args

    def table(self):
        self.expect('{')
        items = []
        while not self.check('}'):
            if self.check('['):
                self.next()
                k = self.expr()
                self.expect(']')
                self.expect('=')
                v = self.expr()
                items.append(node2('kv', key=k, val=v))
            elif self.peek().kind == 'name' and self.peek(1).kind == 'op' and self.peek(1).val == '=':
                k = node2('str', val=self.name())
                self.next()
                v = self.expr()
                items.append(node2('kv', key=k, val=v))
            else:
                items.append(self.expr())
            if not (self.accept(',') or self.accept(';')):
                break
        self.expect('}')
        return node2('table', items=items)

    def simpleexp(self):
        tok = self.peek()
        if tok.kind == 'num':
            self.next()
            return node2('num', val=tok.val)
        if tok.kind == 'str':
            self.next()
            return node2('str', val=tok.val)
        if tok.kind == 'kw':
            if tok.val == 'nil':
                self.next()
                return node2('nil')
            if tok.val == 'true':
                self.next()
                return node2('true')
            if tok.val == 'false':
                self.next()
                return node2('false')
            if tok.val == 'function':
                self.next()
                return self.funcbody()
        if tok.kind == 'op' and tok.val == '...':
            self.next()
            return node2('vararg')
        if tok.kind == 'op' and tok.val == '{':
            return self.table()
        return self.primaryexp()

    def expr(self, limit=0):
        tok = self.peek()
        if (tok.kind == 'kw' and tok.val == 'not') or (tok.kind == 'op' and tok.val in ('-', '#')):
            self.next()
            operand = self.expr(unarypri)
            left = node2('unop', op=tok.val, expr=operand)
        else:
            left = self.simpleexp()
        while True:
            tok = self.peek()
            op = tok.val
            if tok.kind not in ('op', 'kw') or op not in binpri:
                break
            lp, rp = binpri[op]
            if lp <= limit:
                break
            self.next()
            right = self.expr(rp)
            left = node2('binop', op=op, left=left, right=right)
        return left

    def exprlist(self):
        out = [self.expr()]
        while self.accept(','):
            out.append(self.expr())
        return out

    def exprstat(self):
        e = self.primaryexp()
        if self.check('=') or self.check(','):
            targets = [e]
            while self.accept(','):
                targets.append(self.primaryexp())
            self.expect('=')
            exprs = self.exprlist()
            return node2('assign', targets=targets, exprs=exprs)
        if e.kind != 'call':
            raise SyntaxError('syntax error at %d' % self.peek().pos)
        return node2('callstat', call=e)

def nodes(node, out=None):
    if out is None:
        out = []
    if isinstance(node, node2):
        out.append(node)
        for key, value in node.__dict__.items():
            if key != 'kind':
                nodes(value, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            nodes(item, out)
    return out


def parse(src):
    p = parser(lex(src))
    body = p.block()
    if p.peek().kind != 'eof':
        raise SyntaxError('trailing %r at %d' % (p.peek().val, p.peek().pos))
    return body
