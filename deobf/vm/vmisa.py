import re

def classify(txt):
    if not txt:
        return ('EMPTY',)
    t = txt
    if t == 'return':
        return ('RET0',)
    if re.fullmatch(r'X=X ;; R\[X\]\(R\[\(X\+1\)\]\)( ;; break)?', t):
        return ('CALL1V',)
    if re.fullmatch(r'local X=X ;; R\[X\]\(R\[\(\(X\+1\)\+0\)\]\)( ;; break)?', t):
        return ('CALL1V',)
    if re.fullmatch(r'local X=X ;; R\[X\]\(R\[\(X\+1\)\]\)( ;; break)?', t):
        return ('CALL1V',)
    if re.fullmatch(r'local [A-Za-z_][A-Za-z0-9_]*=R\[X\] ;; if \(not [A-Za-z_][A-Za-z0-9_]*\) then pc=\(pc\+1\) else R\[X\]=[A-Za-z_][A-Za-z0-9_]*;pc=X end', t):
        return ('TESTORT',)

    if re.fullmatch(r'if \(R\[X\]<R\[X\]\) then pc=X else pc=\(pc\+1\) end', t):
        return ('NGTRR',)
    if re.fullmatch(r'R\[X\]\[X\]=X', t):
        return ('SETTABR',)
    if re.fullmatch(r'R\[X\]=\(R\[X\]-R\[X\]\)', t):
        return ('SUB',)
    if re.fullmatch(r'local G=X ;; local X=R\[G\] ;; for X=\(G\+1\),X do X=\(X\.\.R\[X\]\) end ;; R\[X\]=X', t):
        return ('CONCAT',)

    if t == 'pc=X':
        return ('JMP',)
    if re.fullmatch(r'local X=X ;; TOP=\(\(X\+X\)-1\) ;; for X=X,TOP do local X=X\[\(X-X\)\];R\[X\]=X end', t):
        return ('VARARGT',)
    if re.fullmatch(r'if R\[X\] then pc=\(pc\+1\) else pc=X end', t):
        return ('TEST',)
    if re.fullmatch(r'if \(not R\[X\]\) then pc=\(\(?pc\+1\)?\+?0?\)? else pc=X end', t):
        return ('TESTNOT',)
    if re.fullmatch(r'if \(\(not R\[X\]\)X\) then pc=\(pc\+1\) else pc=X end', t):
        return ('TESTNOT',)
    if re.fullmatch(r'if \(R\[X\]==X\) then pc=\(pc\+1\) else pc=X end', t):
        return ('EQ',)
    if re.fullmatch(r'return X\(R,X,TOP\)', t):
        return ('RETT',)
    if re.fullmatch(r'return X\(R,X,X\)', t):
        return ('RETN',)
    if re.fullmatch(r'return R\[X\]\(\)', t):
        return ('TAIL0',)
    if re.search(r'return R\[X\]\(X\(R,\(X\+1\),TOP\)\)', t):
        return ('TAILT',)
    if re.search(r'return R\[X\]\(X\(R,\(X\+1\),X\)\)', t):
        return ('TAILN',)
    if 'X=X({},{' in t:
        m = re.search(r'X\[1\]==(\d+)', t)
        return ('CLOSURE', int(m.group(1)) if m else None)
    if 'TOP=((' in t and 'for X=X,TOP do' in t:
        if re.search(r'\(X\(R,\(\(X\+1\)\+0\),TOP\)\)', t):
            return ('CALLMT',)
        if re.search(r'\(X\(R,\(X\+1\),TOP\)\)', t):
            return ('CALLMT',)
        if re.search(r'\(R\[X\]\(R\[\(X\+1\)\]\)\)', t):
            return ('CALLM1',)
        return ('CALLMN',)
    if re.search(r'R\[X\]=R\[X\]\(X\(R,\(\(X\+1\)\+0\),TOP\)\)', t):
        return ('CALLNT',)
    if re.search(r'R\[X\]=R\[X\]\(X\(R,\(X\+1\),TOP\)\)', t):
        return ('CALLNT',)
    if re.search(r'R\[X\]=R\[X\]\(X\(R,\(\(X\+1\)\+0\),X\)\)', t):
        return ('CALLNN',)
    if re.search(r'R\[X\]=R\[X\]\(X\(R,\(X\+1\),X\)\)', t):
        return ('CALLNN',)
    if re.search(r'R\[X\]=R\[X\]\(R\[\(X\+1\)\]\)', t):
        return ('CALLN1',)
    if re.search(r'R\[X\]\(X\(R,\(\(X\+1\)\+0\),TOP\)\)', t):
        return ('CALLVT',)
    if re.search(r'R\[X\]\(X\(R,\(X\+1\),TOP\)\)', t):
        return ('CALLVT',)
    if re.search(r'R\[X\]\(X\(R,\(\(X\+1\)\+0\),X\)\)', t):
        return ('CALLVN',)
    if re.search(r'R\[X\]\(X\(R,\(X\+1\),X\)\)', t):
        return ('CALLVN',)
    if 'R[(X+3)]=' in t or 'R[((X+3)+0)]=' in t or 'R[((X+2)+1)]=' in t:
        if '(R[X]+X)' in t:
            return ('FORLOOP',)
        return ('FORPREP',)
    if re.fullmatch(r'for X=\(X\+1\),TOP do X\(X,R\[X\]\) end', t):
        return ('PUSHTOP',)
    if re.fullmatch(r'for X=\(X\+1\),X do X\(X,R\[X\]\) end', t):
        return ('PUSHRANGE',)
    if re.fullmatch(r'local X=X ;; local X=R\[X\] ;; for X=\(X\+1\),TOP do X\(X,R\[X\]\) end', t):
        return ('APPEND',)
    if re.fullmatch(r'local X=X ;; local X=R\[X\] ;; for X=\(X\+1\),X do X\(X,R\[X\]\) end', t):
        return ('APPEND',)
    if re.fullmatch(r'for X=X,X do R\[X\]=nil end', t):
        return ('FILLNIL',)
    if re.fullmatch(r'for X=\(X\+1\),X do R\[X\]=nil end', t):
        return ('FILLNIL',)
    if re.fullmatch(r'R\[X\]=\{X?.*\}', t):
        return ('NEWTAB',)
    if t == 'R[X]={}':
        return ('NEWTAB',)
    if re.fullmatch(r'R\[X\]=\(# R\[X\]\)', t):
        return ('LEN',)
    if re.fullmatch(r'R\[X\]=\(R\[X\]%R\[X\]\)', t):
        return ('MOD',)
    if re.fullmatch(r'R\[X\]=\(R\[X\]%X\)', t):
        return ('MODK',)
    if re.fullmatch(r'R\[X\]=\(R\[X\]\+X\)', t):
        return ('ADDK',)
    if re.fullmatch(r'R\[X\]=\(X\+R\[X\]\)', t):
        return ('ADDK',)
    if re.fullmatch(r'R\[X\]=R\[X\]\[X\]', t):
        return ('GETTAB',)
    if re.fullmatch(r'R\[X\]\[X\]=R\[X\]', t):
        return ('SETTAB',)
    if re.fullmatch(r'R\[X\]=G\[X\]', t):
        return ('LOADG',)
    if re.fullmatch(r'R\[X\]=R\[X\]', t):
        return ('MOVE',)
    if re.fullmatch(r'R\[X\]=X', t):
        return ('SETB',)

    if re.fullmatch(r'if \(R\[X\]<=X\) then pc=\(pc\+1\) else pc=X end', t):
        return ('LE',)
    if re.fullmatch(r'if \(R\[X\]<X\) then pc=\(pc\+1\) else pc=X end', t):
        return ('LT',)
    if re.fullmatch(r'if \(R\[X\]<R\[X\]\) then pc=\(pc\+1\) else pc=X end', t):
        return ('LTRR',)
    if re.fullmatch(r'if \(R\[X\]<=R\[X\]\) then pc=\(pc\+1\) else pc=X end', t):
        return ('LERR',)
    if re.fullmatch(r'if \(X<X\) then pc=X else pc=\(pc\+1\) end', t):
        return ('NLT',)
    if re.fullmatch(r'if \(X~=X\) then pc=\(pc\+1\) else pc=X end', t):
        return ('NE',)
    if re.fullmatch(r'local X=X ;; local [A-Za-z_][A-Za-z0-9_]*=R\[X\] ;; R\[\(X\+1\)\]=[A-Za-z_][A-Za-z0-9_]* ;; R\[X\]=[A-Za-z_][A-Za-z0-9_]*\[X\]', t):
        return ('SELF',)
    if re.fullmatch(r'local X=X ;; return R\[X\],R\[\(X\+1\)\]', t):
        return ('RET2',)
    if re.fullmatch(r'R\[X\]=\(X~=0\)( ;; pc=\(pc\+1\))?', t):
        return ('LOADBOOL',)
    if t == 'return R[X]':
        return ('RET1',)
    if re.fullmatch(r'R\[X\]\[R\[X\]\]=R\[X\]', t):
        return ('SETTAB',)
    if re.fullmatch(r'R\[X\]=R\[X\]\[R\[X\]\]', t):
        return ('GETTAB',)
    if re.fullmatch(r'local X=X ;; R\[X\]=R\[X\]\(\)', t):
        return ('CALL00',)
    if re.fullmatch(r'G\[X\]=R\[X\]', t):
        return ('SETG',)
    if re.fullmatch(r'R\[X\]=X\(G\[X\],nil,G\)', t):
        return ('CLOSURE', None)
    if re.fullmatch(r'local X=X ;; local X=\(X\+2\) ;; local X=\{X\} ;; for X=1,X do R\[\(X\+X\)\]=X\[X\] end ;; local [A-Za-z_][A-Za-z0-9_]*=X\[1\] ;; if [A-Za-z_][A-Za-z0-9_]* then [A-Za-z_][A-Za-z0-9_]*\[X\]=[A-Za-z_][A-Za-z0-9_]*;pc=X else pc=\(pc\+1\) end', t):
        return ('TFORSTEP',)
    if re.fullmatch(r'local X=X ;; local X=R\[X\] ;; for X=\(X\+1\),X do X=\(X\.\.R\[X\]\) end ;; R\[X\]=X', t):
        return ('CONCAT',)
    if re.fullmatch(r'local X=X ;; for X=1,X do R\[X\]\[X\]=R\[\(X\+X\)\] end', t):
        return ('SETLIST',)
    if re.fullmatch(r'R\[X\]=\(R\[X\]-X\)', t):
        return ('SUBK',)
    if re.fullmatch(r'R\[X\]=\(R\[X\]\*X\)', t):
        return ('MULK',)
    if re.fullmatch(r'R\[X\]=\(R\[X\]\+R\[X\]\)', t):
        return ('ADD',)
    if re.fullmatch(r'local X=X ;; for X=X,X do X=\(X\+1\);R\[X\]=\{X\}\[X\] end', t):
        return ('CALLM1N',)
    if re.fullmatch(r'local X=X ;; return X\(R,X,\(X\+X\)\)', t):
        return ('RETN',)
    if re.fullmatch(r'local X=X ;; TOP=\(\(X\+X\)-1\) ;; for X=X,TOP do X=\(X\+1\);R\[X\]=X\(R\[X\]\(\)\)\[X\] end', t):
        return ('CALLM0',)
    if re.fullmatch(r'local X=X ;; TOP=\(\(X\+X\)-1\) ;; for X=X,TOP do X=\(X\+1\);R\[X\]=X\(R\[X\]\(R\[\(X\+1\)\]\)\)\[X\] end', t):
        return ('CALLM1',)
    if re.fullmatch(r'local X=X ;; TOP=\(\(X\+X\)-1\) ;; for X=X,TOP do X=\(X\+1\);R\[X\]=X\(R\[X\]\(X\(R,\(X\+1\),X\)\)\)\[X\] end', t):
        return ('CALLMT',)
    if re.fullmatch(r'for X=\(X\+1\),X do X\(X,R\[X\]\) end', t):
        return ('PUSHRANGE',)
    if re.fullmatch(r'local X=X ;; local X=R\[X\] ;; for X=\(X\+1\),TOP do X\(X,R\[X\]\) end', t):
        return ('APPEND',)
    if re.fullmatch(r'local X=X ;; local X=R\[X\] ;; for X=\(X\+1\),X do X\(X,R\[X\]\) end', t):
        return ('APPEND',)
    if re.fullmatch(r'local X=X ;; R\[X\]\[X\]\(\)', t):
        return ('CALL00',)
    return ('UNKNOWN', t)
