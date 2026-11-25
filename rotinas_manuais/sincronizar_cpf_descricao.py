import _base  # noqa: F401

from src.application.use_cases.sincronizar_cpf_descricao.sincronizar_cpf_descricao import (
    SincronizarCpfDescricaoUseCase,
)
from src.bootstrap import conexoes_producao
from src.config.settings import carregar_config_regras
from src.infrastructure.logger.logger_config import setup_logger


def main(somente_desligados=False):
    logger = setup_logger()
    alvo = "desligados" if somente_desligados else "ativos"
    regras = carregar_config_regras()

    logger.warning(f"==== ROTINA MANUAL: sincronizar CPF na description do AD ({alvo}) ====")
    logger.warning("Objetivo: preencher/ajustar a description do usuario no AD com o CPF da tabela de controle.")

    try:
        # Só LDAP: esta rotina não usa a API do AD
        with conexoes_producao(logger, usar_api=False) as (repo, ad, modo):
            if modo.dry_run:
                logger.warning("DRY_RUN ativo: nenhuma description sera alterada no AD e nenhum NM_LOGIN sera atualizado no banco.")
            else:
                logger.warning("DRY_RUN inativo: a rotina pode alterar description no AD via LDAP e, se habilitado, corrigir NM_LOGIN no banco.")

            if regras.cpf_descricao_corrigir_login:
                logger.warning("CPF_DESCRICAO_CORRIGIR_LOGIN ativo: a rotina pode corrigir NM_LOGIN na tabela quando houver match unico por nome no AD.")
            else:
                logger.warning("CPF_DESCRICAO_CORRIGIR_LOGIN inativo: a rotina nao corrigira NM_LOGIN na tabela.")

            SincronizarCpfDescricaoUseCase(
                repo,
                ad,
                logger,
                modo,
                corrigir_login_por_nome=regras.cpf_descricao_corrigir_login,
                somente_desligados=somente_desligados,
            ).executar()

    except Exception as e:
        logger.error(f"Erro fatal na rotina manual de CPF description: {e}", exc_info=True)

    finally:
        logger.warning(f"==== FIM ROTINA MANUAL: sincronizar CPF na description do AD ({alvo}) ====")


if __name__ == "__main__":
    main()
