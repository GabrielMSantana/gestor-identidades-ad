import pytest

from src.application.use_cases.sincronizar_usuarios.sincronizar_usuarios_busca_dn import SincronizarUsuarioBuscaDN
from src.domain.excecoes import CpfDuplicadoADException
from tests.conftest import GRP_FIN, GRP_TEC, OU_FIN, OU_TEC


@pytest.fixture
def busca(amb, logger):
    return SincronizarUsuarioBuscaDN(amb.ad, logger)


def test_cpf_na_description_tem_prioridade_sobre_homonimo(amb, busca):
    amb.ad.adicionar(f"cn=JOSE SILVA,{OU_FIN}", "jose.silva", "JOSE SILVA", "11111111111", GRP_FIN)
    amb.ad.adicionar(f"cn=JOSE SILVA2,{OU_TEC}", "jose.silva2", "JOSE SILVA", "22222222222", GRP_TEC)

    assert busca.buscar_dn("jose.silva", "JOSE SILVA", "222.222.222-22") == f"cn=JOSE SILVA2,{OU_TEC}"


def test_cpf_duplicado_no_ad_bloqueia(amb, busca):
    amb.ad.adicionar(f"cn=ANA,{OU_FIN}", "ana", "ANA", "11111111111", GRP_FIN)
    amb.ad.adicionar(f"cn=ANA ANTIGA,{OU_TEC}", "ana.old", "ANA ANTIGA", "11111111111", GRP_TEC)

    with pytest.raises(CpfDuplicadoADException):
        busca.buscar_dn("ana", "ANA", "11111111111")


def test_sem_cpf_usa_nome_unico(amb, busca):
    amb.ad.adicionar(f"cn=CARLA ROCHA,{OU_FIN}", "carla.rocha", "CARLA ROCHA", "", GRP_FIN)
    assert busca.buscar_dn("carla.rocha", "CARLA ROCHA", "33333333333") == f"cn=CARLA ROCHA,{OU_FIN}"


def test_nome_repetido_desempata_pelo_login(amb, busca):
    amb.ad.adicionar(f"cn=LUCAS DIAS,{OU_FIN}", "lucas.dias", "LUCAS DIAS", "", GRP_FIN)
    amb.ad.adicionar(f"cn=LUCAS DIAS,{OU_TEC}", "lucas.dias2", "LUCAS DIAS", "", GRP_TEC)

    assert busca.buscar_dn("LUCAS.DIAS2", "LUCAS DIAS", None) == f"cn=LUCAS DIAS,{OU_TEC}"


def test_sem_nome_cai_no_login_exato(amb, busca):
    amb.ad.adicionar(f"cn=Outro Nome,{OU_FIN}", "pedro.lima", "Outro Nome", "", GRP_FIN)
    assert busca.buscar_dn("pedro.lima", "PEDRO LIMA", None) == f"cn=Outro Nome,{OU_FIN}"


def test_nao_encontrado(amb, busca):
    assert busca.buscar_dn("ninguem", "NINGUEM", "44444444444") is None
