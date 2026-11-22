"""Configuração lida do .env.

As variáveis só são exigidas quando o recurso é usado de fato: o modo demo e os
testes rodam sem banco, sem AD e sem SMTP configurados.
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from src.application.modo_execucao import ModoExecucao

load_dotenv()


def _env_flag(nome_variavel, default="false"):
    valor = os.getenv(nome_variavel, default)
    return str(valor).strip().lower() in ("1", "true", "yes", "y", "sim", "s")


def _env_obrigatoria(nome: str) -> str:
    valor = os.getenv(nome)
    if valor is None or valor.strip() == "":
        raise ValueError(f"A variável de ambiente '{nome}' não foi definida.")
    return valor.strip().strip("'\"")


def _env_lista(nome: str) -> list[str]:
    bruto = os.getenv(nome, "")
    return [item.strip() for item in bruto.split(",") if item.strip()]


@dataclass(frozen=True)
class ConfigBanco:
    servidor: str
    banco: str
    banco_credenciais: str
    usuario: str
    senha: str
    driver: str


@dataclass(frozen=True)
class ConfigAD:
    servidor: str
    usuario: str
    senha: str
    base_dn: str
    pasta_desligados: str


@dataclass(frozen=True)
class ConfigApiAD:
    url_base: str
    id_credencial: int


@dataclass(frozen=True)
class ConfigEmail:
    usuario: str
    senha: str
    destinatarios: str
    copia: str | None
    smtp_host: str
    smtp_porta: int


@dataclass(frozen=True)
class ConfigRegras:
    # CPFs de contas que a sincronização não deve mexer (diretoria, contas de serviço)
    cpfs_ignorar_sincronia: list[str] = field(default_factory=list)
    # Rotina manual de CPF/description: corrige NM_LOGIN quando o nome no AD tiver match único
    cpf_descricao_corrigir_login: bool = False


def carregar_modo_execucao() -> ModoExecucao:
    return ModoExecucao(
        dry_run=_env_flag("DRY_RUN"),
        executar_procs=_env_flag("DRY_RUN_EXECUTE_PROCS", "true"),
    )


def carregar_config_banco() -> ConfigBanco:
    return ConfigBanco(
        servidor=_env_obrigatoria("DB_SERVER"),
        banco=os.getenv("DB_NAME", "IDENTIDADES"),
        banco_credenciais=os.getenv("DB_NAME_CREDENCIAIS", "SEGURANCA"),
        usuario=_env_obrigatoria("DB_USER"),
        senha=_env_obrigatoria("DB_PASSWORD"),
        driver=os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server"),
    )


def carregar_config_ad() -> ConfigAD:
    return ConfigAD(
        servidor=_env_obrigatoria("AD_SERVER"),
        usuario=_env_obrigatoria("AD_USER"),
        senha=_env_obrigatoria("AD_PASS"),
        base_dn=_env_obrigatoria("AD_BASE_DN"),
        pasta_desligados=_env_obrigatoria("AD_PASTA_DESLIGADOS"),
    )


def carregar_config_api_ad() -> ConfigApiAD:
    return ConfigApiAD(
        url_base=_env_obrigatoria("AD_API_URL").rstrip("/"),
        id_credencial=int(os.getenv("AD_API_ID_CREDENCIAL", "1")),
    )


def carregar_config_email() -> ConfigEmail:
    return ConfigEmail(
        usuario=_env_obrigatoria("EMAIL_USER"),
        senha=_env_obrigatoria("EMAIL_PASS"),
        destinatarios=_env_obrigatoria("EMAIL_DEST"),
        copia=os.getenv("EMAIL_CC") or None,
        smtp_host=os.getenv("SMTP_HOST", "smtp.example.com"),
        smtp_porta=int(os.getenv("SMTP_PORT", "587")),
    )


def carregar_config_regras() -> ConfigRegras:
    return ConfigRegras(
        cpfs_ignorar_sincronia=_env_lista("CPFS_IGNORAR_SINCRONIA"),
        cpf_descricao_corrigir_login=_env_flag("CPF_DESCRICAO_CORRIGIR_LOGIN"),
    )
