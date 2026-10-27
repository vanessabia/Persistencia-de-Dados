# 2PC — Persistência atômica em PostgreSQL e MongoDB

Aplicação que demonstra **Two Phase Commit (2PC)**: a mesma operação é persistida
atomicamente em dois bancos diferentes (PostgreSQL e MongoDB). Se qualquer banco
falhar na fase de preparação, **nenhum** dos dois efetiva a escrita.

Relatório com a análise de cada cenário: [`relatorio.md`](relatorio.md).

## Pré-requisitos

- **Docker Desktop** com a engine funcionando (no Windows, exige WSL2)
- **Python 3.10+**

### Instalando as dependências (Windows)

Com o **winget**, em um PowerShell:

```powershell
winget install Python.Python.3.14       # Python 3.14 (qualquer 3.10+ serve)
winget install Docker.DockerDesktop     # Docker Desktop
```

Após a instalação, **abra o Docker Desktop uma vez** e conclua o assistente
inicial (aceite os termos). Depois **verifique** que tudo está funcionando:

```powershell
python --version    # deve imprimir "Python 3.x.y" (não pode abrir a Microsoft Store)
docker info         # deve imprimir informações do engine (não pode dar erro de conexão)
```

### macOS / Linux

```bash
# macOS (Homebrew) | Linux (apt - ajuste conforme sua distro)
brew install --cask docker   |   sudo apt install docker.io docker-compose python3 python3-venv
```

Nos comandos abaixo, troque `python`/`.\.venv\Scripts\python.exe` por
`python3`/`.venv/bin/python` se necessário.

## Instalação

```powershell
# 1. Sobe os bancos (PostgreSQL 16 + MongoDB 7 em replica set)
docker compose up -d

# 2. Cria o ambiente virtual e instala as dependências
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. Prepara as tabelas/coleções e inicializa o replica set do MongoDB
.\.venv\Scripts\python.exe setup_bancos.py
```

> O MongoDB só permite transações multi-documento (necessárias para o 2PC) em
> **replica set** — o `setup_bancos.py` inicializa um `rs0` single-node
> automaticamente e o `docker-compose.yml` já sobe o `mongod` com `--replSet rs0`.

## Solução de problemas

**`docker compose up -d` falha com "error during connect" / "Docker Desktop
says WSL is too old or incomplete" (Windows):** a engine do Docker depende do
WSL2. Se o `wsl --update` travar (problema conhecido com a Store em algumas
máquinas), a rota que funciona:

```powershell
# PowerShell como Administrador:
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

Reinicie. Depois instale o WSL moderno pelo instalador MSI oficial (baixa
direto, sem Store): https://github.com/microsoft/WSL/releases → `wsl.*.x64.msi`.
Reinicie novamente se pedido, abra o Docker Desktop e teste `docker info`.

**Portas 5432 ou 27017 já ocupadas** (ex.: já tem um PostgreSQL/MongoDB local
instalado): edite `docker-compose.yml` e troque o lado esquerdo do mapeamento
(ex.: `"55432:5432"`) e ajuste `PG_DSN`/`MONGO_URI` em `twopc/config.py`
consecutivamente. Se não houver nada usando as portas, ignore.

**Erro ao conectar nos bancos logo após `docker compose up -d`:** aguarde o
status `healthy` (`docker compose ps`). O `setup_bancos.py` já espera os bancos
ficarem disponíveis por até 30 s.

## Execução

```powershell
.\.venv\Scripts\python.exe cenario1.py   # falha no MongoDB  → rollback no Postgres
.\.venv\Scripts\python.exe cenario2.py   # falha no Postgres → rollback no MongoDB
.\.venv\Scripts\python.exe cenario3.py   # atualizações concorrentes + leitor a cada 10 ms
```

Cada cenário recria o schema do zero e imprime um `VEREDITO: CENARIO CONFIRMADO [OK]`
ao final. Não é necessário rodar `setup_bancos.py` entre os cenários.

## Estrutura

```
docker-compose.yml        # PostgreSQL 16 + MongoDB 7 (replica set rs0)
setup_bancos.py           # cria schemas e inicializa o replica set
cenario1.py               # cenário 1: erro no Mongo  → rollback PG
cenario2.py               # cenário 2: erro no PG     → rollback Mongo
cenario3.py               # cenário 3: concorrência + leitor consistente (10 ms)
twopc/
  coordenador.py          # o coordenador do 2PC (fase 1: prepare, fase 2: commit/rollback)
  postgres_participante.py# participante PostgreSQL (transação fica aberta entre fases)
  mongo_participante.py   # participante MongoDB (sessão/transação aberta entre fases)
  setup_databases.py      # conexões, replica set, criação de schema
  config.py               # DSNs e nomes de banco
relatorio.md              # relatório da arquitetura e dos 3 cenários
```

## Como funciona (resumo)

1. **Fase 1 (Prepare):** o coordenador pede a cada participante que execute a
   escrita **dentro de uma transação aberta** (sem confirmar). Cada participante
   vota SIM (sucesso) ou NÃO (exceção — ex.: violação de constraint/índice único).
2. **Fase 2:** se todos votaram SIM → `COMMIT` nos dois bancos. Se algum votou
   NÃO → `ROLLBACK` em todos os que já tinham preparado.

Os erros dos cenários 1 e 2 são **reais** (índice único/constraint duplicado),
não simulações.
