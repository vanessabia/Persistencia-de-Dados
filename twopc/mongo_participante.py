"""Participante MongoDB do protocolo 2PC.

Usa transacao multi-documento do replica set: a sessao/transacao fica ABERTA
entre preparar() e confirmar()/abortar(), espelhando o participante PostgreSQL.
"""

from pymongo import MongoClient

from .config import MONGO_DB


class ParticipanteMongo:
    nome = "MongoDB"

    def __init__(self, client: MongoClient, db_name: str = MONGO_DB) -> None:
        self._client = client
        self._db = client[db_name]
        self._session = None

    def preparar(self, operacao: dict) -> None:
        self._session = self._client.start_session()
        self._session.start_transaction()
        try:
            if operacao["tipo"] == "inserir_pessoa":
                self._db.pessoas.insert_one(
                    {"nome": operacao["nome"], "email": operacao["email"]},
                    session=self._session,
                )
            elif operacao["tipo"] == "atualizar_saldo":
                resultado = self._db.contas.update_one(
                    {"_id": operacao["conta_id"]},
                    {"$set": {"saldo": operacao["saldo"]}},
                    session=self._session,
                )
                if resultado.matched_count == 0:
                    raise LookupError(
                        f"conta {operacao['conta_id']} inexistente no MongoDB"
                    )
            else:
                raise ValueError(f"operação desconhecida: {operacao['tipo']}")
        except Exception:
            self.abortar()
            raise

    def confirmar(self) -> None:
        try:
            self._session.commit_transaction()
        finally:
            self._session.end_session()
            self._session = None

    def abortar(self) -> None:
        if self._session is None:
            return
        try:
            self._session.abort_transaction()
        finally:
            self._session.end_session()
            self._session = None
