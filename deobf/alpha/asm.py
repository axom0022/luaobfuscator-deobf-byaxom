import struct

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

def const(value):
    if isinstance(value, bool):
        return bytes([constbool, 1 if value else 0])
    if isinstance(value, float) or isinstance(value, int):
        raw = struct.pack('<d', float(value))
        return bytes([constnum]) + raw
    data = value.encode('latin-1')
    return bytes([conststr]) + struct.pack('<I', len(data)) + data

class asm:

    def __init__(self, params=0):
        self.params = params
        self.consts = []
        self.instrs = []
        self.nextreg = 0

    def reg(self):
        reg = self.nextreg
        self.nextreg += 1
        return reg

    def constref(self, value):
        self.consts.append(value)
        return len(self.consts)

    def emit(self, op, a=0, b=0, c=0, bconst=False, cconst=False):
        desc = (0x10 if bconst else 0) | (0x20 if cconst else 0)
        self.instrs.append((desc, op, a, b, c))

    def loadk(self, value, reg=None):
        reg = self.reg() if reg is None else reg
        self.emit(oploadk, a=reg, b=self.constref(value), bconst=True)
        return reg

    def loadg(self, name, reg=None):
        reg = self.reg() if reg is None else reg
        self.emit(oploadg, a=reg, b=self.constref(name), bconst=True)
        return reg

    def gettab(self, tablereg, key, reg=None):
        reg = self.reg() if reg is None else reg
        self.emit(opgettab, a=reg, b=tablereg, c=self.constref(key), cconst=True)
        return reg

    def callspread(self, fnreg, firstarg, lastarg):
        self.emit(opcallm, a=fnreg, b=lastarg)
        return fnreg

    def call(self, fnreg, lastarg):
        self.emit(opcall, a=fnreg, b=lastarg)
        return fnreg

    def call0(self, fnreg):
        self.emit(opcall0, a=fnreg)

    def ret(self):
        self.emit(opreturn)

    def blob(self, kids=()):
        out = bytearray()
        out += struct.pack('<I', len(self.consts))
        for value in self.consts:
            out += const(value)
        out += bytes([self.params])
        out += struct.pack('<I', len(self.instrs))
        for desc, op, a, b, c in self.instrs:
            out += bytes([desc])
            out += struct.pack('<HHHH', op, a, b, c)
        out += struct.pack('<I', len(kids))
        for kid in kids:
            out += kid
        return 'LOL!' + out.hex().upper()

def wrap(blob, preamble):
    return preamble + 'return v15("%s", v9(), ...);\n' % blob

def preambleof(path):
    text = open(path, encoding='utf-8', errors='replace').read()
    cut = text.rindex('return v15("LOL!')
    return text[:cut]
