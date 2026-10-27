import re

def stripheader(code):
    code = code.lstrip()
    if not code:
        return code
    m = re.match(r'--\[(=*)\[', code)
    if m:
        closer = ']' + m.group(1) + ']'
        end = code.find(closer, len(m.group(0)))
        if end >= 0:
            return code[end + len(closer):].lstrip()
        return ''
    if code.startswith('--'):
        end = code.find('\n')
        return code[end:].lstrip() if end >= 0 else ''
    return code

def stripcomments(code):
    out = []
    i = 0
    n = len(code)
    while i < n:
        ch = code[i]
        if ch in '"\'':
            quote = ch
            start = i
            i += 1
            while i < n:
                if code[i] == '\\':
                    i += 2
                    continue
                if code[i] == quote:
                    i += 1
                    break
                i += 1
            out.append(code[start:i])
            continue
        if ch == '-' and code.startswith('--', i):
            m = re.match(r'\[(=*)\[', code[i + 2:])
            if m:
                closer = ']' + m.group(1) + ']'
                end = code.find(closer, i + 2 + len(m.group(0)))
                i = n if end < 0 else end + len(closer)
                continue
            end = code.find('\n', i)
            i = n if end < 0 else end
            continue
        out.append(ch)
        i += 1
    text = ''.join(out)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def tidy(code):
    code = stripheader(code)
    code = stripcomments(code)
    lines = [line.rstrip() for line in code.split('\n')]
    return '\n'.join(lines).strip() + '\n'
