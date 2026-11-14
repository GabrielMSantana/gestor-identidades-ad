"""Regras puras sobre Distinguished Names (DN) do Active Directory e CPF.

Não dependem de banco, LDAP nem API: por isso ficam no domínio e são usadas
por todos os casos de uso.
"""

# Valores que a procedure de criação/movimentação grava no lugar do DN quando
# não consegue calcular o caminho (centro de custo sem OU ou função genérica).
CAMINHOS_INVALIDOS = (
    "CENTRO_CUSTO INVALIDO",
    "NAO POSSUI CAMINHO (FUNCAO GENERICA)",
)

_CAMINHOS_INVALIDOS_NORMALIZADOS = (
    "centro_custo invalido",
    "nao possui caminho",
)


def normalizar_dn(dn: str) -> str:
    """Padroniza o caminho para componentes em minúsculo (CN, OU)"""
    if not dn:
        return dn
    return (
        dn
        .replace("OU=", "ou=")
        .replace("CN=", "cn=")
    )


def normalizar_para_comparar(dn: str) -> str:
    """DN pronto para comparação: minúsculo e sem espaços."""
    if not dn:
        return ""
    return normalizar_dn(dn).replace(" ", "").strip().lower()


def mesmo_dn(dn_a: str, dn_b: str) -> bool:
    if not dn_a or not dn_b:
        return False
    return normalizar_para_comparar(dn_a) == normalizar_para_comparar(dn_b)


def extrair_cn(dn: str) -> str:
    """Devolve só o nome do objeto: 'cn=Fulano,ou=X,...' -> 'Fulano'."""
    dn = str(dn or "").strip()
    if not dn or "," not in dn or "=" not in dn:
        return ""
    return dn[dn.find("=") + 1:dn.find(",")].strip()


def caminho_pai(dn: str) -> str:
    """Devolve a OU onde o objeto está: 'cn=Fulano,ou=X,dc=y' -> 'ou=X,dc=y'."""
    dn = str(dn or "").strip()
    if "," not in dn:
        return ""
    return dn[dn.find(",") + 1:].strip()


def caminho_invalido(dn: str) -> bool:
    dn_norm = str(dn or "").strip().lower()
    return any(valor in dn_norm for valor in _CAMINHOS_INVALIDOS_NORMALIZADOS)


def normalizar_cpf(cpf) -> str:
    if cpf is None:
        return ""
    return "".join(ch for ch in str(cpf) if ch.isdigit())
