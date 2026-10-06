import pathlib
import sys

# Os scripts importam uns aos outros como módulos soltos (ex.: `from ciclo import ...`)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'scripts'))
