"""Composição (composition root): liga casos de uso aos adapters.

Produção: SQL Server + LDAP + API interna do AD.
Demo/testes: banco em memória + AD em memória + RH falso.
"""
import os
from collections.abc import Sequence
from contextlib import contextmanager

from src.application.modo_execucao import ModoExecucao
from src.application.use_cases.atualizar_usuario.atualizar_usuario_service import AtualizarUsuarioService
from src.application.use_cases.ciclo_diario import CicloDiario
from src.application.use_cases.criar_usuario.criar_usuario_service import CriarUsuarioService
from src.application.use_cases.desativar_usuario.desativar_usuario_service import DesativarUsuarioService
from src.application.use_cases.modificar_usuario.modificar_usuario_service import ModificarUsuarioService
from src.application.use_cases.relatorios.enviar_relatorio_criacao import EnviarRelatorioCriacao
from src.application.use_cases.relatorios.gerar_relatorio_criacao import GerarRelatorioCriacao
from src.application.use_cases.sincronizar_usuarios.sincronizar_usuarios import SincronizarUsuariosUseCase


def montar_ciclo(repo, ad, logger, modo: ModoExecucao, cpfs_ignorados: Sequence[str] = (), relatorio=None) -> CicloDiario:
    """O mesmo ciclo para produção e demo: só mudam os adapters."""
    return CicloDiario(
        batimento=repo,
        criar=CriarUsuarioService(repo, ad, logger, modo),
        atualizar=AtualizarUsuarioService(repo, ad, logger, modo),
        modificar=ModificarUsuarioService(repo, ad, logger, modo),
        sincronizar=SincronizarUsuariosUseCase(repo, ad, logger, modo, cpfs_ignorados),
        desativar=DesativarUsuarioService(repo, ad, logger, modo),
        logger=logger,
        modo=modo,
        relatorio=relatorio,
    )


# ---------------------------------------------------------------- produção

@contextmanager
def conexoes_producao(logger, usar_api: bool):
    """Abre banco, AD (LDAP) e, se pedido, a API do AD. Fecha o banco no fim."""
    from src.config.settings import carregar_config_ad, carregar_config_api_ad, carregar_config_banco, carregar_modo_execucao
    from src.infrastructure.active_directory.ad_service import ADService
    from src.infrastructure.database.sqlserver_repository import SQLServerRepository
    from src.infrastructure.external.ad_api_client import ADAPIClient
    from src.infrastructure.external.auth_token_service import AuthTokenService
    from src.infrastructure.repositories.sqlserver_identidades_repository import SqlServerIdentidadesRepository

    modo = carregar_modo_execucao()
    config_banco = carregar_config_banco()
    db = SQLServerRepository.a_partir_da_config(config_banco)
    db_credenciais = None

    try:
        api = None
        if usar_api and not modo.dry_run:
            logger.info("Obtendo token JWT para autenticacao na API do AD...")
            config_api = carregar_config_api_ad()
            db_credenciais = SQLServerRepository.a_partir_da_config(config_banco, config_banco.banco_credenciais)
            auth = AuthTokenService(db_credenciais, config_api.url_base, config_api.id_credencial, logger)
            api = ADAPIClient(config_api.url_base, auth, logger)
            if not api.token:
                raise RuntimeError("Token JWT invalido ou nao gerado.")

        ad = ADService(carregar_config_ad(), logger, api=api, dry_run=modo.dry_run)
        repo = SqlServerIdentidadesRepository(db, logger, dry_run=modo.dry_run)
        yield repo, ad, modo
    finally:
        db.close()
        if db_credenciais:
            db_credenciais.close()


def executar_producao(logger) -> None:
    from src.config.settings import carregar_config_email, carregar_config_regras

    regras = carregar_config_regras()
    with conexoes_producao(logger, usar_api=True) as (repo, ad, modo):
        relatorio = None
        if os.getenv("ENVIAR_RELATORIO_CRIACAO", "false").lower() == "true":
            from src.infrastructure.mail.smtp_client import SMTPClient

            gerador = GerarRelatorioCriacao(repo, logger, modo)
            relatorio = EnviarRelatorioCriacao(SMTPClient(carregar_config_email()), gerador, logger, modo)

        montar_ciclo(repo, ad, logger, modo, regras.cpfs_ignorar_sincronia, relatorio).run()
