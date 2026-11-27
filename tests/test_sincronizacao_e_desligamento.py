from src.application.use_cases.desativar_usuario.desativar_usuario_service import DesativarUsuarioService
from src.application.use_cases.sincronizar_desligados.sincronizar_desligados import SincronizarDesligadosUseCase
from src.application.use_cases.sincronizar_usuarios.sincronizar_usuarios import SincronizarUsuariosUseCase
from src.domain.status import StatusUsuario
from src.infrastructure.rh.rh_falso import GRUPO_DESLIGADOS, PASTA_DESLIGADOS
from tests.conftest import GRP_TEC, OU_FIN, OU_TEC, REAL, SIMULACAO


def test_sincronizacao_devolve_quem_foi_movido_a_mao(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA")
    usuario_ad = amb.ad.por_login("ana.lima")
    usuario_ad.dn, usuario_ad.grupos = f"cn=ANA LIMA,{OU_TEC}", [GRP_TEC]

    service = SincronizarUsuariosUseCase(amb.banco, amb.ad, logger, amb.modo(REAL))
    service.executar()

    assert service.movidos == 1
    assert usuario_ad.dn == f"cn=ANA LIMA,{OU_FIN}"


def test_sincronizacao_respeita_cpfs_ignorados(amb, logger):
    amb.colaborador("11111111111", "DIRETORA GERAL")
    amb.ad.por_login("diretora.geral").dn = f"cn=DIRETORA GERAL,{OU_TEC}"

    service = SincronizarUsuariosUseCase(amb.banco, amb.ad, logger, amb.modo(REAL), cpfs_ignorados=["111.111.111-11"])
    service.executar()

    assert service.total == 0
    assert amb.ad.operacoes == []


def test_sincronizacao_conta_quem_nao_esta_no_ad(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA", no_ad=False)

    service = SincronizarUsuariosUseCase(amb.banco, amb.ad, logger, amb.modo(REAL))
    service.executar()

    assert service.nao_encontrados == 1


def test_desligado_no_rh_e_desativado_e_movido(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA")
    amb.rh.colaboradores["11111111111"].ativo = False
    amb.preparar()

    service = DesativarUsuarioService(amb.banco, amb.ad, logger, amb.modo(REAL))
    service.executar()

    usuario_ad = amb.ad.por_login("ana.lima")
    assert service.desativados == 1
    assert not usuario_ad.ativo
    assert usuario_ad.dn == f"cn=ANA LIMA,{PASTA_DESLIGADOS}"
    assert usuario_ad.grupos == [GRUPO_DESLIGADOS]  # o grupo que corta as permissões
    assert amb.usuario("11111111111")["TP_STATUS"] == StatusUsuario.DESLIGADO


def test_desligado_ja_na_pasta_so_atualiza_banco(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA")
    amb.rh.colaboradores["11111111111"].ativo = False
    amb.ad.por_login("ana.lima").dn = f"cn=ANA LIMA,{PASTA_DESLIGADOS}"
    amb.preparar()

    service = DesativarUsuarioService(amb.banco, amb.ad, logger, amb.modo(REAL))
    service.executar()

    assert (service.desativados, service.ja_em_desligados) == (0, 1)
    assert amb.ad.operacoes == []
    assert amb.usuario("11111111111")["TP_STATUS"] == StatusUsuario.DESLIGADO


def test_desligamento_em_dry_run_nao_altera_nada(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA")
    amb.rh.colaboradores["11111111111"].ativo = False
    amb.preparar()

    service = DesativarUsuarioService(amb.banco, amb.ad, logger, amb.modo(SIMULACAO))
    service.executar()

    assert service.dry_run == 1
    assert amb.ad.por_login("ana.lima").ativo
    assert amb.usuario("11111111111")["TP_STATUS"] == StatusUsuario.ATIVO


def test_rotina_desligados_corrige_quem_ficou_fora_da_pasta(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA")
    amb.usuario("11111111111")["TP_STATUS"] = int(StatusUsuario.DESLIGADO)  # banco diz desligado, AD não

    rotina = SincronizarDesligadosUseCase(amb.banco, amb.ad, logger, amb.modo(REAL), PASTA_DESLIGADOS)
    rotina.executar()

    assert rotina.movidos_desligados == 1
    assert amb.ad.esta_em_desligados(amb.ad.por_login("ana.lima").dn)


def test_rotina_desligados_bloqueada_sem_pasta_configurada(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA")
    amb.usuario("11111111111")["TP_STATUS"] = int(StatusUsuario.DESLIGADO)

    rotina = SincronizarDesligadosUseCase(amb.banco, amb.ad, logger, amb.modo(REAL), pasta_desligados="")
    rotina.executar()

    assert amb.ad.operacoes == []
