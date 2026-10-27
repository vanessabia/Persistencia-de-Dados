"""Preparacao do ambiente: conexoes, replica set do MongoDB e schema dos dois bancos."""

import time

import psycopg
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from .config import MONGO_DB, MONGO_URI, PG_DSN


def conectar_postgres(autocommit: bool = False) -> psycopg.Connection:
    ultimo_erro: Exception | None = None
    for _ in range(30):
        try:
            return psycopg.connect(PG_DSN, autocommit=autocommit)
        except psycopg.OperationalError as exc:
            ultimo_erro = exc
            time.sleep(1)
    raise RuntimeError("PostgreSQL nao respondeu. Suba os bancos: docker compose up -d") from ultimo_erro


def configurar_replica_set(client: MongoClient) -> None:
    """O MongoDB exige replica set para transacoes; inicia um single-node se preciso."""
    try:
        client.admin.command("replSetGetStatus")
        return
    except PyMongoError:
        pass
    print("Inicializando replica set rs0 (obrigatorio p/ transacoes no MongoDB)...")
    client.admin.command(
        "replSetInitiate",
        {"_id": "rs0", "members": [{"_id": 0, "host": "localhost:27017"}]},
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            status = client.admin.command("replSetGetStatus")
            if status["members"][0].get("stateStr") == "PRIMARY":
                print("Replica set rs0 no estado PRIMARY.")
                return
        except PyMongoError:
            pass
        time.sleep(0.5)
    raise RuntimeError("Replica set rs0 nao ficou PRIMARY a tempo")


def conectar_mongo() -> MongoClient:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    ultimo_erro: Exception | None = None
    for _ in range(30):
        try:
            client.admin.command("ping")
            break
        except PyMongoError as exc:
            ultimo_erro = exc
            time.sleep(1)
    else:
        raise RuntimeError("MongoDB nao respondeu. Suba os bancos: docker compose up -d") from ultimo_erro
    configurar_replica_set(client)
    return client


def recriar_esquemas(pg_conn: psycopg.Connection, client: MongoClient) -> None:
    """Recria tabela/colecoes do zero (cada comeco de cenario parte de estado limpo)."""
    db = client[MONGO_DB]
    with pg_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS pessoas CASCADE")
        cur.execute("DROP TABLE IF EXISTS contas CASCADE")
        cur.execute(
            """
            CREATE TABLE pessoas (
                id    SERIAL PRIMARY KEY,
                nome  TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE contas (
                id    INT PRIMARY KEY,
                nome  TEXT NOT NULL,
                saldo DOUBLE PRECISION NOT NULL
            )
            """
        )
    pg_conn.commit()
    db.drop_collection("pessoas")
    db.drop_collection("contas")
    db.pessoas.create_index("email", unique=True)
    print("Esquemas recriados no PostgreSQL (tabelas pessoas/contas) e no MongoDB (colecoes pessoas/contas).")


def main() -> None:
    print("Aguardando PostgreSQL e MongoDB...")
    pg = conectar_postgres()
    client = conectar_mongo()
    recriar_esquemas(pg, client)
    pg.close()
    client.close()
    print("Ambiente pronto.")
