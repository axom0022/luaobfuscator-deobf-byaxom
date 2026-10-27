import re
import struct

blob2 = re.compile(r'"(LOL![0-9A-Fa-fQ]+)"')

constbool, constnum, conststr = 1, 2, 3

oploadk = 0
opcallm = 1
opnewtab = 2
opcall = 3
opreturn = 4
opcall0 = 5
opgettab = 6
oprun = 7
oploadg = 8

def findblob(code):
    m = blob2.search(code)
    return m.group(1) if m else None

def undehex(blob):
    data = blob[4:]
    out = bytearray()
    repeat = 0
    for i in range(0, len(data) - 1, 2):
        pair = data[i:i + 2]
        if pair[1] in 'Qq':
            repeat = int(pair[0], 16)
            continue
        byte = int(pair, 16)
        if repeat:
            out.extend([byte] * repeat)
            repeat = 0
        else:
            out.append(byte)
    return bytes(out)

class reader2:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, n):
        chunk = self.data[self.pos:self.pos + n]
        if len(chunk) != n:
            raise ValueError('truncated payload')
        self.pos += n
        return chunk

    def u8(self):
        return self.take(1)[0]

    def u16(self):
        return struct.unpack('<H', self.take(2))[0]

    def u32(self):
        return struct.unpack('<I', self.take(4))[0]

    def f64(self):
        low = self.u32()
        high = self.u32()
        return struct.unpack('<d', struct.pack('<II', low, high))[0]

    def string(self):
        return self.take(self.u32())

    def const(self):
        kind = self.u8()
        if kind == constbool:
            return self.u8() != 0
        if kind == constnum:
            return self.f64()
        if kind == conststr:
            return self.string().decode('latin-1')
        raise ValueError('unknown constant kind %d' % kind)

def descriptor(value):
    return {'bconst': bool(value & 0x10), 'cconst': bool(value & 0x20)}

def proto(reader):
    nconsts = reader.u32()
    consts = [reader.const() for unused in range(nconsts)]
    nparams = reader.u8()
    ninstr = reader.u32()
    instrs = []
    for unused in range(ninstr):
        desc = reader.u8()
        op = reader.u16()
        a = reader.u16()
        b = reader.u16()
        c = reader.u16()
        flags = descriptor(desc)
        instrs.append({
            'op': op,
            'a': a,
            'b': consts[b - 1] if flags['bconst'] and 0 < b <= len(consts) else b,
            'c': consts[c - 1] if flags['cconst'] and 0 < c <= len(consts) else c,
            'bconst': flags['bconst'],
            'cconst': flags['cconst'],
        })
    nkids = reader.u32()
    kids = [proto(reader) for unused in range(nkids)]
    return {'consts': consts, 'params': nparams, 'instrs': instrs, 'kids': kids}

def parse(code):
    blob = findblob(code)
    if not blob:
        return None
    try:
        return proto(reader2(undehex(blob)))
    except (ValueError, IndexError, struct.error):
        return None

def looks(code):
    blob = findblob(code)
    if not blob or 'Q' not in blob:
        return False
    return ('getfenv' in code or '_ENV' in code) and 'sub' in code

class lifter2:

    def __init__(self):
        self.lines = []
        self.vals = {}
        self.selfof = {}
        self.notes = []

    def emit(self, text):
        self.lines.append(text)

    def expr(self, reg):
        return self.vals.get(reg, 'r%d' % reg)

    def literal(self, ins, which):
        value = ins[which]
        if ins[which + 'const']:
            if isinstance(value, bool):
                return 'true' if value else 'false'
            if isinstance(value, str):
                return stringlit(value)
            return numlit(value)
        return self.expr(value)

    def globalof(self, ins):
        name = ins['b']
        if ins['bconst'] and isinstance(name, str) and ident(name):
            return name
        return 'env[%s]' % self.literal(ins, 'b')

    def key(self, ins):
        key = ins['c']
        if ins['cconst'] and isinstance(key, str) and ident(key):
            return '.' + key
        return '[%s]' % self.literal(ins, 'c')

    window2 = 8

    def readlater(self, reg):
        return self.upcoming is not None and any(
            reg in effect(ins)[0] for ins in self.upcoming)

    def results(self, instrs, i, a):
        seen = 0
        for ins in instrs[i + 1:]:
            reads, writes = effect(ins)
            for reg in reads:
                if a <= reg <= a + self.window2:
                    seen = max(seen, reg - a + 1)
            if any(a <= reg <= a + self.window2 for reg in writes):
                break
            if ins['op'] == opreturn:
                break
        return seen

    def calltext(self, targetreg, argregs):
        target = self.expr(targetreg)
        args = [self.expr(r) for r in argregs]
        owner = self.selfof.get(targetreg)
        field = None
        if owner is not None and target.startswith(owner):
            field = target[len(owner):]
        if field and args and args[0] == owner:
            base = prefix(owner)
            if field.startswith('.') and ident(field[1:]):
                return '%s:%s(%s)' % (base, field[1:], ', '.join(args[1:]))
            return '%s%s(%s)' % (base, field, ', '.join(args))
        return '%s(%s)' % (prefix(target), ', '.join(args))

    def emitcall(self, reg, text):
        if self.readlater(reg):
            name = 'r%d' % reg
            self.emit('local %s = %s' % (name, text))
            self.vals[reg] = name
        else:
            self.emit(text)
            self.vals.pop(reg, None)
        self.selfof.pop(reg, None)

    def body(self, proto):
        instrs = proto['instrs']
        i = 0
        while i < len(instrs):
            ins = instrs[i]
            op = ins['op']
            a = ins['a']
            if op == oploadk:
                self.vals[a] = self.literal(ins, 'b')
                self.selfof.pop(a, None)
            elif op == oploadg:
                self.vals[a] = self.globalof(ins)
                self.selfof.pop(a, None)
            elif op == opnewtab:
                self.vals[a] = '{}'
                self.selfof.pop(a, None)
            elif op == opgettab:
                obj = self.expr(ins['b'])
                self.vals[a] = obj + self.key(ins)
                self.selfof[a] = obj
                self.vals[a + 1] = obj
                self.selfof.pop(a + 1, None)
            elif op == oprun:
                i = self.superinstr(instrs, i)
                continue
            elif op == opcallm:
                last = ins['b'] if isinstance(ins['b'], int) else a + 1
                self.lastcallm = a
                text = self.calltext(a, list(range(a + 1, last + 1)))
                self.upcoming = instrs[i + 1:]
                nxtop = instrs[i + 1] if i + 1 < len(instrs) else None
                nxt = nxtop['op'] if nxtop else None
                if nxt == opcall and nxtop['a'] + 1 == a:
                    self.forwarded = (a, text)
                    for reg in range(a, last + 1):
                        self.vals.pop(reg, None)
                        self.selfof.pop(reg, None)
                elif nxt == opcall:
                    raw = 'raw%d' % a
                    self.emit('local %s = {%s}' % (raw, text))
                    self.captured = (a, last, raw, text)
                    for reg in range(a, last + 1):
                        self.vals.pop(reg, None)
                        self.selfof.pop(reg, None)
                else:
                    count = self.results(instrs, i, a)
                    if count <= 0:
                        self.emit(text)
                        self.vals.pop(a, None)
                        self.selfof.pop(a, None)
                    else:
                        names = ', '.join(self.fresh(a, k) for k in range(count))
                        self.emit('local %s = %s' % (names, text))
                    for reg in range(a, last + 1):
                        self.vals.pop(reg, None)
                        self.selfof.pop(reg, None)
            elif op == opcall:
                self.upcoming = instrs[i + 1:]
                if self.forwarded and self.forwarded[0] == self.lastcallm:
                    self.captured = None
                    text = '%s(%s)' % (prefix(self.expr(a)), self.forwarded[1])
                    self.forwarded = None
                elif self.captured and self.captured[0] > a:
                    first, last, raw, original = self.captured
                    self.captured = None
                    start = a + 2 - first
                    if start == 1:
                        text = '%s(%s)' % (prefix(self.expr(a)), original)
                    else:
                        text = '%s(unpack(%s, %d))' % (prefix(self.expr(a)), raw, start)
                else:
                    top = self.tops[-1] if self.tops else a
                    text = self.calltext(a, list(range(a + 1, top + 1)))
                self.emitcall(a, text)
            elif op == opcall0:
                self.emit('%s()' % self.expr(a))
            elif op == opreturn:
                if not self.lines or self.lines[-1] != 'return':
                    self.emit('return')
            else:
                self.notes.append('opcode %d not handled' % op)
            i += 1

    def fresh(self, a, k):
        name = 'r%d' % (a + k)
        self.vals[a + k] = name
        return name

    tops = None

    def superinstr(self, instrs, i):
        window = instrs[i:i + 9]
        if len(window) < 9:
            self.notes.append('truncated super instruction')
            return len(instrs)
        newtab, load1, load2, field, loadk, callm, call, call0 = window[:8]
        clean = self.idiom(newtab, load1, load2, field, loadk, callm, call, call0)
        if clean is not None:
            for line in clean:
                self.emit(line)
            return i + 9
        self.notes.append('unfamiliar run sequence, rendered by register')
        self.vals[newtab['a']] = '{}'
        self.vals[load1['a']] = self.globalof(load1)
        self.vals[load2['a']] = self.globalof(load2)
        obj = self.expr(field['b'])
        self.vals[field['a']] = obj + self.key(field)
        self.selfof[field['a']] = obj
        self.vals[field['a'] + 1] = obj
        self.vals[loadk['a']] = self.literal(loadk, 'b')
        last = callm['b'] if isinstance(callm['b'], int) else callm['a'] + 1
        top = callm['a']
        self.upcoming = instrs[i + 9:]
        text = self.calltext(callm['a'], list(range(callm['a'] + 1, last + 1)))
        textofcall = text
        capture = 'raw%d' % callm['a']
        if call['a'] + 2 - top != 1:
            self.emit('local %s = {%s}' % (capture, text))
        for reg in range(callm['a'], last + 1):
            self.vals.pop(reg, None)
            self.selfof.pop(reg, None)
        self.vals[callm['a']] = '%s[1]' % capture
        self.upcoming = instrs[i + 9:]
        target = self.expr(call['a'])
        start = call['a'] + 2 - top
        if start == 1:
            text = '%s(%s)' % (prefix(target), textofcall)
        else:
            text = '%s(unpack(%s, %d))' % (prefix(target), capture, start)
        name = 'r%d' % call['a']
        self.emit('local %s = %s' % (name, text))
        self.vals[call['a']] = name
        self.emit('%s()' % prefix(self.expr(call0['a'])))
        self.emit('return')
        return i + 9

    def idiom(self, newtab, load1, load2, field, loadk, callm, call, call0):
        if not (load1['bconst'] and load2['bconst'] and field['cconst'] and loadk['bconst']):
            return None
        callee = load1['b']
        target = load2['b']
        method = field['c']
        arg = loadk['b']
        if not all(isinstance(v, str) and ident(v) for v in (callee, target, method)):
            return None
        if field['b'] != load2['a'] or loadk['a'] != callm['b'] or callm['a'] != field['a']:
            return None
        if call['a'] != load1['a'] or call0['a'] != call['a']:
            return None
        argtext = stringlit(arg) if isinstance(arg, str) else numlit(arg)
        return [
            'local url = %s' % argtext,
            'local source = %s:%s(url)' % (target, method),
            'local chunk = %s(source)' % callee,
            'chunk()',
            'return',
        ]

    def run(self, proto):
        self.tops = []
        self.captured = None
        self.forwarded = None
        self.lastcallm = None
        self.upcoming = None
        self.body(proto)
        return self.lines, self.notes

def effect(ins):
    op = ins['op']
    a = ins['a']
    if op in (oploadk, oploadg, opnewtab):
        return set(), {a}
    if op == opgettab:
        return {ins['b']}, {a, a + 1}
    if op == opcallm:
        last = ins['b'] if isinstance(ins['b'], int) else a + 1
        return set(range(a, last + 1)), set(range(a, last + 2))
    if op == opcall:
        return {a}, {a}
    if op == opcall0:
        return {a}, {a}
    return set(), set()

def inlineonce(lines):
    out = list(lines)
    i = 0
    while i < len(out) - 1:
        m = re.match(r'^(\s*)local (r\d+|raw\d+) = (.+)$', out[i])
        if not m:
            i += 1
            continue
        indent, name, value = m.group(1), m.group(2), m.group(3)
        if re.search(r'\b' + name + r'\b', value):
            i += 1
            continue
        nxt = out[i + 1]
        hits = re.findall(r'\b' + name + r'\b(?!\s*=[^=])', nxt)
        total = sum(len(re.findall(r'\b' + name + r'\b', line))
                    for k, line in enumerate(out) if k != i)
        if len(hits) != 1 or total != 1:
            i += 1
            continue
        folded = re.sub(r'\b' + name + r'\b', value, nxt)
        out[i:i + 2] = [folded]
    return out

def prefix(text):
    if ident(text) or text.startswith('(') or text.endswith(')'):
        return text
    if text.startswith('{'):
        return '(' + text + ')'
    if text.startswith('"') or text.startswith("'"):
        return '(' + text + ')'
    try:
        float(text)
    except ValueError:
        return text
    return '(' + text + ')'

def ident(text):
    return bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', text))

def stringlit(value):
    out = ['"']
    for ch in value:
        code = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ch == '\n':
            out.append('\\n')
        elif 32 <= code < 127:
            out.append(ch)
        else:
            out.append('\\%d' % code)
    out.append('"')
    return ''.join(out)

def numlit(value):
    if isinstance(value, float) and value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return repr(value)

def deobfuscate(code):
    tree = parse(code)
    if tree is None:
        return None, ['alpha: payload not readable']
    if tree['kids']:
        return None, ['alpha: nested protos not handled']
    lines, notes = lifter2().run(tree)
    return '\n'.join(inlineonce(lines)) + '\n', notes
