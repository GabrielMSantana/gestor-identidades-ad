import logging

import pytest

from src.application.modo_execucao import ModoExecucao
from src.domain.status import StatusUsuario
from src.infrastructure.active_directory.ad_memoria import DiretorioADMemoria
from src.infrastructure.repositories.memoria_identidades_repository import BancoIdentidadesMemoria
from src.infrastructure.rh.rh_falso import GRUPO_DESLIGADOS, PASTA_DESLIGADOS, Colaborador, RHFalso, organograma_exemplo

OU_FIN, GRP_FIN = organograma_exemplo().destino("2101")
OU_TEC, GRP_TEC = organograma_exemplo().destino("2104")

REAL = ModoExecucao(dry_run=False)
SIMULACAO = ModoExecucao(dry_run=True, executar_procs=True)


@pytest.fixture
def logger():
    return logging.getLogger("testes")


class Ambiente:
    """RH + banco + AD em memória já 'batendo', com helpers para montar casos."""

    def __init__(self, logger):
        self.rh = RHFalso()
        self.banco = BancoIdentidadesMemoria(self.rh, organograma_exemplo(), logger)
        self.ad = DiretorioADMemoria(PASTA_DESLIGADOS, logger, grupo_desligados=GRUPO_DESLIGADOS)

    def colaborador(self, cpf, nome, id_cc="2101", *, no_ad=True, com_cpf=True, login=None, ativo_na_tabela=True):
        """Colaborador já existente: RH + tabela (+ AD)."""
        c = self.rh.adicionar(Colaborador(cpf, nome, id_cc, "Area", "ANALISTA"))
        ou, grupo = self.banco.organograma.destino(id_cc)
        dn = f"cn={nome},{ou}"
        login = login or self.banco._gerar_login(nome)
        if ativo_na_tabela:
            self.banco.inserir_usuario(nome, login, cpf, dn, grupo, StatusUsuario.ATIVO, id_cc)
        if no_ad:
            self.ad.adicionar(dn, login, nome, cpf if com_cpf else "", grupo)
        return c

    def modo(self, modo: ModoExecucao):
        self.banco.dry_run = modo.dry_run
        self.ad.dry_run = modo.dry_run
        return modo

    def preparar(self):
        """Roda o batimento (RH -> colaboradores ativos), como o ciclo faz no início."""
        self.banco.executar_batimento()
        return self

    def usuario(self, cpf):
        return self.banco._por_cpf(cpf)[0]


@pytest.fixture
def amb(logger):
    return Ambiente(logger)
