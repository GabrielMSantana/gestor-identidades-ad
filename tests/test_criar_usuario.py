from src.application.use_cases.criar_usuario.criar_usuario_interpretador import CriarUsuarioInterpretador
from src.application.use_cases.criar_usuario.criar_usuario_service import CriarUsuarioService
from src.domain.status import StatusUsuario
from src.infrastructure.rh.rh_falso import Colaborador
from tests.conftest import GRP_FIN, OU_FIN, REAL, SIMULACAO


def _admitir(amb, cpf, nome, id_cc="2101"):
    amb.rh.adicionar(Colaborador(cpf, nome, id_cc, "Area", "ANALISTA"))


def test_cria_admitido_com_cpf_na_description_e_marca_ativo(amb, logger):
    _admitir(amb, "11111111111", "MARIA SOUZA LIMA")
    amb.preparar()

    service = CriarUsuarioService(amb.banco, amb.ad, logger, amb.modo(REAL), gerador_senha=lambda: "Senha#Teste123")
    service.executar()

    usuario_ad = amb.ad.por_login("maria.lima")
    assert usuario_ad.dn == f"cn=MARIA SOUZA LIMA,{OU_FIN}"
    assert usuario_ad.description == "11111111111"
    assert usuario_ad.grupos == [GRP_FIN]
    assert amb.usuario("11111111111")["TP_STATUS"] == StatusUsuario.ATIVO


def test_login_repetido_ganha_sufixo(amb, logger):
    amb.colaborador("22222222222", "MARIA LIMA")
    _admitir(amb, "11111111111", "MARIA SOUZA LIMA")
    amb.preparar()

    CriarUsuarioService(amb.banco, amb.ad, logger, amb.modo(REAL)).executar()

    assert amb.ad.por_login("maria.lima2").description == "11111111111"


def test_centro_de_custo_sem_ou_nao_e_criado(amb, logger):
    _admitir(amb, "11111111111", "MARIA LIMA", id_cc="9999")
    amb.preparar()

    CriarUsuarioService(amb.banco, amb.ad, logger, amb.modo(REAL)).executar()

    assert amb.ad.usuarios == []
    assert amb.usuario("11111111111")["TP_STATUS"] == StatusUsuario.PENDENTE


def test_cpf_invalido_nao_chama_o_ad(amb, logger):
    _admitir(amb, "123", "MARIA LIMA")
    amb.preparar()

    CriarUsuarioService(amb.banco, amb.ad, logger, amb.modo(REAL)).executar()

    assert amb.ad.operacoes == []


def test_dry_run_gera_fila_mas_nao_cria(amb, logger):
    _admitir(amb, "11111111111", "MARIA LIMA")
    amb.preparar()

    CriarUsuarioService(amb.banco, amb.ad, logger, amb.modo(SIMULACAO)).executar()

    assert amb.ad.usuarios == []
    assert amb.usuario("11111111111")["TP_STATUS"] == StatusUsuario.PENDENTE  # a procedure rodou, o update não


def test_interpretador_de_criacao():
    interp = CriarUsuarioInterpretador(None)
    assert interp.interpretar({"status": "sucesso"})[0] == "sucesso"
    assert interp.interpretar({"erro": "entryAlreadyExists"})[0] == "existente"
    assert interp.interpretar({"error": "TOKEN_EXPIRED"})[0] == "erro"
    assert interp.interpretar("timeout")[0] == "erro"
