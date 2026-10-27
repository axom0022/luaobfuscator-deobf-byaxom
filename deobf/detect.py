import re

def hastoken(code):
    return 'LOL!' in code

def hasxor(code):
    return bool(re.search(r'\\\d+', code)) and ('bxor' in code or 'bit32' in code or 'bit ' in code)

def detectpreset(code):
    if hastoken(code):
        return 'vm'
    if hasxor(code):
        return 'xor'
    return None
