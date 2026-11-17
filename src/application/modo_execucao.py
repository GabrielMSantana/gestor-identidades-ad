from dataclasses import dataclass


@dataclass(frozen=True)
class ModoExecucao:
    """Modo seguro operacional (permanente no projeto).

    dry_run=True: calcula e loga as ações, mas não altera AD, API nem banco
    pelos repositories.
    executar_procs: com dry_run=True, decide se as procedures que alimentam as
    filas continuam rodando (recomendado, para simular com candidatos reais).
    """
    dry_run: bool = False
    executar_procs: bool = True
