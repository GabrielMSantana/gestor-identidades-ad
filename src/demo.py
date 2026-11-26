"""Modo demo: roda o ciclo completo sem AD e sem banco.

Monta um cenário com ~1.300 colaboradores (o tamanho da operação real) e as
situações que o robô trata no dia a dia: admissões, desligamentos, troca de
área, mudança de nome, usuário movido à mão no AD, homônimos, CPF duplicado,
contas antigas sem CPF na description e centro de custo sem OU.

Roda o ciclo três vezes:
1. DRY_RUN: mostra o que faria e prova que o AD não mudou;
2. execução real;
3. de novo, para provar idempotência (nada a fazer, só os bloqueios).
Depois roda a auditoria de CPF na description e a correção.
"""
import logging
import random
import time
from dataclasses import dataclass, field

from src.application.modo_execucao import ModoExecucao
from src.application.use_cases.sincronizar_cpf_descricao.sincronizar_cpf_descricao import SincronizarCpfDescricaoUseCase
from src.application.use_cases.validar_cpf_descricao_ad.validar_cpf_descricao_ad import ValidarCpfDescricaoADUseCase
from src.bootstrap import montar_ciclo
from src.domain.dn import caminho_invalido
from src.domain.status import StatusUsuario
from src.infrastructure.active_directory.ad_memoria import DiretorioADMemoria
from src.infrastructure.repositories.memoria_identidades_repository import BancoIdentidadesMemoria
from src.infrastructure.rh.rh_falso import (
    AREAS,
    GRUPO_DESLIGADOS,
    PASTA_DESLIGADOS,
    Colaborador,
    RHFalso,
    gerar_colaboradores,
    gerar_cpf,
    organograma_exemplo,
)

CENTRO_CUSTO_SEM_OU = "9999"


@dataclass
class Cenario:
    rh: RHFalso
    banco: BancoIdentidadesMemoria
    ad: DiretorioADMemoria
    casos: dict[str, list[str]] = field(default_factory=dict)  # tipo -> CPFs


def _outra_area(rng, atual):
    return rng.choice([cc for cc in AREAS if cc != atual])


def montar_cenario(quantidade: int = 1300, semente: int = 42, logger=None) -> Cenario:
    """Estado de 'ontem' (RH, tabela e AD batendo) + as mudanças de 'hoje' no RH e no AD."""
    rng = random.Random(semente)
    logger = logger or logging.getLogger("demo")
    organograma = organograma_exemplo()
    rh = RHFalso()
    banco = BancoIdentidadesMemoria(rh, organograma, logger)
    ad = DiretorioADMemoria(PASTA_DESLIGADOS, logger, grupo_desligados=GRUPO_DESLIGADOS)

    colaboradores = gerar_colaboradores(quantidade, rng)

    # Homônimos: dois colaboradores diferentes com exatamente o mesmo nome
    colaboradores[1].nome = colaboradores[0].nome

    def provisionar(c: Colaborador, com_cpf=True):
        """Colaborador que já existia ontem: está no RH, na tabela e no AD."""
        rh.adicionar(c)
        ou, grupo = organograma.destino(c.id_centro_custo)
        dn = f"cn={c.nome},{ou}"
        login = banco._gerar_login(c.nome)
        banco.inserir_usuario(c.nome, login, c.cpf, dn, grupo, StatusUsuario.ATIVO, c.id_centro_custo, c.centro_custo, c.funcao)
        ad.adicionar(dn, login, c.nome, c.cpf if com_cpf else "", grupo)

    def amostra(n, disponiveis):
        escolhidos = rng.sample(sorted(disponiveis), n)
        disponiveis.difference_update(escolhidos)
        return escolhidos

    n = lambda pct: max(1, round(quantidade * pct))  # noqa: E731
    indices_livres = set(range(2, quantidade))
    novos = set(amostra(n(0.02), indices_livres))
    sem_cpf = set(amostra(n(0.03), indices_livres))

    for i, c in enumerate(colaboradores):
        if i not in novos:
            provisionar(c, com_cpf=i not in sem_cpf)

    casos: dict[str, list[str]] = {"admissoes": [], "sem_cpf_na_description": [colaboradores[i].cpf for i in sem_cpf]}

    # --- mudanças de hoje -------------------------------------------------
    for i in sorted(novos):  # admissões (2 delas com centro de custo que ainda não tem OU)
        c = colaboradores[i]
        if len(casos.setdefault("centro_custo_sem_ou", [])) < 2:
            c.id_centro_custo, c.centro_custo = CENTRO_CUSTO_SEM_OU, "AREA NOVA"
            casos["centro_custo_sem_ou"].append(c.cpf)
        else:
            casos["admissoes"].append(c.cpf)
        rh.adicionar(c)

    casos["troca_de_area"] = []
    for i in amostra(n(0.015), indices_livres):
        c = colaboradores[i]
        c.id_centro_custo = _outra_area(rng, c.id_centro_custo)
        c.centro_custo = AREAS[c.id_centro_custo]
        casos["troca_de_area"].append(c.cpf)

    casos["mudanca_de_nome"] = []
    for i in amostra(n(0.006), indices_livres):
        c = colaboradores[i]
        c.nome = f"{c.nome} {rng.choice(['MACHADO', 'TEIXEIRA', 'MOURA', 'CAMPOS'])}"
        casos["mudanca_de_nome"].append(c.cpf)

    casos["desligamentos"] = []
    for i in amostra(n(0.015), indices_livres):
        colaboradores[i].ativo = False
        casos["desligamentos"].append(colaboradores[i].cpf)

    # Usuário arrastado para a OU errada direto no AD (o banco continua certo)
    casos["movido_a_mao_no_ad"] = []
    for i in amostra(n(0.005), indices_livres):
        c = colaboradores[i]
        usuario = ad.por_login(banco._por_cpf(c.cpf)[0]["NM_LOGIN"])
        ou_errada, _ = organograma.destino(_outra_area(rng, c.id_centro_custo))
        usuario.dn = f"cn={c.nome},{ou_errada}"
        casos["movido_a_mao_no_ad"].append(c.cpf)

    # Um dos homônimos troca de área: o CPF garante que o certo é movido
    homonimo = colaboradores[0]
    homonimo.id_centro_custo = _outra_area(rng, homonimo.id_centro_custo)
    homonimo.centro_custo = AREAS[homonimo.id_centro_custo]
    casos["homonimo_que_troca_de_area"] = [homonimo.cpf]
    casos["homonimo_que_fica"] = [colaboradores[1].cpf]

    # CPF duplicado no AD (conta antiga esquecida) + troca de área: tem que bloquear
    c = colaboradores[amostra(1, indices_livres)[0]]
    c.id_centro_custo = _outra_area(rng, c.id_centro_custo)
    c.centro_custo = AREAS[c.id_centro_custo]
    ou_antiga, grupo_antigo = organograma.destino(_outra_area(rng, c.id_centro_custo))
    ad.adicionar(f"cn={c.nome} (ANTIGO),{ou_antiga}", f"conta.antiga.{gerar_cpf(rng)[:4]}", f"{c.nome} (ANTIGO)", c.cpf, grupo_antigo)
    casos["cpf_duplicado_no_ad"] = [c.cpf]

    return Cenario(rh, banco, ad, casos)


# ---------------------------------------------------------------- execução

def _rodar_ciclo(cenario: Cenario, modo: ModoExecucao, logger) -> dict[str, dict[str, int]]:
    cenario.banco.dry_run = modo.dry_run
    cenario.ad.dry_run = modo.dry_run
    operacoes_antes = len(cenario.ad.operacoes)
    ciclo = montar_ciclo(cenario.banco, cenario.ad, logger, modo)
    ciclo.run()

    return {
        "criacao": {
            "simulados": len(cenario.banco.listar_pendentes_criacao()) if modo.dry_run else 0,
            "criados": sum(1 for op, _ in cenario.ad.operacoes[operacoes_antes:] if op == "criar"),
            "sem_ou_aguardando": sum(
                1 for u in cenario.banco.usuarios.values()
                if u["TP_STATUS"] == StatusUsuario.PENDENTE and caminho_invalido(u["USER_DN"])
            ),
        },
        "renomeacao": {"renomeados": ciclo.atualizar.renomeados, "simulados": ciclo.atualizar.dry_run, "falhas": ciclo.atualizar.falhas},
        "movimentacao": {
            "movidos": ciclo.modificar.movidos, "simulados": ciclo.modificar.dry_run_movimentos,
            "bloqueados": ciclo.modificar.bloqueados, "falhas": ciclo.modificar.falhas,
        },
        "sincronizacao": {
            "ja_corretos": ciclo.sincronizar.ja_corretos, "movidos": ciclo.sincronizar.movidos,
            "simulados": ciclo.sincronizar.dry_run_movimentos, "bloqueados": ciclo.sincronizar.bloqueados,
            "nao_encontrados": ciclo.sincronizar.nao_encontrados,
        },
        "desligamento": {
            "desativados": ciclo.desativar.desativados, "ja_em_desligados": ciclo.desativar.ja_em_desligados,
            "simulados": ciclo.desativar.dry_run, "erros": len(ciclo.desativar.erros),
        },
    }


def _imprimir(titulo, resumo):
    print(f"\n== {titulo}")
    for fluxo, numeros in resumo.items():
        texto = ", ".join(f"{k}={v}" for k, v in numeros.items())
        print(f"  {fluxo:<14} {texto}")


def executar_demo(quantidade: int = 1300, semente: int = 42, logger=None) -> dict[str, object]:
    logger = logger or logging.getLogger("demo")
    inicio = time.perf_counter()
    cenario = montar_cenario(quantidade, semente, logger)

    print(f"Cenario: {len(cenario.rh.colaboradores)} colaboradores no RH, {len(cenario.ad.usuarios)} contas no AD")
    print("Mudancas de hoje: " + ", ".join(f"{k}={len(v)}" for k, v in cenario.casos.items()))

    # 1) DRY_RUN
    ad_antes = cenario.ad.snapshot()
    simulado = _rodar_ciclo(cenario, ModoExecucao(dry_run=True, executar_procs=True), logger)
    ad_intacto = cenario.ad.snapshot() == ad_antes and not cenario.ad.operacoes
    _imprimir("1) DRY_RUN (simulacao)", simulado)
    print(f"  AD intacto apos DRY_RUN: {ad_intacto}")

    # 2) real
    real = _rodar_ciclo(cenario, ModoExecucao(dry_run=False), logger)
    _imprimir("2) Execucao real", real)

    # 3) idempotência
    operacoes_antes = len(cenario.ad.operacoes)
    repeticao = _rodar_ciclo(cenario, ModoExecucao(dry_run=False), logger)
    novas_operacoes = len(cenario.ad.operacoes) - operacoes_antes
    _imprimir("3) Rodando de novo (idempotencia)", repeticao)
    print(f"  Escritas no AD na segunda execucao: {novas_operacoes}")

    # 4) auditoria e correção do CPF na description
    modo = ModoExecucao(dry_run=False)
    auditoria = ValidarCpfDescricaoADUseCase(cenario.banco, cenario.ad, logger)
    auditoria.executar()
    sem_cpf_antes = auditoria.nao_encontrados
    correcao = SincronizarCpfDescricaoUseCase(cenario.banco, cenario.ad, logger, modo)
    correcao.executar()
    auditoria.executar()
    print("\n== 4) Rotina manual: CPF na description")
    print(f"  sem CPF antes={sem_cpf_antes}, preenchidos={correcao.atualizados}, "
          f"sem CPF depois={auditoria.nao_encontrados}, duplicados no AD={auditoria.duplicados}")

    # Conferências que a demo garante
    homonimo_movido = cenario.casos["homonimo_que_troca_de_area"][0]
    homonimo_parado = cenario.casos["homonimo_que_fica"][0]
    conferencias = {
        "ad_intacto_no_dry_run": ad_intacto,
        "segunda_execucao_sem_escritas": novas_operacoes == 0,
        "homonimo_certo_movido": _ou_bate_com_rh(cenario, homonimo_movido) and _ou_bate_com_rh(cenario, homonimo_parado),
        "cpf_duplicado_bloqueado": repeticao["movimentacao"]["bloqueados"] >= 1,
    }
    print("\n== Conferencias")
    for nome, ok in conferencias.items():
        print(f"  {'OK ' if ok else 'FALHOU'} {nome}")
    print(f"\nduracao_s: {time.perf_counter() - inicio:.2f}")

    return {"cenario": cenario, "simulado": simulado, "real": real, "repeticao": repeticao,
            "conferencias": conferencias, "novas_operacoes": novas_operacoes}


def _ou_bate_com_rh(cenario: Cenario, cpf: str) -> bool:
    from src.domain.dn import caminho_pai, normalizar_para_comparar

    colaborador = cenario.rh.colaboradores[cpf]
    ou, _ = cenario.banco.organograma.destino(colaborador.id_centro_custo)
    contas = [u for u in cenario.ad.usuarios if u.description == cpf]
    return len(contas) == 1 and normalizar_para_comparar(caminho_pai(contas[0].dn)) == normalizar_para_comparar(ou)
