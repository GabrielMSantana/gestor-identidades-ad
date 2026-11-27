from src.application.use_cases.sincronizar_cpf_descricao.sincronizar_cpf_descricao import SincronizarCpfDescricaoUseCase
from src.application.use_cases.validar_cpf_descricao_ad.validar_cpf_descricao_ad import ValidarCpfDescricaoADUseCase
from tests.conftest import OU_FIN, REAL, SIMULACAO


def test_preenche_description_vazia(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA", com_cpf=False)

    rotina = SincronizarCpfDescricaoUseCase(amb.banco, amb.ad, logger, amb.modo(REAL))
    rotina.executar()

    assert rotina.atualizados == 1
    assert amb.ad.por_login("ana.lima").description == "11111111111"


def test_nao_sobrescreve_description_com_outro_valor(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA", com_cpf=False)
    amb.ad.por_login("ana.lima").description = "Conta do financeiro"

    rotina = SincronizarCpfDescricaoUseCase(amb.banco, amb.ad, logger, amb.modo(REAL))
    rotina.executar()

    assert rotina.ignorados == 1
    assert amb.ad.por_login("ana.lima").description == "Conta do financeiro"


def test_nome_diferente_no_ad_nao_recebe_cpf(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA", com_cpf=False)
    amb.ad.por_login("ana.lima").nome = "OUTRA PESSOA"
    amb.ad.por_login("ana.lima").dn = f"cn=OUTRA PESSOA,{OU_FIN}"

    rotina = SincronizarCpfDescricaoUseCase(amb.banco, amb.ad, logger, amb.modo(REAL))
    rotina.executar()

    assert rotina.atualizados == 0
    assert amb.ad.por_login("ana.lima").description == ""


def test_aceita_nome_truncado_no_ad(amb, logger):
    amb.colaborador("11111111111", "MARIA APARECIDA SOUZA", com_cpf=False)
    usuario = amb.ad.por_login("maria.souza")
    usuario.nome = "MARIA APARECIDA SOUZ"
    usuario.dn = f"cn=MARIA APARECIDA SOUZ,{OU_FIN}"

    rotina = SincronizarCpfDescricaoUseCase(amb.banco, amb.ad, logger, amb.modo(REAL))
    rotina.executar()

    assert rotina.atualizados == 1


def test_corrige_login_errado_na_tabela_quando_nome_e_unico(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA", com_cpf=False)
    amb.usuario("11111111111")["NM_LOGIN"] = "ANA.ERRADO"

    rotina = SincronizarCpfDescricaoUseCase(amb.banco, amb.ad, logger, amb.modo(REAL), corrigir_login_por_nome=True)
    rotina.executar()

    assert rotina.logins_corrigidos == 1
    assert amb.usuario("11111111111")["NM_LOGIN"] == "ANA.LIMA"
    assert amb.ad.por_login("ana.lima").description == "11111111111"


def test_dry_run_nao_altera_description(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA", com_cpf=False)

    SincronizarCpfDescricaoUseCase(amb.banco, amb.ad, logger, amb.modo(SIMULACAO)).executar()

    assert amb.ad.por_login("ana.lima").description == ""


def test_auditoria_classifica_e_nao_altera(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA")
    amb.colaborador("22222222222", "BRUNO DIAS", com_cpf=False)
    amb.colaborador("33333333333", "CARLA ROCHA")
    amb.ad.adicionar(f"cn=CARLA ANTIGA,{OU_FIN}", "carla.antiga", "CARLA ANTIGA", "33333333333")
    antes = amb.ad.snapshot()

    auditoria = ValidarCpfDescricaoADUseCase(amb.banco, amb.ad, logger)
    auditoria.executar()

    assert (auditoria.encontrados, auditoria.nao_encontrados, auditoria.duplicados) == (1, 1, 1)
    assert auditoria._formatar_cpfs_para_sql(auditoria.lista_nao_encontrados) == "('22222222222')"
    assert amb.ad.snapshot() == antes
