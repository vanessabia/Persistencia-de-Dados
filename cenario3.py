#!/usr/bin/env python3
"""CENÁRIO 3 — atualizações concorrentes nos dois bancos com leitor a cada 10 ms.

- N contas são semeadas em AMBOS os bancos (estado inicial idêntico).
- Vários trabalhadores executam transações 2PC de atualização de saldo
  (cada trabalhador opera contas disjuntas, para isolar a concorrência).
- Um leitor consulta os DOIS bancos a cada 10 ms e compara os conjuntos de
  dados, contando quantas leituras observaram os bancos divergentes.

Execução: python cenario3.py
"""

import threading
import time

from twopc.config import MONGO_DB
from twopc.coordenador import Coordenador2PC
from twopc.mongo_participante import ParticipanteMongo
from twopc.postgres_participante import ParticipantePostgres
from twopc.setup_databases import conectar_mongo, conectar_postgres, recriar_esquemas

N_CONTAS = 8
TRABALHADORES = 4
ATUALIZACOES_POR_TRABALHADOR = 100
INCREMENTO = 10.0
INTERVALO_LEITURA_S = 0.01
SALDO_INICIAL = 1000.0


def main() -> None:
    print("=" * 72)
    print("CENÁRIO 3 — atualizações concorrentes + leitor consistente (10 ms)")
    print("=" * 72)

    pg = conectar_postgres()
    client = conectar_mongo()
    recriar_esquemas(pg, client)
    db = client[MONGO_DB]

    # Estado inicial idêntico nos dois bancos (fora do 2PC: e o ponto de partida).
    with pg.cursor() as cur:
        for conta_id in range(1, N_CONTAS + 1):
            cur.execute(
                "INSERT INTO contas (id, nome, saldo) VALUES (%s, %s, %s)",
                (conta_id, f"Conta {conta_id}", SALDO_INICIAL),
            )
    pg.commit()
    db.contas.insert_many(
        [
            {"_id": conta_id, "nome": f"Conta {conta_id}", "saldo": SALDO_INICIAL}
            for conta_id in range(1, N_CONTAS + 1)
        ]
    )
    print(f"\nSemeadas {N_CONTAS} contas com saldo {SALDO_INICIAL:.2f} nos DOIS bancos.")
    print(
        f"{TRABALHADORES} trabalhadores x {ATUALIZACOES_POR_TRABALHADOR} atualizacoes "
        f"2PC de +{INCREMENTO:.2f}; leitor compara os bancos a cada {int(INTERVALO_LEITURA_S * 1000)} ms.\n"
    )

    parar = threading.Event()
    imprimir = threading.Lock()
    erros: list[str] = []

    def trabalhador(id_trabalhador: int) -> None:
        # Partição disjunta de contas: cada conta tem um único escritor.
        contas = [
            c for c in range(1, N_CONTAS + 1)
            if (c - 1) % TRABALHADORES == id_trabalhador
        ]
        saldos = {c: SALDO_INICIAL for c in contas}
        conn = conectar_postgres()
        part_pg = ParticipantePostgres(conn)
        part_mongo = ParticipanteMongo(client, MONGO_DB)
        coord = Coordenador2PC(verbose=False)
        try:
            for n in range(ATUALIZACOES_POR_TRABALHADOR):
                conta = contas[n % len(contas)]
                saldos[conta] += INCREMENTO
                operacao = {
                    "tipo": "atualizar_saldo",
                    "conta_id": conta,
                    "saldo": saldos[conta],
                }
                resultado = coord.executar([part_pg, part_mongo], operacao)
                if not resultado.confirmado:
                    with imprimir:
                        erros.append(f"T{id_trabalhador} upd {n}: {resultado.erro}")
                elif (n + 1) % 25 == 0:
                    with imprimir:
                        print(f"  [T{id_trabalhador}] {n + 1}/{ATUALIZACOES_POR_TRABALHADOR} atualizacoes 2PC ok")
        except Exception as exc:
            with imprimir:
                erros.append(f"T{id_trabalhador}: {type(exc).__name__}: {exc}")
        finally:
            part_pg.fechar()

    def leitor() -> dict:
        verif_pg = conectar_postgres(autocommit=True)
        polls = 0
        divergencias = 0
        exemplos: list[tuple[dict, dict]] = []
        while not parar.is_set():
            with verif_pg.cursor() as cur:
                cur.execute("SELECT id, saldo FROM contas ORDER BY id")
                mapa_pg = {int(i): float(s) for i, s in cur.fetchall()}
            mapa_mongo = {
                int(d["_id"]): float(d["saldo"]) for d in db.contas.find({}, {"saldo": 1})
            }
            polls += 1
            if mapa_pg != mapa_mongo:
                divergencias += 1
                if len(exemplos) < 3:
                    exemplos.append((mapa_pg, mapa_mongo))
            time.sleep(INTERVALO_LEITURA_S)
        verif_pg.close()
        return {"polls": polls, "divergencias": divergencias, "exemplos": exemplos}

    inicio = time.perf_counter()
    resultado_leitor: dict = {}
    thread_leitor = threading.Thread(target=lambda: resultado_leitor.update(leitor()), daemon=True)
    thread_leitor.start()

    threads = [
        threading.Thread(target=trabalhador, args=(i,)) for i in range(TRABALHADORES)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    duracao = time.perf_counter() - inicio

    parar.set()
    thread_leitor.join()

    print(f"\nAtualizacoes 2PC concluidas em {duracao:.2f}s.")
    if erros:
        print(f"Erros nos trabalhadores ({len(erros)}):")
        for e in erros[:10]:
            print(f"  - {e}")

    polls = resultado_leitor.get("polls", 0)
    divergencias = resultado_leitor.get("divergencias", 0)
    print("\n--- Resultado do leitor de consistencia ---")
    print(f"Leituras aos dois bancos:        {polls}")
    print(f"Leituras com bancos divergentes: {divergencias}"
          f" ({100 * divergencias / max(polls, 1):.2f}%)")
    for mapa_pg, mapa_mongo in resultado_leitor.get("exemplos", []):
        diferencas = {
            c: (mapa_pg.get(c), mapa_mongo.get(c))
            for c in set(mapa_pg) | set(mapa_mongo)
            if mapa_pg.get(c) != mapa_mongo.get(c)
        }
        print(f"  exemplo: contas divergentes (postgres, mongo) = {diferencas}")

    # Verificação final: os dois bancos tem que terminar idênticos.
    verif_pg = conectar_postgres(autocommit=True)
    with verif_pg.cursor() as cur:
        cur.execute("SELECT id, saldo FROM contas ORDER BY id")
        final_pg = {int(i): float(s) for i, s in cur.fetchall()}
    final_mongo = {
        int(d["_id"]): float(d["saldo"]) for d in db.contas.find({}, {"saldo": 1})
    }
    soma_esperada = N_CONTAS * SALDO_INICIAL + (
        TRABALHADORES * ATUALIZACOES_POR_TRABALHADOR * INCREMENTO
    )

    print("\n--- Verificacao final ---")
    print(f"Soma dos saldos PostgreSQL: {sum(final_pg.values()):.2f}")
    print(f"Soma dos saldos MongoDB:    {sum(final_mongo.values()):.2f}  (esperado: {soma_esperada:.2f})")
    print(f"Bancos identicos ao final:  {final_pg == final_mongo}")

    ok = not erros and final_pg == final_mongo and abs(sum(final_pg.values()) - soma_esperada) < 1e-6
    print(f"\nVEREDITO: {'CENARIO CONFIRMADO [OK]' if ok else 'DEMONSTRACAO FALHOU [ERRO]'}")

    verif_pg.close()
    pg.close()
    client.close()


if __name__ == "__main__":
    main()