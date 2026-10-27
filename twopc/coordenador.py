"""Coordenador 2PC (Two Phase Commit).

Fase 1 (Prepare): cada participante executa a escrita dentro de uma transação
aberta e vota SIM (sucesso) ou NAO (excecao).
Fase 2 (Commit): se todos votaram SIM, confirma em todos. Se algum votou NAO,
aborta todos os participantes que ja tinham preparado (rollback).
"""

from __future__ import annotations

from dataclasses import dataclass, field


class Participante:
    """Interface de um participante da transacao distribuida."""

    nome: str

    def preparar(self, operacao: dict) -> None:
        """Executa a escrita dentro de uma transação ABERTA (não confirma ainda)."""

    def confirmar(self) -> None:
        """Confirma (commit) a transação preparada."""

    def abortar(self) -> None:
        """Desfaz (rollback) a transação preparada."""


@dataclass
class Resultado2PC:
    confirmado: bool
    participantes_preparados: list[str] = field(default_factory=list)
    erro: str | None = None


class Coordenador2PC:
    def __init__(self, verbose: bool = True) -> None:
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"  [2PC] {msg}")

    def executar(self, participantes: list[Participante], operacao: dict) -> Resultado2PC:
        preparados: list[Participante] = []
        try:
            # ---------------- Fase 1: Prepare ----------------
            for p in participantes:
                self._log(f"Fase 1 — preparando em '{p.nome}'...")
                p.preparar(operacao)
                preparados.append(p)
                self._log(f"'{p.nome}' votou SIM (transação preparada)")

            # ---------------- Fase 2: Commit ----------------
            for p in participantes:
                self._log(f"Fase 2 — confirmando (COMMIT) em '{p.nome}'...")
                p.confirmar()
            self._log("COMMIT global concluído com sucesso")
            return Resultado2PC(
                confirmado=True,
                participantes_preparados=[p.nome for p in participantes],
            )

        except Exception as exc:
            # ------------- Fase 2: Rollback -------------
            self._log(
                f"Fase 1 — '{participantes[len(preparados)].nome}' votou NAO "
                f"({type(exc).__name__}: {exc})"
            )
            self._log("Fase 2 — ROLLBACK de todos os participantes preparados:")
            for p in reversed(preparados):
                try:
                    p.abortar()
                    self._log(f"'{p.nome}' abortado com sucesso (rollback)")
                except Exception as rollback_exc:
                    self._log(f"ERRO ao abortar '{p.nome}': {rollback_exc}")
            return Resultado2PC(
                confirmado=False,
                participantes_preparados=[p.nome for p in preparados],
                erro=f"{type(exc).__name__}: {exc}",
            )
