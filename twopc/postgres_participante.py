"""Participante PostgreSQL do protocolo 2PC.

A transação fica ABERTA entre preparar() e confirmar()/abortar().
"""

import psycopg

class ParticipantePostgres:
    nome = "PostgreSQL"

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def preparar(self, operacao: dict) -> None:
        with self._conn.cursor() as cur:
            if operacao["tipo"] == "inserir_pessoa":
                cur.execute(
                    "INSERT INTO pessoas (nome, email) VALUES (%s, %s)",
                    (operacao["nome"], operacao["email"]),
                )
            elif operacao["tipo"] == "atualizar_saldo":
                cur.execute(
                    "UPDATE contas SET saldo = %s WHERE id = %s",
                    (operacao["saldo"], operacao["conta_id"]),
                )
                if cur.rowcount == 0:
                    raise LookupError(
                        f"conta {operacao['conta_id']} inexistente no PostgreSQL"
                    )
            else:
                raise ValueError(f"operação desconhecida: {operacao['tipo']}")

    def confirmar(self) -> None:
        self._conn.commit()

    def abortar(self) -> None:
        self._conn.rollback()

    def fechar(self) -> None:
        self._conn.close()
