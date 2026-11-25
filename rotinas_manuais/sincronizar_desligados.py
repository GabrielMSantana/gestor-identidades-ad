import _base  # noqa: F401

from src.application.use_cases.sincronizar_desligados.sincronizar_desligados import (
    SincronizarDesligadosUseCase,
)
from src.bootstrap import conexoes_producao
from src.infrastructure.logger.logger_config import setup_logger


def main():
    logger = setup_logger()
    logger.warning("==== ROTINA MANUAL: sincronizar usuarios desligados no AD ====")
    logger.warning("Objetivo: auditar TP_STATUS=2 e garantir que o usuario esteja na OU de Desligados, atualizando o banco quando necessario.")

    try:
        with conexoes_producao(logger, usar_api=True) as (repo, ad, modo):
            if modo.dry_run:
                logger.warning("DRY_RUN ativo: nenhuma alteracao sera feita no AD ou no banco.")
            else:
                logger.warning("DRY_RUN inativo: a rotina pode mover usuarios para Desligados e atualizar USER_DN/TP_STATUS no banco.")

            SincronizarDesligadosUseCase(repo, ad, logger, modo, ad.config.pasta_desligados).executar()

    except Exception as e:
        logger.error(f"Erro fatal na rotina manual de sincronizacao de desligados: {e}", exc_info=True)

    finally:
        logger.warning("==== FIM ROTINA MANUAL: sincronizar usuarios desligados no AD ====")


if __name__ == "__main__":
    main()
