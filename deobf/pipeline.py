import re
from deobf.lua import luaparse
from deobf.lua import fold
from deobf.vm import dispatch
from deobf.vm import payload
from deobf.vm import recover
from deobf.vm import vmisa
from deobf.alpha import lift as alphalift
from deobf.vm import lift
from deobf import clean
from deobf.lua import emit
from deobf.lua.luaparse import node2
from deobf.lua.luaast import stmtstr

def unescape(text):
    return payload.unescape(text)

def xorbytes(data, key):
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data, 1))

def decodepairs(code):
    pattern = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*"((?:\\.|[^"\\])*)"\s*,\s*"((?:\\.|[^"\\])*)"\s*\)')
    out = code
    for m in pattern.finditer(code):
        data = unescape(m.group(2))
        key = unescape(m.group(3))
        if not data or not key:
            continue
        try:
            plain = xorbytes(data, key).decode('latin-1')
        except Exception:
            continue
        if not all(32 <= ord(ch) < 127 or ch in '\n\t' for ch in plain):
            continue
        out = out.replace(m.group(0), lift.strlit(plain))
    return out

strpart = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

def badname(name):
    return bool(re.search(r'[A-Z]', name)) or '_' in name

declattr = {'local': 'names', 'localfunc': 'name', 'function': 'params',
            'fornum': 'var', 'forin': 'names'}

def walk(node, fn):
    if isinstance(node, (list, tuple)):
        for item in node:
            walk(item, fn)
        return
    if not isinstance(node, luaparse.node2):
        return
    fn(node)
    for key, value in vars(node).items():
        if key == 'kind':
            continue
        if isinstance(value, (luaparse.node2, list, tuple)):
            walk(value, fn)

def declnames(node):
    attr = declattr.get(node.kind)
    if attr is None:
        return []
    value = getattr(node, attr, None)
    return value if isinstance(value, list) else [value]

def declared(code):
    try:
        body = luaparse.parse(code)
    except Exception:
        return set()
    names = set()
    walk(body, lambda node: names.update(n for n in declnames(node) if n))
    return names

def flatloc(code):
    try:
        body = luaparse.parse(code)
    except Exception:
        return flatnames(code)
    names = set()
    walk(body, lambda node: names.update(n for n in declnames(node) if n))
    mapping = {}
    for name in sorted(names):
        if badname(name):
            mapping[name] = 't%d' % (len(mapping) + 1)
    if not mapping:
        return code

    def apply(node):
        attr = declattr.get(node.kind)
        if attr is not None:
            value = getattr(node, attr, None)
            if isinstance(value, list):
                setattr(node, attr, [mapping.get(v, v) for v in value])
            elif isinstance(value, str):
                setattr(node, attr, mapping.get(value, value))
        elif node.kind == 'name':
            node.name = mapping.get(node.name, node.name)

    walk(body, apply)
    try:
        return emit.render(body)
    except Exception:
        return code

def flatnames(code):
    parts = strpart.split(code)
    lits = strpart.findall(code)
    seen = {}
    for i, part in enumerate(parts):
        for m in re.finditer(r'\blocal\s+([A-Za-z_][A-Za-z0-9_]*)', part):
            nm = m.group(1)
            if badname(nm) and nm not in seen:
                seen[nm] = 't%d' % (len(seen) + 1)
        for m in re.finditer(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=', part, re.M):
            nm = m.group(1)
            if badname(nm) and nm not in seen:
                seen[nm] = 't%d' % (len(seen) + 1)
    if not seen:
        return code
    for i, part in enumerate(parts):
        for nm, new in seen.items():
            part = re.sub(r'(?<![.:\w])' + re.escape(nm) + r'\b', new, part)
        parts[i] = part
    out = []
    for i, part in enumerate(parts):
        out.append(part)
        if i < len(lits):
            out.append(lits[i])
    return ''.join(out)

def references(stmts):
    names = set()
    for s in stmts:
        for n in dispatch.walkall(s, []):
            if n.kind == 'name':
                names.add(n.name)
    return names

def prune(stmts):
    stmts = list(stmts)
    changed = True
    while changed:
        changed = False
        for i, s in enumerate(stmts):
            if s.kind not in ('local', 'localfunc'):
                continue
            defined = s.names if s.kind == 'local' else [s.name]
            rest = stmts[:i] + stmts[i + 1:]
            used = references(rest)
            if all(name not in used for name in defined):
                stmts = rest
                changed = True
                break
    return stmts

def fromxor(code, notes=None):
    decoded = decodepairs(code)
    if decoded == code:
        if notes is not None and re.search(r'bxor|bit32|string\.char', code):
            notes.append('xor decoder found but no string literal could be decoded')
        return None
    body = luaparse.parse(decoded)
    body = prune(body)
    return emit.render(body)

def buildisa(info, notes=None):
    core = info['core']
    keep = set(v for v in core.values() if v)
    isa = {}
    magic = None
    for op, sts in info['leaves'].items():
        kind = vmisa.classify(recover.canon(sts, info['roles'], keep))
        isa[op] = kind
        if kind[0] == 'UNKNOWN' and notes is not None:
            notes.append('opcode %s not recognised' % op)
        if kind[0] == 'CLOSURE' and kind[1] is not None:
            magic = kind[1]
    return isa, magic

def fromvm(code, notes=None):
    blob = payload.findblob(code)
    if not blob:
        return None
    info = recover.analyze(code)
    if not info or not info['leaves']:
        return None
    isa, magic = buildisa(info, notes)
    proto, used = payload.parseblob(blob)
    if notes is not None and used != len(blob):
        notes.append('payload has %d unread bytes' % (len(blob) - used))
    lifter = lift.lifter2(isa, magic)
    lines = lifter.body(proto, [], None)
    lines = lift.unshackle(lift.reindent(lines))
    for unused in range(3):
        lines = lift.droppure(lift.inlinevals(lift.addlocals(lift.polish(lines))))
    return '\n'.join(lines)

def passthrough(code):
    try:
        body = luaparse.parse(code)
    except Exception:
        return None
    try:
        return emit.render(body)
    except Exception:
        return None

names2 = ('descriptive', 'flat')

def describenames(code):
    try:
        from deobf.vendor import luaurenamer
        out = luaurenamer.renamecode(code)
    except Exception:
        return None
    return out if isinstance(out, str) and out.strip() else None

def withreport(code, names='descriptive'):
    notes = []
    code = clean.stripcomments(clean.stripheader(code))
    out = None
    if 'LOL!' in code:
        trial = []
        try:
            out = fromvm(code, trial)
        except Exception:
            out = None
        if out is not None:
            notes.extend(trial)
        elif alphalift.looks(code):
            out, anotes = alphalift.deobfuscate(code)
            notes.extend(anotes)
    if out is None:
        out = fromxor(code, notes)
    if out is None:
        out = passthrough(code)
        if out is not None:
            notes.append('no obfuscation recovered, script passed through')
    if out is not None:
        out = flatloc(out)
    if out is not None and names == 'descriptive':
        renamed = describenames(out)
        if renamed:
            out = renamed
        else:
            notes.append('identifier inference skipped')
    if out is not None:
        try:
            luaparse.parse(out)
        except Exception as err:
            notes.append('output does not parse: %s' % err)
    return out, notes

def deobfuscate(code, names='descriptive'):
    out, unused = withreport(code, names=names)
    return out
