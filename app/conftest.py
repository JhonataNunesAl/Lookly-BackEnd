import os
import sys

# Os módulos do app (model, service, schemas, core...) são importados como
# pacotes de topo (`from model.look import Look`), assumindo que `app/` está
# no sys.path — é assim que `main.py`/uvicorn já rodam (cwd = app/). Isso
# garante o mesmo funcionando com pytest, não importa de onde for chamado.
sys.path.insert(0, os.path.dirname(__file__))

# Os testes não tocam em banco nem em rede, mas `core.config` exige estas variáveis
# já no import. Valores de exemplo bastam num checkout limpo (CI, outra máquina) e, de
# quebra, garantem que o teste nunca fale com o banco real mesmo que exista um `.env`:
# `setdefault` roda antes de o `.env` ser lido, e o `.env` não sobrescreve o que já está definido.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://teste:teste@localhost:5432/teste")
os.environ.setdefault("SUPABASE_URL", "https://exemplo.supabase.co")
