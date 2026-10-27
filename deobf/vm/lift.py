import re
from . import vmisa

keywords = {'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for', 'function', 'if', 'in',
            'local', 'nil', 'not', 'or', 'repeat', 'return', 'then', 'true', 'until', 'while', 'goto'}

def isident(text):
    return bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', text)) and text not in keywords

def strlit(value):
    out = ['"']
    for ch in value:
        code = ord(ch)
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
        elif 32 <= code < 127:
            out.append(ch)
        else:
            out.append('\\%d' % code)
    out.append('"')
    return ''.join(out)

def polish(lines):
    for unused in range(8):
        lines = mergeassign(lines)
    return dropdead(lines)

def reindent(lines):
    out = []
    depth = 0
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if text in ('end', 'else') or text.startswith('elseif ') or text == 'until':
            depth = max(0, depth - 1)
        out.append('  ' * depth + text)
        opens = text.endswith(' then') or text.endswith(' do') or re.search(r'function\([^)]*\)$', text)
        if text in ('else',) or text.startswith('elseif '):
            opens = True
        if opens:
            depth += 1
    return out

def paths(lines):
    out = []
    stack = []
    for line in lines:
        text = line.strip()
        if text in ('end', 'else') or text.startswith('elseif ') or text.startswith('until '):
            if stack:
                stack.pop()
        out.append(tuple(stack))
        if text.endswith(' then'):
            stack.append('if')
        elif re.search(r'function\s*\([^)]*\)$', text):
            stack.append('func')
        elif text.endswith(' do') or re.search(r'^for .* do$', text):
            stack.append('loop')
        elif text == 'repeat':
            stack.append('loop')
        elif text == 'else' or text.startswith('elseif '):
            stack.append('if')
    return out

def langs(lines):
    loops = []
    funcs = []
    stack = []
    for line in lines:
        text = line.strip()
        if text in ('end', 'else') or text.startswith('elseif ') or text.startswith('until '):
            if stack:
                stack.pop()
        loops.append(sum(1 for kind in stack if kind == 'loop'))
        funcs.append(sum(1 for kind in stack if kind == 'func'))
        if text.endswith(' then'):
            stack.append('if')
        elif re.search(r'function\s*\([^)]*\)$', text):
            stack.append('func')
        elif text.endswith(' do') or re.search(r'^for .* do$', text):
            stack.append('loop')
        elif text == 'repeat':
            stack.append('loop')
        elif text == 'else' or text.startswith('elseif '):
            stack.append('if')
    return loops, funcs

def loopdepths(lines):
    return langs(lines)[0]

pureval = re.compile(r'(?:[A-Za-z_][A-Za-z0-9_.\[\]"]*|"[^"]*"|-?\d+(?:\.\d+)?|\{\})')

def namesin(text):
    return set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', text))

def readsline(line, name):
    m = assigns(line)
    if m[0] == name:
        return re.search(r'\b' + re.escape(name) + r'\b', m[1] or '') is not None
    return re.search(r'\b' + re.escape(name) + r'\b', line) is not None

def inlinevals(lines):
    for unused in range(60):
        depths, funcs = langs(lines)
        where = paths(lines)
        done = True
        for i, line in enumerate(lines):
            m = re.match(r'^(\s*)local ([A-Za-z_][A-Za-z0-9_]*) = (.+)$', line)
            if not m:
                continue
            name, val = m.group(2), m.group(3)
            if 'function' in val or maybevararg(val) or not pureval.fullmatch(val):
                continue
            reads = []
            firstdef = len(lines)
            shadowed = False
            for j in range(i + 1, len(lines)):
                lhs, rhs = assigns(lines[j])
                if readsline(lines[j], name):
                    reads.append(j)
                if lhs == name:
                    firstdef = j
                    if paths(lines)[j] != paths(lines)[i]:
                        shadowed = True
                    break
            if shadowed:
                continue
            reads = [j for j in reads if j <= firstdef]
            if not reads:
                continue
            if len(reads) != 1:
                continue
            use = reads[0]
            if use == firstdef:
                continue
            if where[use] != where[i]:
                continue
            touched = namesin(val)
            blocked = False
            for j in range(i + 1, use):
                lhs, unused = assigns(lines[j])
                if lhs in touched:
                    blocked = True
                    break
            if blocked:
                continue
            inner = val if re.fullmatch(r'(?:[A-Za-z_][A-Za-z0-9_.\[\]"]*|"[^"]*"|-?\d+(?:\.\d+)?|\{\})', val) else '(' + val + ')'
            lines[use] = subst(lines[use], name, inner)
            del lines[i]
            done = False
            break
        if done:
            break
    return lines

def dropdead(lines):
    out = []
    for line in lines:
        stripped = line.strip()
        if out and out[-1].strip().startswith('return'):
            prev = out[-1]
            if len(prev) - len(prev.lstrip()) == len(line) - len(line.lstrip()):
                continue
        out.append(line)
    return out

assign = re.compile(r'^(\s*)([A-Za-z_][A-Za-z0-9_]*) = (.*)$')

def mergeassign(lines):
    out = list(lines)
    for i in range(len(out) - 1):
        m1 = assign.match(out[i])
        m2 = assign.match(out[i + 1])
        if not m1 or not m2:
            continue
        if m1.group(2) != m2.group(2) or m1.group(1) != m2.group(1):
            continue
        first, name, val = m1.group(1), m1.group(2), m1.group(3)
        rhs = m2.group(3)
        if not rhs.startswith(name):
            continue
        if maybevararg(rhs) or ' = ' in val or re.search(r'\b' + name + r'\b', val):
            continue
        rest = rhs[len(name):]
        if rest and (rest[0] not in '.(['):
            continue
        inner = val if re.fullmatch(r'(?:[A-Za-z_][A-Za-z0-9_.\[\]"]*|"[^"]*"|-?\d+(?:\.\d+)?|\{\})', val) else '(' + val + ')'
        out[i] = first + name + ' = ' + inner + rest
        del out[i + 1]
        return out
    return out

pure = re.compile(r'^(?:[A-Za-z_][A-Za-z0-9_]*|-?\d+(?:\.\d+)?|"[^"]*"|\{\}|true|false|nil|#[A-Za-z_][A-Za-z0-9_]*)$')

def pureexpr(rhs):
    if rhs.strip() == '...' or '...' in rhs:
        return False
    if '(' in rhs or ')' in rhs:
        return False
    for part in rhs.split():
        pass
    return bool(re.fullmatch(r'[A-Za-z0-9_\[\].\"]+', rhs))

def maybevararg(val):
    return val.strip().startswith('...') or ', ...' in val or val.strip() == '...'

def subst(line, name, text):
    lhs, rhs = assigns(line)
    word = re.compile(r'\b' + re.escape(name) + r'\b')
    if lhs == name and rhs is not None:
        return line[:len(line) - len(rhs)] + word.sub(lambda mm: text, rhs, count=1)
    return word.sub(lambda mm: text, line, count=1)

def assigns(line):
    m = re.match(r'^\s*(?:local )?([A-Za-z_][A-Za-z0-9_]*) = (.*)$', line)
    if m:
        return m.group(1), m.group(2)
    return None, None

def copyprop(lines):
    for i, line in enumerate(lines):
        m = assign.match(line)
        if not m:
            continue
        name, val = m.group(2), m.group(3)
        if name == val:
            del lines[i]
            return lines
        if maybevararg(val) or not pureexpr(val) or val in ('nil',):
            continue
        word = re.compile(r'\b' + name + r'\b')
        loops, funcs = langs(lines)
        uses = 0
        defs = 0
        cross = False
        for j, other in enumerate(lines):
            if j != i and word.search(other) and funcs[j] != funcs[i]:
                cross = True
            m2 = assign.match(other)
            if m2 and m2.group(2) == name:
                defs += 1
            if j != i:
                uses += len(word.findall(other))
        if defs != 1 or uses == 0 or cross:
            continue
        inner = val if re.fullmatch(r'(?:[A-Za-z_][A-Za-z0-9_.\[\]"]*|"[^"]*"|-?\d+(?:\.\d+)?)', val) else '(%s)' % val
        for j in range(len(lines)):
            if j == i:
                continue
            lines[j] = subst(lines[j], name, inner)
        del lines[i]
        return lines
    return lines

def addlocals(lines):
    stack = [(-1, set())]
    out = []
    for line in lines:
        indent = len(line) - len(line.lstrip())
        while len(stack) > 1 and indent < stack[-1][0]:
            stack.pop()
        text = line.strip()
        if text.startswith(('if ', 'elseif ', 'else')):
            out.append(line)
            continue
        decl = re.match(r'^\s*local ([A-Za-z_][A-Za-z0-9_]*)( = .*)?$', line)
        if decl:
            stack[-1][1].add(decl.group(1))
            out.append(line)
            continue
        m = assign.match(line)
        if m:
            name = m.group(2)
            head = line
            outer = any(name in seen for unused, seen in stack[:-1])
            if name not in stack[-1][1] and not outer:
                stack[-1][1].add(name)
                head = m.group(1) + 'local ' + line.strip()
            out.append(head)
            if line.rstrip().endswith(')') and ' function(' in line:
                stack.append((indent + 2, set()))
            continue
        out.append(line)
    return out

fnhead = re.compile(r'^(\s*)(?:local )?([A-Za-z_][A-Za-z0-9_]*) = function\(')
fnhead2 = re.compile(r'^(\s*)local function ([A-Za-z_][A-Za-z0-9_]*)\(')

def enclosingfunction(lines, i, where=None):
    if where is None:
        where = paths(lines)
    outer = where[i][:-1]
    for k in range(i - 1, -1, -1):
        if where[k] != outer:
            continue
        m = fnhead.match(lines[k]) or fnhead2.match(lines[k])
        if m:
            return m.group(2), k
    return None, -1

def fnname(lines, i):
    fn, unused = enclosingfunction(lines, i)
    return fn

def dedent(line):
    return line[2:] if line.startswith('  ') else line

def unshackle(lines):
    lines = list(lines)
    for unused in range(8):
        where = paths(lines)
        hit = None
        for i, line in enumerate(lines):
            text = line.strip()
            if not text.startswith('if ') or not text.endswith(' then'):
                continue
            base = where[i]
            elseat = None
            endat = None
            j = i + 1
            while j < len(lines):
                here = lines[j].strip()
                if where[j] == base and here == 'else' and elseat is None:
                    elseat = j
                elif where[j] == base and here == 'end':
                    endat = j
                    break
                j += 1
            if elseat is None or endat is None:
                continue
            body = [k for k in range(elseat + 1, endat) if lines[k].strip()]
            taken = [k for k in range(i + 1, elseat) if lines[k].strip()]
            if not body or not taken:
                continue
            call = None
            for k in reversed(body):
                text = lines[k].strip()
                hitline = re.match(r'return ([A-Za-z_][A-Za-z0-9_]*)\(', text)
                if hitline:
                    call = hitline
                    break
                if not re.match(r'^return\b[^()]*$', text):
                    break
            if not call:
                continue
            name = call.group(1)
            fn, start = enclosingfunction(lines, i, where)
            alias = False
            for k in list(body) + list(range(start, i)):
                lhs, rhs = assigns(lines[k])
                if lhs == name and rhs is not None and rhs.strip() == (fn or ''):
                    alias = True
            if fn is None:
                continue
            if name != fn and not alias:
                continue
            if not any((':%d' in lines[k]) or ('pcall(' in lines[k]) for k in range(start, i)):
                continue
            hit = (i, elseat, endat, taken)
            break
        if hit is None:
            break
        i, elseat, endat, taken = hit
        cond = lines[i].strip()[3:-5]
        fn, start = enclosingfunction(lines, i, where)
        block = [dedent(lines[k]) for k in taken]
        head = dropprobe(lines[:i], start, i, cond)
        lines = head + block + lines[endat + 1:]
    return lines

pureatom = re.compile(r'(?:[A-Za-z_][A-Za-z0-9_.]*|"[^"]*"|-?\d+(?:\.\d+)?|\{\}|true|false|nil)')

def droppure(lines):
    for unused in range(8):
        where = paths(lines)
        changed = False
        for i, line in enumerate(lines):
            m = re.match(r'^\s*local ([A-Za-z_][A-Za-z0-9_]*) = (.+)$', line)
            if not m:
                continue
            name, val = m.group(1), m.group(2)
            if not pureatom.fullmatch(val):
                continue
            used = any(re.search(r'\b' + re.escape(name) + r'\b', other)
                       for j, other in enumerate(lines) if j != i)
            if used:
                continue
            del lines[i]
            changed = True
            break
        if not changed:
            break
    return lines

def dropprobe(lines, start, stop, cond):
    defs = {}
    for k in range(start + 1, stop):
        lhs, rhs = assigns(lines[k])
        if lhs is None or 'function' in (rhs or ''):
            continue
        defs.setdefault(lhs, []).append(k)
    drop = set()
    pending = [n for n in namesin(cond)]
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen or name not in defs:
            continue
        seen.add(name)
        for k in defs[name]:
            drop.add(k)
            pending.extend(namesin(assigns(lines[k])[1] or ''))
    if not drop:
        return lines
    return [line for k, line in enumerate(lines) if k not in drop]

def numlit(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value != value:
        return '(0/0)'
    if value in (float('inf'), float('-inf')):
        return '(1/0)' if value > 0 else '(-1/0)'
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return repr(value)

prefix2 = 'abcdefghijklmnopqrstuvwxyz'

class lifter2:
    def __init__(self, isa, magic, level=0):
        self.isa = isa
        self.magic = magic
        self.lines = []
        self.counter = 0
        self.depth = 0
        self.level = level
        self.prefix = prefix2[min(level, len(prefix2) - 1)]
        self.unknown = []

    def newname(self):
        name = '%s%d' % (self.prefix, self.counter)
        self.counter += 1
        return name

    def reg(self, idx):
        if not isinstance(idx, (int, float)) or isinstance(idx, bool):
            return 'nil'
        idx = int(idx)
        while len(self.names) <= idx:
            self.names.append(None)
        if self.names[idx] is None:
            self.names[idx] = '%s%d' % (self.prefix, idx)
        return self.names[idx]

    def kind(self, ins):
        info = self.isa.get(ins.op)
        if info is None:
            return ('UNKNOWN',)
        return info

    def oper(self, ins, which):
        if which == 'b':
            value, flag = ins.b, ins.bf
        else:
            value, flag = ins.c, ins.cf
        if value is None:
            return None
        if flag:
            if isinstance(value, str):
                return strlit(value)
            if isinstance(value, bool):
                return 'true' if value else 'false'
            return numlit(value)
        return self.reg(value)

    def emitline(self, txt):
        self.lines.append('  ' * self.depth + txt)
        self.counted = getattr(self, 'counted', 0) + 1

    def touch(self, idx):
        if isinstance(idx, (int, float)) and not isinstance(idx, bool):
            self.topreg = max(self.topreg, int(idx))

    def isgoto(self, ins, idx):
        k = self.kind(ins)[0]
        return k == 'JMP'

    def target(self, ins):
        return min(int(ins.b) + 1, len(self.instrs) + 1)

    def body(self, proto, upvals=None, params=None, counter=None):
        self.proto = proto
        self.instrs = proto.instrs
        self.names = []
        self.remap = {}
        self.fixed = params is not None
        self.upvals = upvals or []
        if counter is not None:
            self.counter = counter
        if params:
            for nm in params:
                self.names.append(nm)
                self.remap[len(self.names) - 1] = nm
        self.maxreg = 0
        self.topreg = -1
        self.vargname = None
        self.varbase = 10 ** 6
        self.vararg = False
        for ins in self.instrs:
            for value, flag in ((ins.a, ins.af), (ins.b, ins.bf), (ins.c, ins.cf)):
                if isinstance(value, (int, float)) and not isinstance(value, bool) and not flag:
                    self.maxreg = max(self.maxreg, int(value))
        self.run(1, len(self.instrs) + 1, None)
        self.vararg = any(self.kind(ins)[0] in ('VARARG', 'VARARGT') for ins in self.instrs)
        return self.lines

    def jumptrue(self, kind):
        return kind in ('TESTNOT', 'NGTRR', 'NLT')

    def iscond(self, kind):
        return kind in ('TEST', 'TESTNOT', 'EQ', 'LE', 'LT', 'LTRR', 'LERR', 'NLT', 'NE', 'NGTRR')

    def isjmp(self, ins):
        return self.kind(ins)[0] == 'JMP'

    def condat(self, idx):
        if 1 <= idx <= len(self.instrs):
            return self.instrs[idx - 1]
        return None

    def run(self, start, stop, loopend):
        self.block(start, stop, loopend)
        return stop + 1

    def repeatend(self, start, stop):
        for j in range(start + 1, stop + 1):
            ins = self.condat(j)
            if ins is not None and self.iscond(self.kind(ins)[0]) and self.target(ins) == start:
                return j
        return None

    def block(self, start, stop, loopend=None):
        end = self.repeatend(start, stop)
        if end is not None:
            ins = self.condat(end)
            kind = self.kind(ins)[0]
            self.emitline('repeat')
            self.depth += 1
            self.block(start, end - 1, end)
            self.depth -= 1
            self.emitline('until %s' % self.condtext(ins, kind))
            self.block(end + 2, stop, loopend)
            return
        i = start
        guard = 0
        while i <= stop and 1 <= i <= len(self.instrs):
            guard += 1
            if guard > 20000:
                break
            i = self.node(i, stop, loopend)

    def node(self, i, stop, loopend):
        ins = self.instrs[i - 1]
        kind = self.kind(ins)[0]
        if kind == 'TESTORT':
            default = self.condat(i + 1)
            value = None
            if default is not None and self.kind(default)[0] == 'SETB':
                value = self.oper(default, 'b')
            elif default is not None:
                value = self.simple(default, self.kind(default)[0])
                if not isinstance(value, str):
                    value = None
            self.emitline('%s = %s or %s' % (self.reg(ins.a), self.reg(ins.c), value or 'nil'))
            return i + 3
        if self.iscond(kind):
            fast = self.boolpair(i, ins, kind)
            if fast is not None:
                return fast
            return self.cond(i, ins, kind, stop, loopend)
        if kind == 'JMP':
            tgt = self.target(ins)
            step = self.condat(tgt)
            if step is not None and self.kind(step)[0] == 'TFORSTEP':
                return self.genfor(i, step, tgt, stop)
            if loopend is not None and tgt == loopend:
                self.emitline('break')
                return i + 1
            if tgt <= i or tgt > stop + 1:
                return i + 1
            return tgt
        if kind == 'FORPREP':
            return self.forloop(i, ins)
        if kind == 'CLOSURE':
            return self.closure(i, ins)
        if kind in ('RETT', 'RETN', 'RET0', 'RET1', 'RET2', 'TAIL0', 'TAILN', 'TAILT'):
            self.emitline(self.retline(ins, kind))
            return i + 1
        if kind in ('CALLMN', 'CALLM0', 'CALLM1', 'CALLMT'):
            after = self.condat(i + 1)
            if (after is not None and self.kind(after)[0] in ('APPEND', 'PUSHTOP')
                    and self.intof(ins.a) == self.intof(after.a) + 1):
                return self.capture(i, ins, kind, after)
        self.skipnext = False
        line = self.simple(ins, kind)
        if isinstance(line, list):
            for part in line:
                self.emitline(part)
        elif line:
            self.emitline(line)
        if getattr(self, 'skipnext', False):
            self.skipnext = False
            return i + 2
        return i + 1

    def boolpair(self, i, ins, kind):
        t = self.target(ins)
        skip = self.condat(i + 1)
        if skip is None or not self.isjmp(skip):
            return None
        j = self.target(skip)
        if j <= i or t <= i or min(t, j) > len(self.instrs):
            return None
        one = self.condat(t)
        two = self.condat(j)
        if one is None or two is None:
            return None
        if self.kind(one)[0] != 'LOADBOOL' or self.kind(two)[0] != 'LOADBOOL':
            return None
        if self.intof(one.a) != self.intof(two.a):
            return None
        truth = {}
        for node in (one, two):
            truth[id(node)] = self.intof(node.b) != 0
        if truth[id(one)] == truth[id(two)]:
            return None
        tside = truth[id(one)]
        jt = self.jumptrue(kind)
        valueontrue = tside if jt else (not tside)
        text = self.condtext(ins, kind)
        if not valueontrue:
            text = 'not (%s)' % text
        self.emitline('%s = %s' % (self.reg(self.intof(one.a)), text))
        return max(t, j) + 1

    def cond(self, i, ins, kind, stop, loopend):
        tgt = self.target(ins)
        cond = self.condtext(ins, kind)
        pad = self.condat(i + 1)
        fall = i + 2
        if not (pad is not None and self.isjmp(pad) and self.target(pad) == tgt):
            fall = i + 1
        if tgt <= i:
            return self.backcond(i, ins, kind, stop)
        if tgt <= fall or tgt > stop + 2:
            return min(fall, i + 1)
        bodyend = tgt - 1
        tail = self.condat(tgt - 1)
        if self.isjmp(tail) and self.target(tail) == i:
            self.emitline('while %s do' % cond)
            self.depth += 1
            self.block(fall, tgt - 2, tgt)
            self.depth -= 1
            self.emitline('end')
            return tgt
        if self.isjmp(tail) and self.target(tail) > tgt:
            join = self.target(tail)
            if self.jumptrue(kind):
                first, second = (tgt, join - 1), (fall, tgt - 2)
            else:
                first, second = (fall, tgt - 2), (tgt, join - 1)
            self.emitline('if %s then' % cond)
            self.depth += 1
            self.block(first[0], first[1], loopend)
            self.depth -= 1
            self.emitline('else')
            self.depth += 1
            self.block(second[0], second[1], loopend)
            self.depth -= 1
            self.emitline('end')
            return join
        head = 'if %s then' % cond if not self.jumptrue(kind) else 'if not (%s) then' % cond
        self.emitline(head)
        self.depth += 1
        self.block(fall, bodyend, loopend)
        self.depth -= 1
        self.emitline('end')
        return tgt

    def backcond(self, i, ins, kind, stop):
        tgt = max(1, self.target(ins))
        cond = self.condtext(ins, kind)
        self.emitline('repeat')
        self.depth += 1
        self.block(tgt, i - 1)
        self.depth -= 1
        self.emitline('until %s' % cond)
        return i + 2

    def arglist(self, ins):
        kind = self.kind(ins)[0]
        base = self.intof(ins.a) + 1
        if kind.endswith('T'):
            high = self.topreg
        elif kind == 'CALL1V':
            high = base
        else:
            cands = []
            for value, flag in ((ins.b, ins.bf), (ins.c, ins.cf)):
                if isinstance(value, (int, float)) and not isinstance(value, bool) and not flag:
                    if int(value) >= base:
                        cands.append(int(value))
            high = max(cands) if cands else self.topreg
        if high < base:
            return ''
        if self.vargname is not None and high >= self.varbase:
            plain = [self.reg(k) for k in range(base, self.varbase)]
            plain.append('unpack(%s)' % self.vargname)
            return ', '.join(plain)
        return ', '.join(self.reg(k) for k in range(base, high + 1))

    def retline(self, ins, kind):
        if kind == 'RET0':
            return 'return'
        if kind == 'TAIL0':
            return 'return %s()' % self.reg(ins.a)
        if kind in ('TAILN', 'TAILT'):
            return 'return %s(%s)' % (self.reg(ins.a), self.arglist(ins))
        if kind == 'RETT':
            high = max(int(ins.a), self.topreg)
            return 'return %s' % ', '.join(self.reg(k) for k in range(int(ins.a), high + 1))
        if kind == 'RET2':
            return 'return %s, %s' % (self.reg(ins.a), self.reg(self.intof(ins.a) + 1))
        if kind == 'RET1':
            return 'return %s' % self.reg(ins.a)
        if kind == 'RETN':
            high = int(ins.a) + self.intof(ins.b)
            return 'return %s' % ', '.join(self.reg(k) for k in range(int(ins.a), high + 1))
        return 'return %s' % self.reg(ins.a)

    def rawval(self, value):
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, (int, float)):
            return numlit(value)
        if isinstance(value, str):
            return strlit(value)
        return 'nil'

    def condtext(self, ins, kind):
        if kind == 'TESTORT':
            self.emitline('%s = %s or %s' % (self.reg(ins.a), self.reg(ins.b), self.constof(ins, 'c')))
            return i + 2
        if kind == 'TEST':
            return self.reg(ins.a)
        if kind == 'TESTNOT':
            return self.reg(ins.a)
        if kind == 'LE':
            return '%s <= %s' % (self.reg(ins.a), self.constof(ins, 'c'))
        if kind == 'LT':
            return '%s < %s' % (self.reg(ins.a), self.constof(ins, 'c'))
        if kind == 'NGTRR':
            return '%s < %s' % (self.reg(ins.a), self.reg(ins.c))
        if kind == 'LTRR':
            return '%s < %s' % (self.reg(ins.a), self.reg(ins.c))
        if kind == 'LERR':
            return '%s <= %s' % (self.reg(ins.a), self.reg(ins.c))
        if kind == 'NLT':
            return '%s < %s' % (self.rawval(ins.a), self.rawval(ins.c))
        if kind == 'NE':
            return '%s ~= %s' % (self.rawval(ins.a), self.rawval(ins.c))
        return '%s == %s' % (self.reg(ins.a), self.oper(ins, 'c'))

    def capture(self, i, ins, kind, after):
        a = self.intof(ins.a)
        target = self.intof(after.a)
        args = self.reg(a + 1) if kind == 'CALLM1' else self.arglist(ins)
        self.emitline('%s = {%s(%s)}' % (self.reg(target), self.reg(a), args))
        self.topreg = target
        return i + 2

    def genfor(self, i, step, tgt, stop):
        a = self.intof(step.a)
        count = self.intof(step.c)
        vars = ', '.join(self.reg(a + 3 + k) for k in range(max(1, count)))
        exprs = ', '.join(self.reg(a + k) for k in range(3))
        self.emitline('for %s in %s do' % (vars, exprs))
        self.depth += 1
        self.block(i + 1, tgt - 1, tgt)
        self.depth -= 1
        self.emitline('end')
        return tgt + 2

    def forloop(self, i, ins):
        a = int(ins.a)
        tgt = self.target(ins)
        end = None
        for j in range(i + 1, min(tgt + 2, len(self.instrs) + 1)):
            cand = self.instrs[j - 1]
            if self.kind(cand)[0] == 'FORLOOP' and self.target(cand) == i + 1:
                end = j
                break
        if end is None:
            end = tgt - 1
        self.emitline('for %s = %s, %s, %s do' % (self.reg(a + 3), self.reg(a), self.reg(a + 1), self.reg(a + 2)))
        self.depth += 1
        self.run(i + 1, end, tgt)
        self.depth -= 1
        self.emitline('end')
        return tgt

    def closure(self, i, ins):
        count = int(ins.c) if isinstance(ins.c, (int, float)) and not isinstance(ins.c, bool) else 0
        ups = []
        for k in range(count):
            desc = self.instrs[i + k] if i + k < len(self.instrs) else None
            if desc is None:
                ups.append('nil')
                continue
            if self.kind(desc)[0] == 'MOVE':
                ups.append(self.reg(desc.b))
            else:
                idx = self.intof(desc.b)
                if 0 <= idx < len(self.upvals):
                    ups.append(self.upvals[idx])
                else:
                    ups.append('nil')
        idx = int(ins.b) if isinstance(ins.b, (int, float)) and not isinstance(ins.b, bool) else 0
        kid = self.proto.kids[idx] if idx < len(self.proto.kids) else None
        if kid is None:
            self.emitline('%s = nil' % self.reg(ins.a))
            return i + count + 1
        sub = lifter2(self.isa, self.magic, self.level + 1)
        pnames = ['%s%d' % (sub.prefix, k) for k in range(kid.params)]
        sub.lines = self.lines
        sub.depth = self.depth + 1
        mark = len(self.lines)
        sub.body(kid, ups, pnames)
        if sub.vararg:
            pnames.append('...')
        name = self.reg(ins.a)
        word = re.compile(r'\b' + re.escape(name) + r'\b')
        recursive = any(word.search(line) for line in self.lines[mark:])
        head = '  ' * self.depth + '%s = function(%s)' % (name, ', '.join(pnames))
        self.lines.insert(mark, head)
        if recursive:
            self.lines.insert(mark, '  ' * self.depth + 'local ' + name)
        self.lines.append('  ' * self.depth + 'end')
        return i + count + 1

    def simple(self, ins, kind):
        a = int(ins.a) if isinstance(ins.a, (int, float)) and not isinstance(ins.a, bool) else None
        if a is None:
            return None
        self.touch(a)
        self.topreg = max(self.topreg, a)
        if kind == 'SETB':
            return '%s = %s' % (self.reg(a), self.oper(ins, 'b'))
        if kind == 'MOVE':
            return '%s = %s' % (self.reg(a), self.reg(ins.b))
        if kind == 'LOADG':
            return '%s = %s' % (self.reg(a), self.globtext(ins))
        if kind == 'GETTAB':
            return '%s = %s' % (self.reg(a), self.indextext(self.reg(ins.b), ins, 'c'))
        if kind == 'SETTAB':
            return '%s = %s' % (self.indextext(self.reg(ins.a), ins, 'b'), self.oper(ins, 'c'))
        if kind == 'SETTABR':
            return '%s[%s] = %s' % (self.reg(a), self.reg(ins.b), self.reg(ins.c))
        if kind == 'NEWTAB':
            return '%s = {}' % self.reg(a)
        if kind == 'LEN':
            return '%s = #%s' % (self.reg(a), self.reg(ins.b))
        if kind == 'MOD':
            return '%s = %s %% %s' % (self.reg(a), self.reg(ins.b), self.oper(ins, 'c'))
        if kind == 'MODK':
            return '%s = %s %% %s' % (self.reg(a), self.reg(ins.b), self.oper(ins, 'c'))
        if kind == 'ADDK':
            return '%s = %s + %s' % (self.reg(a), self.addleft(ins), self.addright(ins))
        if kind == 'CALL1V':
            return '%s(%s)' % (self.reg(a), self.reg(a + 1))
        if kind in ('CALLVT', 'CALLVN'):
            return '%s(%s)' % (self.reg(a), self.arglist(ins))
        if kind in ('CALLNT', 'CALLNN'):
            return '%s = %s(%s)' % (self.reg(a), self.reg(a), self.arglist(ins))
        if kind == 'CALLN1':
            return '%s = %s(%s)' % (self.reg(a), self.reg(a), self.reg(a + 1))
        if kind == 'FILLNIL':
            low = a
            high = ins.b if isinstance(ins.b, (int, float)) and not isinstance(ins.b, bool) else a
            return '%s = nil' % self.reg(low) if int(high) <= low else '%s = nil' % self.reg(low)
        if kind in ('APPEND', 'PUSHTOP'):
            low = a + 1
            high = self.topreg if self.topreg >= low else low
            return ['table.insert(%s, %s)' % (self.reg(a), self.reg(k)) for k in range(low, high + 1)]
        if kind == 'SETLIST':
            count = self.intof(ins.b)
            base = a
            parts = ['%s[%d] = %s' % (self.reg(base), i, self.reg(base + i)) for i in range(1, count + 1)]
            return parts
        if kind == 'PUSHRANGE':
            count = self.intof(ins.b) - a
            parts = ['%s[%d] = %s' % (self.reg(a), i, self.reg(a + i)) for i in range(1, count + 1)]
            return parts
        if kind == 'LOADBOOL':
            value = ins.b
            truth = True if isinstance(value, bool) else (self.intof(value) != 0)
            self.skipnext = self.intof(ins.c) != 0
            return '%s = %s' % (self.reg(a), 'true' if truth else 'false')
        if kind == 'LOADGX':
            return '%s = %s' % (self.reg(a), self.globtext(ins))
        if kind == 'SETG':
            return '%s = %s' % (self.globtext(ins), self.reg(a))
        if kind == 'CONCAT':
            low = self.intof(ins.b)
            high = self.intof(ins.c)
            if high < low:
                high = low
            return '%s = %s' % (self.reg(a), ' .. '.join(self.reg(k) for k in range(low, high + 1)))
        if kind in ('SUBK', 'MULK', 'ADDK', 'MODK'):
            op = {'SUBK': '-', 'MULK': '*', 'ADDK': '+', 'MODK': '%'}[kind]
            return '%s = %s %s %s' % (self.reg(a), self.reg(ins.b), op, self.constof(ins, 'c'))
        if kind in ('SUB',):
            return '%s = %s - %s' % (self.reg(a), self.reg(ins.b), self.reg(ins.c))
        if kind in ('ADD', 'MUL', 'MOD'):
            op = {'ADD': '+', 'SUB': '-', 'MUL': '*', 'MOD': '%'}[kind]
            return '%s = %s %s %s' % (self.reg(a), self.reg(ins.b), op, self.constof(ins, 'c'))
        if kind == 'SELF':
            obj = self.reg(ins.b)
            self.emitline('%s = %s' % (self.reg(a + 1), obj))
            self.emitline('%s = %s%s' % (self.reg(a), obj, self.keytext(ins, 'c')))
            return None
        if kind == 'CALL00':
            return '%s = %s()' % (self.reg(a), self.reg(a))
        if kind == 'CALLM1N':
            high = self.intof(ins.c)
            if high < a:
                high = a
            last = self.intof(ins.b)
            if last <= a:
                last = a + 1
            args = ', '.join(self.reg(k) for k in range(a + 1, last + 1))
            self.topreg = high
            targets = ', '.join(self.reg(k) for k in range(a, high + 1))
            return '%s = %s(%s)' % (targets, self.reg(a), args)
        if kind in ('CALLM0', 'CALLM1', 'CALLMT', 'CALLMN'):
            args = self.reg(a + 1) if kind == 'CALLM1' else self.arglist(ins)
            self.topreg = a
            return '%s = %s(%s)' % (self.reg(a), self.reg(a), args)
        if kind in ('VARARG', 'VARARGT'):
            if self.vargname is None:
                self.vargname = 'v' + self.prefix + 'arg'
            self.varbase = a
            self.vararg = True
            return 'local %s = {...}' % self.vargname
        return None

    def keytext(self, ins, which):
        value = ins.c if which == 'c' else ins.b
        flag = ins.cf if which == 'c' else ins.bf
        if flag and isinstance(value, str):
            return '.' + value if isident(value) else '[' + strlit(value) + ']'
        return '[' + self.constof(ins, which) + ']'

    def intof(self, value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
        return 0

    def constof(self, ins, which):
        value = ins.c if which == 'c' else ins.b
        flag = ins.cf if which == 'c' else ins.bf
        if flag:
            if isinstance(value, str):
                return strlit(value)
            if isinstance(value, bool):
                return 'true' if value else 'false'
            return numlit(value)
        return self.reg(value)

    def globtext(self, ins):
        value = ins.b
        if isinstance(value, str):
            return value if isident(value) else '_ENV[%s]' % strlit(value)
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, (int, float)):
            idx = int(value)
            if 0 <= idx < len(self.upvals):
                return self.upvals[idx]
            return 'nil'
        return 'nil'

    def indextext(self, base, ins, which):
        value, flag = (ins.b, ins.bf) if which == 'b' else (ins.c, ins.cf)
        if flag and isinstance(value, str):
            if isident(value):
                return base + '.' + value
            return base + '[' + strlit(value) + ']'
        return base + '[' + self.oper(ins, which) + ']'

    def addleft(self, ins):
        return self.oper(ins, 'b') if not ins.bf else self.oper(ins, 'b')

    def addright(self, ins):
        return self.oper(ins, 'c')
