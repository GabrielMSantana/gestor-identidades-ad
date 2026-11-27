from datetime import datetime

from src.application.modo_execucao import ModoExecucao
from src.application.use_cases.relatorios.enviar_relatorio_criacao import EnviarRelatorioCriacao
from src.application.use_cases.relatorios.gerar_relatorio_criacao import GerarRelatorioCriacao
from src.demo import executar_demo


def test_demo_completa_passa_em_todas_as_conferencias(logger, capsys):
    resultado = executar_demo(quantidade=400, semente=7, logger=logger)

    assert all(resultado["conferencias"].values()), resultado["conferencias"]
    casos = resultado["cenario"].casos
    real = resultado["real"]
    assert real["criacao"]["criados"] == len(casos["admissoes"])
    assert real["renomeacao"]["renomeados"] == len(casos["mudanca_de_nome"])
    assert real["desligamento"]["desativados"] == len(casos["desligamentos"])
    assert real["sincronizacao"]["movidos"] == len(casos["movido_a_mao_no_ad"])
    # trocas de área + o homônimo que mudou; o CPF duplicado fica bloqueado
    assert real["movimentacao"]["movidos"] == len(casos["troca_de_area"]) + 1
    assert real["movimentacao"]["bloqueados"] == 1


def test_dry_run_sem_procs_nao_mexe_em_nada(amb, logger):
    from src.bootstrap import montar_ciclo
    from src.infrastructure.rh.rh_falso import Colaborador

    amb.rh.adicionar(Colaborador("11111111111", "NOVA PESSOA", "2101", "Area", "ANALISTA"))
    modo = amb.modo(ModoExecucao(dry_run=True, executar_procs=False))

    montar_ciclo(amb.banco, amb.ad, logger, modo).run()

    assert amb.banco.usuarios == {}
    assert amb.banco.colaboradores_ativos == {}
    assert amb.ad.operacoes == []


class _EmailFalso:
    def __init__(self):
        self.enviados = []

    def enviar_email(self, assunto, mensagem, anexo=None, cc=None, bcc=None):
        with open(anexo, encoding="utf-8-sig") as f:
            self.enviados.append((assunto, f.read()))


def test_relatorio_envia_uma_vez_por_dia_e_sem_senha(amb, logger, tmp_path):
    amb.colaborador("11111111111", "ANA LIMA")
    amb.usuario("11111111111")["DT_ATUALIZACAO"] = datetime.now().date()
    modo = ModoExecucao(dry_run=False)
    gerador = GerarRelatorioCriacao(amb.banco, logger, modo, caminho_arquivo=str(tmp_path / "novos.csv"))
    email = _EmailFalso()
    relatorio = EnviarRelatorioCriacao(email, gerador, logger, modo, arquivo_controle=str(tmp_path / "enviado.txt"))

    relatorio.executar(agora=datetime(2026, 1, 5, 9, 0))   # antes do horário: não envia
    relatorio.executar(agora=datetime(2026, 1, 5, 15, 0))
    relatorio.executar(agora=datetime(2026, 1, 5, 16, 0))  # já enviado hoje

    assert len(email.enviados) == 1
    conteudo = email.enviados[0][1]
    assert "ana.lima" in conteudo
    assert "SENHA" not in conteudo.upper()
