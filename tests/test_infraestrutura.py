"""Adapters reais testados sem rede e sem banco (dublês simples)."""
import pytest

from src.infrastructure.active_directory.ad_service import _escapar
from src.infrastructure.database.sqlserver_repository import ACAO_REALIZADA
from src.infrastructure.external.ad_api_client import ADAPIClient
from src.infrastructure.repositories.sqlserver_identidades_repository import SqlServerIdentidadesRepository

# ---------------------------------------------------------------- API do AD

class _Resposta:
    def __init__(self, status_code, corpo):
        self.status_code = status_code
        self._corpo = corpo

    def json(self):
        return self._corpo


class _HttpFalso:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def post(self, url, headers, json, timeout):
        self.chamadas.append((url, headers["Authorization"], json))
        return self.respostas.pop(0)


class _AuthFalso:
    def __init__(self, tokens):
        self.tokens = list(tokens)
        self.renovacoes = 0

    def obter_token_ad(self, forcar_renovacao=False):
        if forcar_renovacao:
            self.renovacoes += 1
        return self.tokens.pop(0) if self.tokens else None


def test_token_expirado_e_renovado_e_a_chamada_repetida_uma_vez(logger):
    http = _HttpFalso([_Resposta(401, {}), _Resposta(200, {"status": "sucesso"})])
    auth = _AuthFalso(["token-velho", "token-novo"])
    api = ADAPIClient("http://api.example.com", auth, logger, sessao=http)

    resposta = api.desativar_usuario("cn=Ana,ou=TI", cpf="111.111.111-11")

    assert resposta == {"status": "sucesso"}
    assert auth.renovacoes == 1
    assert [c[1] for c in http.chamadas] == ["Bearer token-velho", "Bearer token-novo"]
    assert http.chamadas[0][2] == {"userDn": "cn=Ana,ou=TI", "cpf": "11111111111"}


def test_token_que_nao_renova_devolve_erro_sem_loop(logger):
    http = _HttpFalso([_Resposta(401, {})])
    api = ADAPIClient("http://api.example.com", _AuthFalso(["token-velho"]), logger, sessao=http)

    assert api.criar_usuario("Ana", "Lima", "Ana Lima", "ana.lima", "x", "cn=a", "cn=g", "1") == {"error": "TOKEN_EXPIRED"}
    assert len(http.chamadas) == 1


def test_erro_http_devolve_corpo_da_api(logger):
    http = _HttpFalso([_Resposta(409, {"erro": "entryAlreadyExists"})])
    api = ADAPIClient("http://api.example.com", _AuthFalso(["t"]), logger, sessao=http)

    assert api.modificar_usuario("a", "b", "c", "d") == {"erro": "entryAlreadyExists"}


# ---------------------------------------------------------------- LDAP

def test_filtro_ldap_escapa_caracteres_especiais():
    assert _escapar("ANA (TI)*") == "ANA \\28TI\\29\\2a"


# ---------------------------------------------------------------- SQL Server

class _DbFalso:
    def __init__(self):
        self.execucoes = []

    def execute(self, query, params=()):
        self.execucoes.append((" ".join(query.split()), params))
        return ACAO_REALIZADA


def test_updates_usam_parametros_e_nao_concatenam_valores(logger):
    db = _DbFalso()
    repo = SqlServerIdentidadesRepository(db, logger, dry_run=False)

    repo.atualizar_tabela_usuarios("11111111111", "cn=O'Neil,ou=TI", "cn=GRP")

    query, params = db.execucoes[0]
    assert "O'Neil" not in query
    assert params == ("cn=O'Neil,ou=TI", "cn=GRP", "11111111111")


@pytest.mark.parametrize("chamada", [
    lambda r: r.atualizar_status_criacao(1, "ana", "sucesso"),
    lambda r: r.atualizar_user_dn_renomeado("1", "cn=a"),
    lambda r: r.atualizar_fila_movimentacao("1", "cn=a", "cn=g"),
    lambda r: r.atualizar_tabela_usuarios("1", "cn=a", "cn=g"),
    lambda r: r.atualizar_desativado(1, "cn=a", "ana"),
    lambda r: r.atualizar_login(1, "1", "ANA"),
])
def test_dry_run_no_repositorio_sql_nao_executa_update(logger, chamada):
    db = _DbFalso()
    chamada(SqlServerIdentidadesRepository(db, logger, dry_run=True))
    assert db.execucoes == []


def test_cpfs_ignorados_viram_parametros(logger):
    db = _DbFalso()
    db.execute = lambda q, p=(): db.execucoes.append((" ".join(q.split()), p)) or []
    repo = SqlServerIdentidadesRepository(db, logger, dry_run=False)

    repo.listar_ativos_para_sincronia(["111.111.111-11", "22222222222"])

    query, params = db.execucoes[0]
    assert "NOT IN (?, ?)" in query
    assert params == ("11111111111", "22222222222")
