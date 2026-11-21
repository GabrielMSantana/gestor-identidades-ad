import os
from datetime import date, datetime, time

from src.application.modo_execucao import ModoExecucao
from src.application.ports import EnviadorEmail


class EnviarRelatorioCriacao:
    """Envia o relatorio de criacao uma vez por dia, a partir de um horario."""

    def __init__(
        self,
        email_client: EnviadorEmail,
        gerador_relatorio,
        logger,
        modo: ModoExecucao,
        horario_minimo: time = time(14, 30),
        arquivo_controle="./arquivo/relatorio_enviado.txt",
    ):
        self.email_client = email_client
        self.gerador_relatorio = gerador_relatorio
        self.logger = logger
        self.modo = modo
        self.horario_minimo = horario_minimo
        self.arquivo_controle = arquivo_controle
        self.caminho_arquivo = gerador_relatorio.caminho_arquivo

    def executar(self, agora: datetime | None = None):
        try:
            if self.modo.dry_run:
                self.logger.info("[DRY_RUN] Nao enviaria email de relatorio de criacao.")
                return

            agora = agora or datetime.now()

            # Só executa depois do horário mínimo
            if agora.time() < self.horario_minimo:
                return

            if self.ja_enviado_hoje():
                self.logger.info("Relatório já enviado hoje.")
                return

            status = self.gerador_relatorio.executar()

            if status != "ARQUIVO GERADO":
                return

            # Envio do email
            self.email_client.enviar_email(
                assunto="ALERTA - CRIAÇÃO DE USUÁRIO",
                mensagem="""
                    Prezados,<br><br>
                    Segue relação de novos usuários criados no Active Directory.<br>
                """,
                anexo=self.caminho_arquivo,
            )
            self.marcar_como_enviado()
            self.logger.info("Email de relatorio enviado com sucesso.")

            # Remove o arquivo após envio
            if os.path.exists(self.caminho_arquivo):
                os.remove(self.caminho_arquivo)
                self.logger.info("Arquivo de relatório removido após envio.")

        except Exception as e:
            self.logger.error(
                f"Erro ao enviar email de relatorio: {e}",
                exc_info=True
            )

    def ja_enviado_hoje(self):
        if not os.path.exists(self.arquivo_controle):
            return False

        with open(self.arquivo_controle) as f:
            data = f.read().strip()

        return data == date.today().isoformat()

    def marcar_como_enviado(self):
        with open(self.arquivo_controle, "w") as f:
            f.write(date.today().isoformat())
