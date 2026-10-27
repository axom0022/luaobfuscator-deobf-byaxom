import sys
from deobf import pipeline as deobfuscate
from deobf import clean

usage = """usage: python3 cli.py [--names descriptive|flat] <input> [output]

  --names descriptive   infer readable names from usage (default)
  --names flat          keep the lifter's flat names (a0, b3, c1)
"""

def main(argv):
    names = 'descriptive'
    if '--names' in argv:
        i = argv.index('--names')
        try:
            names = argv[i + 1]
        except IndexError:
            print(usage, file=sys.stderr)
            return 1
        if names not in ('descriptive', 'flat'):
            print(usage, file=sys.stderr)
            return 1
        argv = argv[:i] + argv[i + 2:]
    if not argv or argv[0] in ('-h', '--help'):
        print(usage, file=sys.stderr if argv else sys.stdout)
        return 1 if argv else 0
    src = argv[0]
    code = open(src, encoding='utf-8', errors='replace').read()
    out, notes = deobfuscate.withreport(code, names=names)
    if not out:
        print('unsupported input', file=sys.stderr)
        for note in notes:
            print('warning: %s' % note, file=sys.stderr)
        return 2
    text = clean.tidy(out)
    if len(argv) > 1:
        open(argv[1], 'w', encoding='utf-8').write(text)
        print('written %s' % argv[1])
    else:
        sys.stdout.write(text)
    for note in notes:
        print('warning: %s' % note, file=sys.stderr)
    return 3 if notes else 0

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
