import csv
import os

from src.application.modo_execucao import ModoExecucao
from src.application.ports import RelatorioRepository


class GerarRelatorioCriacao:
    """Gera o CSV com os usuarios criados no dia.

    A senha nao vai no relatorio: no original ela era derivada do nome e
    reconstruida aqui; nesta versao a senha temporaria e aleatoria.
    """

    def __init__(self, repo: RelatorioRepository, logger, modo: ModoExecucao, caminho_arquivo="./arquivo/novosUsuarios.csv"):
        self.repo = repo
        self.logger = logger
        self.modo = modo
        self.caminho_arquivo = caminho_arquivo

    def executar(self):
        self.logger.info("Gerando relatorio de criacao de usuarios.")

        if self.modo.dry_run:
            self.logger.info("[DRY_RUN] Nao geraria arquivo CSV de relatorio de criacao.")
            return "DRY_RUN"

        try:
            retorno = self.repo.listar_criados_hoje()

            if not retorno:
                self.logger.info("Nenhum novo usuario encontrado hoje. Nenhum e-mail será enviado.")
                return "SEM DADOS"

            caminho_arquivo = self.caminho_arquivo

            # Se já existe, remove
            if os.path.exists(caminho_arquivo):
                os.remove(caminho_arquivo)
                self.logger.info("Arquivo existente removido para reescrita limpa.")

            # Criar novo CSV
            with open(caminho_arquivo, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["NM_COLABORADOR", "NM_LOGIN", "NM_FUNCAO", "CENTRO_CUSTO"])
                writer.writerows(retorno)

            self.logger.info("Relatorio de novos usuarios gerado com sucesso.")
            return "ARQUIVO GERADO"

        except Exception as e:
            self.logger.error(f"Erro ao gerar relatorio: {e}", exc_info=True)
            return "ERRO"
