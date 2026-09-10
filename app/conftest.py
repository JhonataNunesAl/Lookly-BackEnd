import os
import sys

# Os módulos do app (model, service, schemas, core...) são importados como
# pacotes de topo (`from model.look import Look`), assumindo que `app/` está
# no sys.path — é assim que `main.py`/uvicorn já rodam (cwd = app/). Isso
# garante o mesmo funcionando com pytest, não importa de onde for chamado.
sys.path.insert(0, os.path.dirname(__file__))
