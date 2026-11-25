import _base  # noqa: F401

from src.application.use_cases.validar_cpf_descricao_ad.validar_cpf_descricao_ad import (
    ValidarCpfDescricaoADUseCase,
)
from src.bootstrap import conexoes_producao
from src.infrastructure.logger.logger_config import setup_logger


def main():
    logger = setup_logger()
    logger.warning("==== ROTINA MANUAL: validar CPF na description do AD (ativos) ====")
    logger.warning("Objetivo: auditar se usuarios ativos possuem CPF na description do AD. Esta rotina nao altera AD nem banco.")

    try:
        with conexoes_producao(logger, usar_api=False) as (repo, ad, _modo):
            ValidarCpfDescricaoADUseCase(repo, ad, logger).executar()

    except Exception as e:
        logger.error(f"Erro fatal na rotina manual de validacao CPF description: {e}", exc_info=True)

    finally:
        logger.warning("==== FIM ROTINA MANUAL: validar CPF na description do AD (ativos) ====")


if __name__ == "__main__":
    main()
