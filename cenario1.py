#!/usr/bin/env python3
"""CENARIO 1 — insere no PostgreSQL OK; o MongoDB falha; rollback no PostgreSQL.

Como a falha do MongoDB é produzida de verdade: o índice ÚNICO de `email` da
coleçâo `pessoas` ja contém o e-mail que a transação tenta inserir, então o
MongoDB rejeita a escrita (DuplicateKeyError) durante a fase de prepare.

Execução: python cenario1.py
"""

from twopc.config import MONGO_DB
from twopc.coordenador import Coordenador2PC
from twopc.mongo_participante import ParticipanteMongo
from twopc.postgres_participante import ParticipantePostgres
from twopc.setup_databases import conectar_mongo, conectar_postgres, recriar_esquemas

EMAIL_DUPLICADO = "dup@dac.br"
PESSOA = {"tipo": "inserir_pessoa", "nome": "Maria Souza", "email": EMAIL_DUPLICADO}


def main() -> None:
    print("=" * 72)
    print("CENÁRIO 1 — falha no MongoDB -> rollback no PostgreSQL")
    print("=" * 72)

    pg = conectar_postgres()
    client = conectar_mongo()
    recriar_esquemas(pg, client)
    db = client[MONGO_DB]

    # Pré-condição (fora do 2PC): o e-mail ja existe no MongoDB.
    db.pessoas.insert_one({"nome": "Registro Original", "email": EMAIL_DUPLICADO})
    print(f"\nPré-condição: MongoDB ja possui o documento com email '{EMAIL_DUPLICADO}'.")
    print("Ordem dos participantes: PostgreSQL -> MongoDB\n")

    resultado = Coordenador2PC(verbose=True).executar(
        [ParticipantePostgres(pg), ParticipanteMongo(client, MONGO_DB)], PESSOA
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
    print(f"Linhas no PostgreSQL com esse email: {total_pg}   (esperado: 0)")
    print(f"Documentos no MongoDB com esse email: {total_mongo}  (esperado: 1 = apenas o pré-existente)")

    ok = (not resultado.confirmado) and total_pg == 0 and total_mongo == 1
    print(f"\nVEREDITO: {'CENÁRIO CONFIRMADO [OK]' if ok else 'DEMONSTRAÇÃO FALHOU [ERRO]'}")

    for conn in (pg, verif_pg):
        conn.close()
    client.close()


if __name__ == "__main__":
    main()
