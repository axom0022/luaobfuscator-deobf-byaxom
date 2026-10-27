import struct
import re
from deobf.lua.luaast import unk

class reader2:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def u8(self):
        v = self.data[self.pos]
        self.pos += 1
        return v

    def u16(self):
        v = struct.unpack_from('<H', self.data, self.pos)[0]
        self.pos += 2
        return v

    def u32(self):
        v = struct.unpack_from('<I', self.data, self.pos)[0]
        self.pos += 4
        return v

    def f64(self):
        v = struct.unpack_from('<d', self.data, self.pos)[0]
        self.pos += 8
        return v

    def raw(self, n):
        v = self.data[self.pos:self.pos + n]
        self.pos += n
        return v

def bits(value, low, high):
    width = high - low + 1
    return (value >> (low - 1)) & ((1 << width) - 1)

def unescape(text):
    out = bytearray()
    i = 0
    table = {'a': 7, 'b': 8, 'f': 12, 'n': 10, 'r': 13, 't': 9, 'v': 11, '\\': 92, '"': 34, "'": 39, '\n': 10}
    while i < len(text):
        c = text[i]
        if c != '\\':
            out.append(ord(c) & 255)
            i += 1
            continue
        i += 1
        if i >= len(text):
            break
        c = text[i]
        if c.isdigit():
            digits = ''
            while i < len(text) and len(digits) < 3 and text[i].isdigit():
                digits += text[i]
                i += 1
            out.append(int(digits) % 256)
            continue
        if c == 'x':
            hx = text[i + 1:i + 3]
            if re.fullmatch(r'[0-9a-fA-F]{2}', hx or ''):
                out.append(int(hx, 16))
                i += 3
                continue
        out.append(table.get(c, ord(c)) & 255)
        i += 1
    return bytes(out)

def rrle(text):
    out = bytearray()
    hexd = '0123456789abcdefABCDEF'
    i = 0
    while i < len(text):
        if i + 3 < len(text) and text[i] in hexd and text[i + 1] == 'Q':
            out.extend(bytes([int(text[i + 2:i + 4], 16)]) * int(text[i], 16))
            i += 4
            continue
        if i + 1 < len(text) and text[i] in hexd and text[i + 1] in hexd:
            out.append(int(text[i:i + 2], 16))
            i += 2
            continue
        i += 1
    return bytes(out)

def findblob(src):
    idx = src.find('LOL!')
    if idx < 0:
        return None
    start = src.rfind('"', 0, idx)
    if start < 0:
        return None
    i = start + 1
    buf = []
    while i < len(src):
        c = src[i]
        if c == '\\':
            buf.append(src[i:i + 2])
            i += 2
            continue
        if c == '"':
            break
        buf.append(c)
        i += 1
    text = ''.join(buf)
    if not text.startswith('LOL!'):
        return None
    return rrle(unescape(text[4:]).decode('latin1'))

class proto2:
    def __init__(self):
        self.consts = []
        self.params = 0
        self.instrs = []
        self.kids = []

class ins2:
    def __init__(self, op, a, b, c, af, bf, cf):
        self.op = op
        self.a = a
        self.b = b
        self.c = c
        self.af = af
        self.bf = bf
        self.cf = cf

    def __repr__(self):
        return 'Ins(%d,%r,%r,%r)' % (self.op, self.a, self.b, self.c)

def readconst(rd):
    kind = rd.u8()
    if kind == 1:
        return rd.u8() != 0
    if kind == 2:
        return rd.f64()
    if kind == 3:
        n = rd.u32()
        return rd.raw(n).decode('latin-1')
    raise ValueError('bad const kind %d' % kind)

def readproto(rd):
    p = proto2()
    n = rd.u32()
    p.consts = [readconst(rd) for unused in range(n)]
    p.params = rd.u8()
    count = rd.u32()
    for unused in range(count):
        hdr = rd.u8()
        if bits(hdr, 1, 1) != 0:
            p.instrs.append(ins2(-1, 0, None, None, 0, 0, 0))
            continue
        variant = bits(hdr, 2, 3)
        flags = bits(hdr, 4, 6)
        op = rd.u16()
        a = rd.u16()
        b = None
        c = None
        if variant == 0:
            b = rd.u16()
            c = rd.u16()
        elif variant == 1:
            b = rd.u32()
        elif variant == 2:
            raw = rd.u32()
            low = raw - (1 << 16)
            high = raw - (1 << 31)
            if -64 <= low <= count + 64:
                b = low
            elif -64 <= high <= count + 64:
                b = high
            else:
                b = low
        elif variant == 3:
            b = rd.u32() - (1 << 16)
            c = rd.u16()
        af = bits(flags, 1, 1)
        bf = bits(flags, 2, 2)
        cf = bits(flags, 3, 3)
        if af:
            a = p.consts[a - 1]
        if bf:
            b = p.consts[b - 1]
        if cf:
            c = p.consts[c - 1]
        p.instrs.append(ins2(op, a, b, c, af, bf, cf))
    nkids = rd.u32()
    p.kids = [readproto(rd) for unused in range(nkids)]
    return p

def parseblob(data):
    rd = reader2(data)
    proto = readproto(rd)
    return proto, rd.pos
