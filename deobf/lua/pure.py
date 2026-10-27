import math
import struct

from deobf.lua import luaparse


class impure(Exception):
    pass


class budget(Exception):
    pass


limit = 20000

libs = {
    'string': {'char', 'byte', 'sub', 'rep', 'len', 'upper', 'lower', 'reverse',
               'format', 'gsub', 'find', 'match'},
    'table': {'insert', 'concat', 'remove', 'unpack'},
    'bit32': {'bxor', 'bor', 'band', 'bnot', 'lshift', 'rshift', 'arshift',
              'btest', 'extract', 'replace'},
    'bit': {'bxor', 'bor', 'band', 'bnot', 'lshift', 'rshift', 'arshift'},
    'math': {'floor', 'ceil', 'abs', 'max', 'min', 'fmod', 'huge', 'pi'},
}

bits = 2 ** 32


def b32(value):
    return int(value) % bits


def signed(value):
    value = b32(value)
    return value - bits if value >= 2 ** 31 else value


def wrap(value):
    if isinstance(value, float) and value.is_integer() and abs(value) < 2 ** 53:
        return int(value)
    return value


def checkstr(value):
    if not isinstance(value, str):
        raise impure('expected string')
    return value


def checknum(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise impure('expected number')
    return value


def callstring(name, args):
    if name == 'char':
        return ''.join(chr(b32(checknum(a)) % 256) for a in args)
    if name == 'byte':
        text = checkstr(args[0])
        i = int(checknum(args[1])) if len(args) > 1 else 1
        j = int(checknum(args[2])) if len(args) > 2 else i
        if i < 0:
            i = len(text) + i + 1
        if j < 0:
            j = len(text) + j + 1
        i = max(i, 1)
        j = min(j, len(text))
        out = [ord(ch) for ch in text[i - 1:j]]
        return out[0] if len(out) == 1 else out
    if name == 'sub':
        text = checkstr(args[0])
        i = int(checknum(args[1]))
        j = int(checknum(args[2])) if len(args) > 2 else -1
        if i < 0:
            i = len(text) + i + 1
        if j < 0:
            j = len(text) + j + 1
        i = max(i, 1)
        j = min(j, len(text))
        return text[i - 1:j] if i <= j else ''
    if name == 'rep':
        text = checkstr(args[0])
        n = int(checknum(args[1]))
        sep = checkstr(args[2]) if len(args) > 2 else ''
        return sep.join([text] * max(n, 0))
    if name == 'len':
        return len(checkstr(args[0]))
    if name in ('upper', 'lower', 'reverse'):
        text = checkstr(args[0])
        return getattr(text, name)()
    if name == 'gsub':
        text = checkstr(args[0])
        pattern = checkstr(args[1])
        repl = checkstr(args[2])
        if pattern not in text:
            return text
        return text.replace(pattern, repl)
    if name in ('find', 'match'):
        raise impure('pattern matching')
    if name == 'format':
        spec = checkstr(args[0])
        return spec % tuple(args[1:])
    raise impure('string.' + name)


def calltable(name, args):
    if name == 'insert':
        table = args[0]
        if not isinstance(table, list):
            raise impure('table expected')
        if len(args) == 2:
            table.append(args[1])
        elif len(args) == 3:
            table.insert(int(checknum(args[1])) - 1, args[2])
        else:
            raise impure('insert arity')
        return None
    if name == 'concat':
        table = args[0]
        if not isinstance(table, list):
            raise impure('table expected')
        sep = checkstr(args[1]) if len(args) > 1 else ''
        return sep.join(checkstr(v) for v in table)
    if name == 'remove':
        table = args[0]
        if not isinstance(table, list):
            raise impure('table expected')
        if len(args) > 1:
            return table.pop(int(checknum(args[1])) - 1)
        return table.pop() if table else None
    if name == 'unpack':
        table = args[0]
        if not isinstance(table, list):
            raise impure('table expected')
        return list(table)
    raise impure('table.' + name)


def callbit(name, args):
    if name == 'bnot':
        return signed(~b32(checknum(args[0])))
    if name == 'bxor':
        out = 0
        for a in args:
            out = b32(out) ^ b32(checknum(a))
        return signed(out)
    if name == 'band':
        out = bits - 1
        for a in args:
            out &= b32(checknum(a))
        return signed(out)
    if name == 'bor':
        out = 0
        for a in args:
            out |= b32(checknum(a))
        return signed(out)
    if name == 'btest':
        return callbit('band', args) != 0
    if name == 'lshift':
        return signed(b32(checknum(args[0])) << (b32(checknum(args[1])) % 32))
    if name == 'rshift':
        return signed(b32(checknum(args[0])) >> (b32(checknum(args[1])) % 32))
    if name == 'arshift':
        return signed(signed(checknum(args[0])) >> (b32(checknum(args[1])) % 32))
    raise impure('bit.' + name)


def callmath(name, args):
    if name == 'floor':
        return int(math.floor(checknum(args[0])))
    if name == 'ceil':
        return int(math.ceil(checknum(args[0])))
    if name == 'abs':
        return abs(checknum(args[0]))
    if name == 'max':
        return max(checknum(a) for a in args)
    if name == 'min':
        return min(checknum(a) for a in args)
    if name == 'fmod':
        return wrap(math.fmod(checknum(args[0]), checknum(args[1])))
    if name == 'huge':
        return float('inf')
    if name == 'pi':
        return math.pi
    raise impure('math.' + name)


def calllib(root, name, args):
    if root == 'string':
        return callstring(name, args)
    if root == 'table':
        return calltable(name, args)
    if root in ('bit32', 'bit'):
        return callbit(name, args)
    if root == 'math':
        return callmath(name, args)
    raise impure(root)


def truthy(value):
    if value is unknown:
        raise impure('unknown condition')
    if isinstance(value, tuple):
        raise impure('library value')
    return not (value is None or value is False)


def tonum(value):
    if isinstance(value, bool):
        raise impure('boolean arith')
    return checknum(value)


def arith(op, left, right):
    a, b = tonum(left), tonum(right)
    if op == '+':
        return wrap(a + b)
    if op == '-':
        return wrap(a - b)
    if op == '*':
        return wrap(a * b)
    if op == '/':
        return wrap(a / b)
    if op == '//':
        return wrap(a // b)
    if op == '%':
        return wrap(a % b)
    if op == '^':
        return wrap(a ** b)
    raise impure(op)


def compare(op, left, right):
    if op == '==':
        return left == right
    if op == '~=':
        return left != right
    if isinstance(left, str) or isinstance(right, str):
        raise impure('string compare')
    a, b = tonum(left), tonum(right)
    if op == '<':
        return a < b
    if op == '>':
        return a > b
    if op == '<=':
        return a <= b
    if op == '>=':
        return a >= b
    raise impure(op)


class evaler:

    def __init__(self, funcs):
        self.funcs = funcs
        self.steps = 0

    def tick(self):
        self.steps += 1
        if self.steps > limit:
            raise budget('step limit')

    def lookup(self, name, scope):
        for frame in reversed(scope):
            if name in frame:
                value = frame[name]
                if value is unknown:
                    raise impure('unknown ' + name)
                return value
        if name in libs:
            return (lib, name)
        raise impure('global ' + name)

    def index(self, obj, key):
        if isinstance(obj, tuple) and len(obj) == 2 and obj[0] == lib:
            if str(key) not in libs[obj[1]]:
                raise impure('%s.%s' % (obj[1], key))
            return (obj[1], key)
        raise impure('index on table')

    def expr(self, node, scope):
        self.tick()
        kind = node.kind
        if kind == 'num':
            return wrap(node.val)
        if kind == 'str':
            return node.val
        if kind == 'nil':
            return None
        if kind == 'true':
            return True
        if kind == 'false':
            return False
        if kind == 'name':
            return self.lookup(node.name, scope)
        if kind == 'paren':
            return self.expr(node.expr, scope)
        if kind == 'vararg':
            raise impure('vararg')
        if kind == 'table':
            out = []
            for item in node.items:
                if item.kind == 'kv':
                    if item.key is not None:
                        raise impure('table key')
                    out.append(self.expr(item.val, scope))
                else:
                    out.append(self.expr(item, scope))
            return out
        if kind == 'unop':
            value = self.expr(node.expr, scope)
            if node.op == '-':
                return -tonum(value)
            if node.op == 'not':
                return not truthy(value)
            if node.op == '#':
                if isinstance(value, str):
                    return len(value)
                if isinstance(value, list):
                    return len(value)
                raise impure('length')
            raise impure(node.op)
        if kind == 'binop':
            op = node.op
            if op == 'and':
                left = self.expr(node.left, scope)
                return self.expr(node.right, scope) if truthy(left) else left
            if op == 'or':
                left = self.expr(node.left, scope)
                return left if truthy(left) else self.expr(node.right, scope)
            left = self.expr(node.left, scope)
            right = self.expr(node.right, scope)
            if op == '..':
                return concatstr(left, right)
            if op in ('+', '-', '*', '/', '//', '%', '^'):
                return arith(op, left, right)
            return compare(op, left, right)
        if kind == 'index':
            if node.key.kind == 'str':
                key = node.key.val
            else:
                key = self.expr(node.key, scope)
            return self.index(self.expr(node.obj, scope), key)
        if kind == 'call':
            args = [self.expr(a, scope) for a in node.args]
            target = node.func
            if target.kind == 'name':
                value = self.lookup(target.name, scope)
                if isinstance(value, luaparse.node2):
                    return self.call(value, args, scope)
                if isinstance(value, tuple) and len(value) == 2 and value[0] != lib:
                    return calllib(value[0], value[1], args)
                raise impure('call of value')
            if target.kind == 'index':
                member = self.expr(target, scope)
                if isinstance(member, tuple) and not member[0] == lib:
                    return calllib(member[0], member[1], args)
                raise impure('call field')
            if target.kind == 'function':
                return self.call(target, args, scope)
            raise impure('call target')
        raise impure('expr ' + kind)

    def resolve(self, name, scope):
        for frame in reversed(scope):
            if name in frame:
                value = frame[name]
                if isinstance(value, luaparse.node2):
                    return value
                raise impure('call of value')
        fn = self.funcs.get(name)
        if fn is None:
            raise impure('call ' + name)
        return fn

    def call(self, fn, args, scope):
        frame = {}
        for i, param in enumerate(fn.params):
            frame[param] = args[i] if i < len(args) else None
        inner = scope + [frame]
        value = self.block(fn.body, inner)
        if isinstance(value, tuple):
            return value[0] if value else None
        return value

    def block(self, stmts, scope):
        for stmt in stmts:
            value = self.stmt(stmt, scope)
            if isinstance(value, tuple):
                return value
        return None

    def stmt(self, node, scope):
        self.tick()
        kind = node.kind
        if kind == 'local':
            values = [self.expr(e, scope) for e in node.exprs]
            for i, name in enumerate(node.names):
                scope[-1][name] = values[i] if i < len(values) else None
            return None
        if kind == 'localfunc':
            scope[-1][node.name] = node.func
            return None
        if kind == 'assign':
            values = [self.expr(e, scope) for e in node.exprs]
            for i, target in enumerate(node.targets):
                if target.kind != 'name':
                    raise impure('assign target')
                value = values[i] if i < len(values) else None
                for frame in reversed(scope):
                    if target.name in frame:
                        frame[target.name] = value
                        break
                else:
                    raise impure('assign global')
            return None
        if kind == 'if':
            for cond, body in node.clauses:
                if truthy(self.expr(cond, scope)):
                    return self.block(body, scope + [{}])
            if node.orelse is not None:
                return self.block(node.orelse, scope + [{}])
            return None
        if kind == 'fornum':
            start = tonum(self.expr(node.start, scope))
            stop = tonum(self.expr(node.stop, scope))
            step = tonum(self.expr(node.step, scope)) if node.step is not None else 1
            if step == 0:
                raise impure('zero step')
            value = start
            while (step > 0 and value <= stop) or (step < 0 and value >= stop):
                inner = scope + [{node.var: value}]
                result = self.block(node.body, inner)
                if isinstance(result, tuple):
                    return result
                value += step
            return None
        if kind == 'do':
            return self.block(node.body, scope + [{}])
        if kind == 'return':
            return (tuple(self.expr(e, scope) for e in node.exprs),)
        if kind == 'callstat':
            self.expr(node.call, scope)
            return None
        if kind == 'while':
            while truthy(self.expr(node.cond, scope)):
                result = self.block(node.body, scope + [{}])
                if isinstance(result, tuple):
                    return result
            return None
        if kind == 'break':
            raise impure('break')
        raise impure('stmt ' + kind)


class marker:
    def __repr__(self):
        return 'unknown'


unknown = marker()
lib = '#lib'


def concatstr(left, right):
    return luaish(left) + luaish(right)


def luaish(value):
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        raise impure('concat nil')
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def literals(node):
    return node.kind in ('num', 'str', 'true', 'false')


def constish(node, scope):
    if node.kind == 'function':
        return node
    runner = evaler({})
    try:
        value = runner.expr(node, scope)
    except (impure, budget, RecursionError, OverflowError):
        return unknown
    if isinstance(value, tuple) and len(value) == 2:
        return value
    if isinstance(value, list):
        return value
    if isinstance(value, luaparse.node2):
        return value
    if value is None or isinstance(value, (bool, str)) or isinstance(value, (int, float)):
        return value
    return unknown


def constnode(value):
    if isinstance(value, bool):
        return luaparse.node2('true' if value else 'false')
    if isinstance(value, str):
        return luaparse.node2('str', val=value)
    if isinstance(value, (int, float)):
        return luaparse.node2('num', val=float(value))
    if value is None:
        raise impure('nil literal')
    raise impure('result type')


def evaluate(node, scope):
    if node.func.kind != 'name':
        return None
    if not all(literals(a) for a in node.args):
        return None
    runner = evaler({})
    args = []
    for a in node.args:
        if a.kind == 'num':
            args.append(wrap(a.val))
        elif a.kind == 'str':
            args.append(a.val)
        else:
            args.append(a.kind == 'true')
    try:
        fn = None
        for frame in reversed(scope):
            if node.func.name in frame:
                fn = frame[node.func.name]
                break
        if fn is None or not isinstance(fn, luaparse.node2):
            return None
        value = runner.call(fn, args, scope)
    except (impure, budget, RecursionError, IndexError, KeyError, ValueError,
            ZeroDivisionError, OverflowError, TypeError, struct.error):
        return None
    if isinstance(value, tuple):
        value = value[0] if value else None
    try:
        return constnode(value)
    except impure:
        return None


def foldexpr(node, scope, counter):
    if not isinstance(node, luaparse.node2):
        return node
    if node.kind == 'function':
        node.body = symbolic(node.body, stale(node.params, scope), counter)
        return node
    if node.kind == 'call':
        folded = evaluate(node, scope)
        if folded is not None:
            counter[0] += 1
            return folded
    for key, value in list(vars(node).items()):
        if key == 'kind':
            continue
        if isinstance(value, luaparse.node2):
            setattr(node, key, foldexpr(value, scope, counter))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, luaparse.node2):
                    value[i] = foldexpr(item, scope, counter)
                elif isinstance(item, tuple):
                    value[i] = tuple(foldexpr(x, scope, counter) if isinstance(x, luaparse.node2) else x
                                     for x in item)
    return node


def stale(names, scope):
    frame = {name: unknown for name in names}
    return scope + [frame]


def symbolic(stmts, scope, counter):
    kept = []
    for stmt in stmts:
        kind = stmt.kind
        if kind == 'local':
            stmt.exprs = [foldexpr(e, scope, counter) for e in stmt.exprs]
            values = [constish(e, scope) for e in stmt.exprs]
            for name, value in zip(stmt.names, values):
                scope[-1][name] = value
            kept.append(stmt)
        elif kind == 'localfunc':
            scope[-1][stmt.name] = stmt.func
            stmt.func.body = symbolic(stmt.func.body, stale(stmt.func.params, scope), counter)
            kept.append(stmt)
        elif kind == 'assign':
            stmt.exprs = [foldexpr(e, scope, counter) for e in stmt.exprs]
            values = [constish(e, scope) for e in stmt.exprs]
            for target, value in zip(stmt.targets, values):
                if target.kind == 'name':
                    for frame in reversed(scope):
                        if target.name in frame:
                            frame[target.name] = value
                            break
            kept.append(stmt)
        elif kind == 'callstat':
            stmt.call = foldexpr(stmt.call, scope, counter)
            kept.append(stmt)
        elif kind == 'return':
            stmt.exprs = [foldexpr(e, scope, counter) for e in stmt.exprs]
            kept.append(stmt)
        elif kind == 'if':
            taken = None
            decided = True
            clauses = []
            for cond, body in stmt.clauses:
                value = constish(cond, scope)
                if value is unknown:
                    decided = False
                clauses.append((cond, body))
                if decided and taken is None and truthy(value):
                    taken = body
            if decided and taken is None and stmt.orelse is not None:
                taken = stmt.orelse
            if decided:
                if taken is not None:
                    kept.extend(symbolic(taken, scope + [{}], counter))
            else:
                newclauses = []
                for cond, body in stmt.clauses:
                    cond = foldexpr(cond, scope, counter)
                    newclauses.append((cond, symbolic(body, scope + [{}], counter)))
                stmt.clauses = newclauses
                if stmt.orelse is not None:
                    stmt.orelse = symbolic(stmt.orelse, scope + [{}], counter)
                kept.append(stmt)
        elif kind == 'fornum':
            for attr in ('start', 'stop', 'step'):
                value = getattr(stmt, attr, None)
                if value is not None:
                    setattr(stmt, attr, foldexpr(value, scope, counter))
            stmt.body = symbolic(stmt.body, stale([stmt.var], scope), counter)
            kept.append(stmt)
        elif kind == 'forin':
            stmt.exprs = [foldexpr(e, scope, counter) for e in stmt.exprs]
            stmt.body = symbolic(stmt.body, stale(stmt.names, scope), counter)
            kept.append(stmt)
        elif kind == 'while':
            stmt.cond = foldexpr(stmt.cond, scope, counter)
            stmt.body = symbolic(stmt.body, scope + [{}], counter)
            kept.append(stmt)
        elif kind == 'repeat':
            inner = scope + [{}]
            stmt.body = symbolic(stmt.body, inner, counter)
            stmt.cond = foldexpr(stmt.cond, inner, counter)
            kept.append(stmt)
        elif kind == 'do':
            kept.extend(symbolic(stmt.body, scope + [{}], counter))
        else:
            kept.append(stmt)
    return kept


def clone(node):
    if isinstance(node, list):
        return [clone(x) for x in node]
    if isinstance(node, tuple):
        return tuple(clone(x) for x in node)
    if isinstance(node, luaparse.node2):
        out = luaparse.node2(node.kind)
        for key, value in node.__dict__.items():
            if key == 'kind':
                continue
            setattr(out, key, clone(value))
        return out
    return node


def substituted(node, mapping):
    node = clone(node)
    return rename(node, mapping)


def rename(node, mapping):
    if isinstance(node, list):
        for i, item in enumerate(node):
            node[i] = rename(item, mapping)
        return node
    if isinstance(node, tuple):
        return tuple(rename(x, mapping) for x in node)
    if not isinstance(node, luaparse.node2):
        return node
    if node.kind == 'name' and node.name in mapping:
        return mapping[node.name]
    if node.kind == 'function':
        inner = dict(mapping)
        for param in node.params:
            inner.pop(param, None)
        for key, value in list(node.__dict__.items()):
            if key == 'kind':
                continue
            setattr(node, key, rename(value, inner))
        return node
    for key, value in list(node.__dict__.items()):
        if key == 'kind':
            continue
        setattr(node, key, rename(value, mapping))
    return node


simplekinds = ('num', 'str', 'true', 'false', 'table', 'name', 'index', 'nil')


def assigned(body, name):
    return name in writesof(body)


def hasvararg(fn):
    for node in luaparse.nodes(fn.body):
        if node.kind == 'vararg':
            return True
    return False


def bindargs(fn, args):
    mapping = {}
    if getattr(fn, 'vararg', False) or hasvararg(fn):
        return None
    for i, param in enumerate(fn.params):
        if i >= len(args):
            break
        arg = args[i]
        if arg.kind not in simplekinds:
            return None
        if assigned(fn.body, param):
            return None
        mapping[param] = clone(arg)
    return mapping


def tailcall(stmt, table, uses, decls=None, writes=None):
    if stmt.kind != 'return':
        return None
    if len(stmt.exprs) != 1:
        return None
    call = stmt.exprs[0]
    if call.kind != 'call' or call.func.kind != 'name':
        return None
    name = call.func.name
    fn = table.get(name)
    if fn is None or uses.get(name, 0) != 1:
        return None
    if decls is not None:
        if decls.get(name, 0) > 1:
            return None
        if writes is not None and writes.get(name, 0) > 1:
            return None
    mapping = bindargs(fn, call.args)
    if mapping is None:
        return None
    return [substituted(item, mapping) for item in fn.body]


def collect(stmts, table):
    for unused in range(6):
        before = dict(table)
        for stmt in stmts:
            for node in luaparse.nodes(stmt):
                if node.kind == 'localfunc':
                    table[node.name] = node.func
                elif node.kind == 'local' and len(node.names) == len(node.exprs):
                    for name, value in zip(node.names, node.exprs):
                        found = None
                        if value.kind == 'function':
                            found = value
                        elif value.kind == 'name':
                            found = table.get(value.name)
                        if found is not None:
                            table[name] = found
                elif node.kind == 'assign':
                    for target, value in zip(node.targets, node.exprs):
                        if target.kind != 'name':
                            continue
                        found = None
                        if value.kind == 'function':
                            found = value
                        elif value.kind == 'name':
                            found = table.get(value.name)
                        if found is not None:
                            table[target.name] = found
        if before == table:
            break
    return table


def declarations(stmts):
    counts = {}
    params = {}
    writes = {}
    for stmt in stmts:
        for node in luaparse.nodes(stmt):
            if node.kind in ('local', 'localfunc', 'forin'):
                for name in getattr(node, 'names', []) or [getattr(node, 'name', None)]:
                    if name:
                        counts[name] = counts.get(name, 0) + 1
            elif node.kind == 'fornum':
                counts[node.var] = counts.get(node.var, 0) + 1
            elif node.kind == 'assign':
                for target in node.targets:
                    if target.kind == 'name':
                        writes[target.name] = writes.get(target.name, 0) + 1
        for node in luaparse.nodes(stmt):
            if node.kind == 'function':
                for param in node.params:
                    params[param] = params.get(param, 0) + 1
    return counts, writes, params


def readcount(node, out=None):
    if out is None:
        out = {}
    if isinstance(node, luaparse.node2):
        if node.kind == 'assign':
            for target in node.targets:
                if target.kind == 'index':
                    readcount(target, out)
            for value in node.exprs:
                readcount(value, out)
            return out
        if node.kind == 'name':
            out[node.name] = out.get(node.name, 0) + 1
        for key, value in node.__dict__.items():
            if key != 'kind':
                readcount(value, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            readcount(item, out)
    return out


def inlinebody(stmts, table, counter, uses=None, decls=None, writes=None):
    if decls is None:
        decls, writes, params = declarations(stmts)
    if uses is None:
        uses = {}
        for stmt in stmts:
            for name, count in readcount(stmt).items():
                uses[name] = uses.get(name, 0) + count
    out = []
    for stmt in stmts:
        body = tailcall(stmt, table, uses, decls, writes)
        if body is not None:
            counter[0] += 1
            out.extend(inlinebody(body, table, counter, None, decls, writes))
            continue
        for attr in ('body', 'orelse'):
            inner = getattr(stmt, attr, None)
            if isinstance(inner, list):
                setattr(stmt, attr, inlinebody(inner, table, counter, None, decls, writes))
        if getattr(stmt, 'clauses', None):
            stmt.clauses = [(cond, inlinebody(body, table, counter, None, decls, writes))
                            for cond, body in stmt.clauses]
        out.append(stmt)
    return out


def namesof(node, out=None):
    if out is None:
        out = []
    if isinstance(node, luaparse.node2):
        if node.kind == 'name':
            out.append(node.name)
        for key, value in node.__dict__.items():
            if key != 'kind':
                namesof(value, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            namesof(item, out)
    return out


def blocks(stmt):
    out = []
    for attr in ('body', 'orelse'):
        inner = getattr(stmt, attr, None)
        if isinstance(inner, list):
            out.append((stmt, attr))
    if getattr(stmt, 'clauses', None):
        out.append((stmt, 'clauses'))
    if stmt.kind in ('local', 'assign'):
        for value in stmt.exprs:
            if isinstance(value, luaparse.node2) and value.kind == 'function':
                out.append((value, 'body'))
    return out


def recurse(stmts, fn):
    for stmt in stmts:
        for owner, attr in blocks(stmt):
            if attr == 'clauses':
                owner.clauses = [(cond, fn(body)) for cond, body in owner.clauses]
            else:
                setattr(owner, attr, fn(getattr(owner, attr)))
    return stmts


def writesof(node, out=None):
    if out is None:
        out = set()
    if isinstance(node, luaparse.node2):
        if node.kind == 'assign':
            for target in node.targets:
                if target.kind == 'name':
                    out.add(target.name)
                else:
                    writesof(target, out)
            for value in node.exprs:
                writesof(value, out)
            return out
        if node.kind in ('local', 'localfunc', 'forin', 'fornum'):
            names = getattr(node, 'names', None) or [
                getattr(node, 'name', getattr(node, 'var', None))]
            for name in names:
                if name:
                    out.add(name)
        if node.kind == 'function':
            for param in node.params:
                out.add(param)
        for key, value in node.__dict__.items():
            if key != 'kind':
                writesof(value, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            writesof(item, out)
    return out


def readnames(node, out=None):
    if out is None:
        out = set()
    if isinstance(node, luaparse.node2):
        if node.kind == 'assign':
            for target in node.targets:
                if target.kind == 'index':
                    readnames(target, out)
            for value in node.exprs:
                readnames(value, out)
            return out
        if node.kind == 'name':
            out.add(node.name)
        for key, value in node.__dict__.items():
            if key != 'kind':
                readnames(value, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            readnames(item, out)
    return out


def guard(stmt):
    if stmt.kind != 'if' or stmt.orelse is not None:
        return set()
    written = set()
    for cond, body in stmt.clauses:
        for inner in body:
            if inner.kind != 'assign':
                return set()
            for target in inner.targets:
                if target.kind != 'name':
                    return set()
                written.add(target.name)
    return written


def deadcode(stmts, top=True):
    recurse(stmts, lambda body: deadcode(body, False))
    stmts = list(stmts)
    changed = True
    while changed:
        changed = False
        for i, stmt in enumerate(stmts):
            if top and stmt.kind == 'if':
                written = guard(stmt)
                if written:
                    used = readnames(stmts[i + 1:])
                    if not (written & used):
                        stmts = stmts[:i] + stmts[i + 1:]
                        changed = True
                        break
            if stmt.kind in ('local', 'localfunc'):
                defined = stmt.names if stmt.kind == 'local' else [stmt.name]
            elif (top and stmt.kind == 'assign'
                  and all(t.kind == 'name' for t in stmt.targets)):
                defined = [t.name for t in stmt.targets]
            else:
                continue
            rest = stmts[:i] + stmts[i + 1:]
            used = set()
            for other in rest:
                used.update(namesof(other))
            if all(name not in used for name in defined):
                stmts = rest
                changed = True
                break
    return stmts


literalkinds = ('num', 'str', 'true', 'false')


def constant(stmts, counter):
    recurse(stmts, lambda body: constant(body, counter)[0])
    out = list(stmts)
    defs = {}
    for i, stmt in enumerate(out):
        if stmt.kind == 'local' and len(stmt.names) == 1 and len(stmt.exprs) == 1:
            if stmt.exprs[0].kind in literalkinds:
                defs[i] = (stmt.names[0], stmt.exprs[0])
        elif (stmt.kind == 'assign' and len(stmt.targets) == 1
              and len(stmt.exprs) == 1 and stmt.targets[0].kind == 'name'
              and stmt.exprs[0].kind in literalkinds):
            defs[i] = (stmt.targets[0].name, stmt.exprs[0])
    if not defs:
        return out, 0
    written = []
    for stmt in out:
        seen = set()
        writesof(stmt, seen)
        written.append(seen)
    drop = {}
    for i, (name, value) in defs.items():
        others = set()
        for j, seen in enumerate(written):
            if j != i:
                others |= seen
        if name in others:
            continue
        uses = sum(1 for j, stmt in enumerate(out) if j != i
                   for n in namesof(stmt) if n == name)
        if uses:
            drop[i] = (name, value)
    if not drop:
        return out, 0
    mapping = {}
    kept = []
    for i, stmt in enumerate(out):
        if i in drop:
            mapping[drop[i][0]] = drop[i][1]
            counter[0] += 1
            continue
        kept.append(stmt)
    return [rename(stmt, mapping) for stmt in kept], len(drop)




def purechain(node):
    if node.kind == 'name':
        return True
    if node.kind == 'str':
        return True
    if node.kind == 'index':
        return purechain(node.obj) and (node.key.kind in ('str', 'num'))
    return False


def purerhs(node):
    if node is None:
        return True
    if node.kind in ('num', 'str', 'true', 'false', 'nil', 'name', 'function'):
        return True
    if node.kind == 'index':
        return purechain(node)
    if node.kind == 'table':
        return all(purerhs(item) for item in node.items)
    if node.kind == 'unop':
        return purerhs(node.expr)
    if node.kind == 'binop':
        return purerhs(node.left) and purerhs(node.right)
    if node.kind == 'paren':
        return purerhs(node.expr)
    return False


def mentions(node, out=None):
    if out is None:
        out = {}
    if isinstance(node, luaparse.node2):
        if node.kind == 'name':
            out[node.name] = out.get(node.name, 0) + 1
        for key, value in node.__dict__.items():
            if key != 'kind':
                mentions(value, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            mentions(item, out)
    return out


def writetargets(stmt):
    if stmt.kind == 'local':
        return list(stmt.names)
    if stmt.kind == 'localfunc':
        return [stmt.name]
    if stmt.kind == 'assign':
        return [t.name for t in stmt.targets if t.kind == 'name']
    return []


def deadends(stmts):
    stmts = list(stmts)
    changed = True
    while changed:
        changed = False
        for i, stmt in enumerate(stmts):
            if stmt.kind not in ('local', 'localfunc'):
                continue
            if stmt.kind == 'local' and not all(purerhs(e) for e in stmt.exprs):
                continue
            rest = stmts[:i] + stmts[i + 1:]
            seen = {}
            for other in rest:
                mentions(other, seen)
            names = writetargets(stmt)
            if names and all(seen.get(name, 0) == 0 for name in names):
                stmts = rest
                changed = True
                break
    return stmts


def deadstores(stmts):
    stmts = list(stmts)
    for i, stmt in enumerate(stmts):
        if stmt is None:
            continue
        if stmt.kind != 'local' or len(stmt.names) != 1 or len(stmt.exprs) != 1:
            continue
        if not purerhs(stmt.exprs[0]):
            continue
        name = stmt.names[0]
        before = [prev for prev in stmts[:i] if prev is not None]
        if any(writetargets(prev).count(name) for prev in before):
            continue
        if any(mentions(prev).get(name) for prev in before):
            continue
        for j in range(i + 1, len(stmts)):
            if stmts[j] is None:
                continue
            if name in readnames(stmts[j]):
                break
            if name in writetargets(stmts[j]):
                later = stmts[j]
                if later.kind != 'assign' or len(later.targets) != 1:
                    break
                if later.targets[0].kind != 'name' or later.targets[0].name != name:
                    break
                stmts[j] = luaparse.node2('local', names=[name], exprs=later.exprs)
                stmts[i] = None
                break
    return [stmt for stmt in stmts if stmt is not None]


def wholewrites(body):
    seen = set()
    writesof(body, seen)
    return seen


def dropmarked(node, out=None):
    if out is None:
        out = []
    if isinstance(node, list):
        kept = [dropmarked(item, out) for item in node]
        return [item for item in kept if item is not None]
    if isinstance(node, luaparse.node2):
        if getattr(node, 'dropped', False):
            return None
        for key, value in list(node.__dict__.items()):
            if key in ('kind', 'dropped'):
                continue
            if isinstance(value, (luaparse.node2, list)):
                setattr(node, key, dropmarked(value, out))
        return node
    if isinstance(node, tuple):
        return tuple(dropmarked(x, out) for x in node)
    return node


def targetnames(node, out=None):
    if out is None:
        out = set()
    if isinstance(node, luaparse.node2):
        if node.kind == 'assign':
            for target in node.targets:
                if target.kind == 'index':
                    out.update(n for n in readnames(target.obj))
            for value in node.exprs:
                targetnames(value, out)
            return out
        for key, value in node.__dict__.items():
            if key != 'kind':
                targetnames(value, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            targetnames(item, out)
    return out


sharedkinds = ('table', 'name')


def propagate(body):
    written = {}
    blocked = targetnames(body)
    reads = {}
    for node in luaparse.nodes(body):
        if node.kind == 'name':
            reads[node.name] = reads.get(node.name, 0) + 1
    for stmt in luaparse.nodes(body):
        for name in writetargets(stmt):
            written[name] = written.get(name, 0) + 1
    mapping = {}
    for stmt in luaparse.nodes(body):
        if stmt.kind != 'local' or len(stmt.names) != 1 or len(stmt.exprs) != 1:
            continue
        name = stmt.names[0]
        value = stmt.exprs[0]
        if written.get(name, 0) != 1:
            continue
        if name in blocked:
            continue
        if value.kind in sharedkinds and reads.get(name, 0) != 1:
            continue
        if value.kind in ('num', 'str', 'true', 'false', 'table'):
            mapping[name] = value
            stmt.dropped = True
        elif value.kind == 'name' and value.name != name:
            mapping[name] = value
            stmt.dropped = True
    if not mapping:
        return body, 0
    total = len(mapping)
    body = rename(body, mapping)
    body = dropmarked(body)
    return body, total


def signature(stmts):
    total = 0
    count = 0
    for stmt in stmts:
        count += 1
        for value in mentions(stmt).values():
            total += value
    return count, total


def mergelocal(stmts):
    out = list(stmts)
    for i, stmt in enumerate(out):
        if stmt is None or stmt.kind != 'local' or stmt.exprs:
            continue
        if i + 1 >= len(out) or out[i + 1] is None:
            continue
        nxt = out[i + 1]
        if nxt.kind != 'assign' or len(nxt.targets) != 1:
            continue
        if nxt.targets[0].kind != 'name':
            continue
        if nxt.targets[0].name not in stmt.names:
            continue
        if len(stmt.names) != 1:
            continue
        name = stmt.names[0]
        reads = set()
        for value in nxt.exprs:
            reads.update(readnames(value))
        if name in reads:
            continue
        out[i] = luaparse.node2('local', names=[name], exprs=list(nxt.exprs))
        out[i + 1] = None
    return [stmt for stmt in out if stmt is not None]


def readcounts(stmts):
    seen = {}
    for stmt in stmts:
        if stmt is None:
            continue
        for name in readnames(stmt):
            seen[name] = seen.get(name, 0) + 1
    return seen


def tailinline(stmts, table, reads):
    out = list(stmts)
    for i, stmt in enumerate(out):
        if stmt is None or stmt.kind != 'return' or len(stmt.exprs) != 1:
            continue
        call = stmt.exprs[0]
        if call.kind != 'call' or call.func.kind != 'name':
            continue
        name = call.func.name
        fn = table.get(name)
        if fn is None or reads.get(name, 0) != 1:
            continue
        if getattr(fn, 'vararg', False) or hasvararg(fn):
            continue
        if len(call.args) != len(fn.params):
            continue
        if not all(arg.kind in simplekinds for arg in call.args):
            continue
        pre = []
        for param, arg in zip(fn.params, call.args):
            pre.append(luaparse.node2('local', names=[param], exprs=[clone(arg)]))
        out[i] = luaparse.node2('do', body=pre + [clone(item) for item in fn.body])
    return [stmt for stmt in out if stmt is not None]


def dropdeadif(stmts):
    out = list(stmts)
    for i, stmt in enumerate(out):
        if stmt is None or stmt.kind != 'if' or stmt.orelse is not None:
            continue
        if len(stmt.clauses) != 1:
            continue
        cond, body = stmt.clauses[0]
        if not purerhs(cond):
            continue
        written = set()
        for inner in body:
            if inner.kind != 'assign' or not all(purerhs(e) for e in inner.exprs):
                written = set()
                break
            for target in inner.targets:
                if target.kind != 'name':
                    written = set()
                    break
                written.add(target.name)
        if not written:
            continue
        used = set()
        for other in out[i + 1:]:
            if other is not None:
                used.update(readnames(other))
        if written & used:
            continue
        out[i] = None
    return [stmt for stmt in out if stmt is not None]


def flatten(stmts):
    out = list(stmts)
    for i, stmt in enumerate(out):
        if stmt.kind == 'do' and len(stmt.body) == 1 and stmt.body[0].kind == 'do':
            out[i] = stmt.body[0]
    return out


def declared(stmts):
    names = set()
    for stmt in stmts:
        if stmt is None:
            continue
        for node in luaparse.nodes(stmt):
            if node.kind in ('local', 'localfunc', 'forin'):
                names.update(n for n in getattr(node, 'names', None) or [getattr(node, 'name', '')] if n)
            elif node.kind == 'fornum':
                names.add(node.var)
    return names


def unwrap(stmts):
    out = list(stmts)
    for i, stmt in enumerate(out):
        if stmt.kind != 'do':
            continue
        inner = declared(stmt.body)
        if not inner:
            out[i:i + 1] = list(stmt.body)
            continue
        outside = set()
        for other in out[:i] + out[i + 1:]:
            if other is not None:
                outside.update(mentions(other))
        if inner & outside:
            continue
        out[i:i + 1] = list(stmt.body)
    return out


def passonce(stmts):
    recurse(stmts, passonce)
    stmts = unwrap(flatten(dropdeadif(mergelocal(stmts))))
    stmts, unused = propagate(stmts)
    stmts = deadends(deadstores(stmts))
    table = collect(stmts, {})
    if table:
        stmts = tailinline(stmts, table, readcounts(stmts))
        stmts = mergelocal(stmts)
        stmts, unused = propagate(stmts)
        stmts = deadends(deadstores(stmts))
    return stmts


def junk(stmts, rounds=8):
    for unused in range(rounds):
        before = signature(stmts)
        stmts = passonce(stmts)
        if signature(stmts) == before:
            break
    return stmts


def simplify(body, rounds=12):
    folds = 0
    changed = False
    for unused in range(rounds):
        before = signature(body)
        body, n = fold(body)
        folds += n
        body = passonce(body)
        if signature(body) != before:
            changed = True
            continue
        break
    return body, (folds if folds else (1 if changed else 0)), folds


def fold(body):
    counter = [0]
    out = symbolic(body, [{}], counter)
    return out, counter[0]
