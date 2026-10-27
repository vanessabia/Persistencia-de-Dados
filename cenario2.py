#!/usr/bin/env python3
"""CENÁRIO 2 — insere no MongoDB OK; o PostgreSQL falha; rollback no MongoDB.

Como a falha do PostgreSQL é produzida de verdade: a constraint UNIQUE de
`pessoas.email` ja contém o e-mail que a transação tenta inserir, então o
Postgres rejeita a escrita (IntegrityError) durante a fase de prepare.

Execução: python cenario2.py
"""

from twopc.config import MONGO_DB
from twopc.coordenador import Coordenador2PC
from twopc.mongo_participante import ParticipanteMongo
from twopc.postgres_participante import ParticipantePostgres
from twopc.setup_databases import conectar_mongo, conectar_postgres, recriar_esquemas

EMAIL_DUPLICADO = "dup@dac.br"
PESSOA = {"tipo": "inserir_pessoa", "nome": "João Pereira", "email": EMAIL_DUPLICADO}


def main() -> None:
    print("=" * 72)
    print("CENÁRIO 2 — falha no PostgreSQL -> rollback no MongoDB")
    print("=" * 72)

    pg = conectar_postgres()
    client = conectar_mongo()
    recriar_esquemas(pg, client)
    db = client[MONGO_DB]

    # Pré-condição (fora do 2PC): o e-mail ja existe no PostgreSQL.
    with pg.cursor() as cur:
        cur.execute(
            "INSERT INTO pessoas (nome, email) VALUES (%s, %s)",
            ("Registro Original", EMAIL_DUPLICADO),
        )
    pg.commit()
    print(f"\nPré-condição: PostgreSQL ja possui a linha com email '{EMAIL_DUPLICADO}'.")
    print("Ordem dos participantes: MongoDB -> PostgreSQL\n")

    resultado = Coordenador2PC(verbose=True).executar(
        [ParticipanteMongo(client, MONGO_DB), ParticipantePostgres(pg)], PESSOA
    )

    print(f"\nResultado do 2PC: confirmado={resultado.confirmado}")
    print(f"Erro registrado:  {resultado.erro}")

    # Verificação independente, com novas conexões de leitura.
    verif_pg = conectar_postgres(autocommit=True)
    with verif_pg.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM pessoas WHERE email = %s", (EMAIL_DUPLICADO,))
        total_pg = cur.fetchone()[0]
    total_mongo = db.pessoas.count_documents({"email": EMAIL_DUPLICADO})

    print("\n--- Verificação pós-execução ---")
    print(f"Linhas no PostgreSQL com esse email: {total_pg}   (esperado: 1 = apenas o pré-existente)")
    print(f"Documentos no MongoDB com esse email: {total_mongo}  (esperado: 0)")

    ok = (not resultado.confirmado) and total_pg == 1 and total_mongo == 0
    print(f"\nVEREDITO: {'CENÁRIO CONFIRMADO [OK]' if ok else 'DEMONSTRAÇÃO FALHOU [ERRO]'}")

    for conn in (pg, verif_pg):
        conn.close()
    client.close()


if __name__ == "__main__":
    main()
