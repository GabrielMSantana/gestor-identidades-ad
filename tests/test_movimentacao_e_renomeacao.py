from src.application.use_cases.atualizar_usuario.atualizar_usuario_service import AtualizarUsuarioService
from src.application.use_cases.modificar_usuario.modificar_usuario_service import ModificarUsuarioService
from tests.conftest import GRP_TEC, OU_FIN, OU_TEC, REAL, SIMULACAO


def _trocar_area(amb, cpf, id_cc):
    amb.rh.colaboradores[cpf].id_centro_custo = id_cc


def test_troca_de_area_move_no_ad_e_atualiza_banco(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA")
    _trocar_area(amb, "11111111111", "2104")
    amb.preparar()

    service = ModificarUsuarioService(amb.banco, amb.ad, logger, amb.modo(REAL))
    service.executar()

    assert service.movidos == 1
    assert amb.ad.por_login("ana.lima").dn == f"cn=ANA LIMA,{OU_TEC}"
    assert amb.ad.por_login("ana.lima").grupos == [GRP_TEC]
    assert amb.usuario("11111111111")["USER_DN"] == f"cn=ANA LIMA,{OU_TEC}"


def test_ja_no_destino_so_atualiza_o_banco(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA")
    _trocar_area(amb, "11111111111", "2104")
    usuario_ad = amb.ad.por_login("ana.lima")
    usuario_ad.dn, usuario_ad.grupos = f"cn=ANA LIMA,{OU_TEC}", [GRP_TEC]  # alguém já moveu à mão
    amb.preparar()

    service = ModificarUsuarioService(amb.banco, amb.ad, logger, amb.modo(REAL))
    service.executar()

    assert (service.movidos, service.ja_no_destino) == (0, 1)
    assert amb.ad.operacoes == []
    assert amb.usuario("11111111111")["USER_DN"] == f"cn=ANA LIMA,{OU_TEC}"


def test_destino_invalido_e_bloqueado(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA")
    _trocar_area(amb, "11111111111", "9999")
    amb.preparar()

    service = ModificarUsuarioService(amb.banco, amb.ad, logger, amb.modo(REAL))
    service.executar()

    assert service.bloqueados == 1
    assert amb.ad.operacoes == []


def test_cpf_duplicado_bloqueia_movimentacao(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA")
    amb.ad.adicionar(f"cn=ANA LIMA (ANTIGA),{OU_FIN}", "ana.antiga", "ANA LIMA (ANTIGA)", "11111111111")
    _trocar_area(amb, "11111111111", "2104")
    amb.preparar()

    service = ModificarUsuarioService(amb.banco, amb.ad, logger, amb.modo(REAL))
    service.executar()

    assert service.bloqueados == 1
    assert amb.ad.operacoes == []


def test_movimentacao_em_dry_run_nao_altera_nada(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA")
    _trocar_area(amb, "11111111111", "2104")
    amb.preparar()
    banco_antes = amb.banco.snapshot()

    service = ModificarUsuarioService(amb.banco, amb.ad, logger, amb.modo(SIMULACAO))
    service.executar()

    assert service.dry_run_movimentos == 1
    assert amb.ad.operacoes == []
    assert amb.banco.snapshot() == banco_antes


def test_mudanca_de_nome_renomeia_pelo_cpf_sem_trocar_login(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA")
    amb.colaborador("22222222222", "ANA LIMA", login="ana.lima2")  # homônimo
    amb.rh.colaboradores["11111111111"].nome = "ANA LIMA ROCHA"
    amb.preparar()

    service = AtualizarUsuarioService(amb.banco, amb.ad, logger, amb.modo(REAL))
    service.executar()

    assert service.renomeados == 1
    assert amb.ad.por_login("ana.lima").dn == f"cn=ANA LIMA ROCHA,{OU_FIN}"
    assert amb.ad.por_login("ana.lima2").dn == f"cn=ANA LIMA,{OU_FIN}"  # o homônimo não foi tocado
    assert amb.usuario("11111111111")["USER_DN"] == f"cn=ANA LIMA ROCHA,{OU_FIN}"

    service.executar()  # segunda vez: nada a fazer
    assert service.total == 0


def test_renomeacao_falha_quando_cpf_nao_esta_no_ad(amb, logger):
    amb.colaborador("11111111111", "ANA LIMA", com_cpf=False)
    amb.rh.colaboradores["11111111111"].nome = "ANA LIMA ROCHA"
    amb.preparar()

    service = AtualizarUsuarioService(amb.banco, amb.ad, logger, amb.modo(REAL))
    service.executar()

    assert (service.renomeados, service.falhas) == (0, 1)
    assert amb.usuario("11111111111")["USER_DN"] == f"cn=ANA LIMA,{OU_FIN}"
