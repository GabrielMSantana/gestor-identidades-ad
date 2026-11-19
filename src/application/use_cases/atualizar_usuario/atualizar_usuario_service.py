from src.application.modo_execucao import ModoExecucao
from src.application.ports import AtualizacaoRepository, DiretorioAD
from src.domain.dn import extrair_cn, normalizar_cpf


class AtualizarUsuarioService:
    """Renomeia no AD quem mudou de nome no RH (ex.: casamento).

    A localização no AD é feita obrigatoriamente pelo CPF na description, para
    não renomear a pessoa errada quando existem homônimos. O login
    (sAMAccountName) não muda; só o nome/CN.
    """

    def __init__(self, repo: AtualizacaoRepository, ad_service: DiretorioAD, logger, modo: ModoExecucao):
        self.repo = repo
        self.ad_service = ad_service
        self.logger = logger
        self.modo = modo
        self._resetar_contadores()

    def _resetar_contadores(self):
        self.total = 0
        self.renomeados = 0
        self.ja_estavam_corretos = 0
        self.dry_run = 0
        self.falhas = 0
        self.erros = []

    def _resposta_sucesso(self, response):
        if not isinstance(response, dict):
            return False

        status_text = str(
            response.get("status")
            or response.get("retorno")
            or response.get("mensagem")
            or ""
        ).lower()

        return (
            "sucesso" in status_text
            or "success" in status_text
            or "ja estava" in status_text
        )

    def _detalhe_resposta(self, response):
        if not isinstance(response, dict):
            return str(response)

        return (
            response.get("erro")
            or response.get("error")
            or response.get("detalhe")
            or response.get("mensagem")
            or response.get("status")
            or str(response)
        )

    def _cpf_valido(self, cpf):
        return len(normalizar_cpf(cpf)) == 11

    def executar(self):
        self.logger.info("==== Iniciando atualizacao de usuarios ====")
        self._resetar_contadores()

        try:
            if self.modo.dry_run and not self.modo.executar_procs:
                self.logger.warning(
                    "[DRY_RUN] Pulando procedure de atualizacao porque DRY_RUN_EXECUTE_PROCS=false."
                )
                usuarios = []
            else:
                if self.modo.dry_run:
                    self.logger.warning(
                        "[DRY_RUN] Executando procedure de atualizacao para preparar dados; renomeacao no AD e updates finais seguem bloqueados."
                    )

                self.logger.info("Executando procedure de atualizacao cadastral...")
                usuarios = self.repo.atualizar_cadastro_e_listar_renomeacoes()

            if not isinstance(usuarios, list):
                usuarios = []

            self.total = len(usuarios)
            self.logger.info(f"Total de usuarios para renomeacao: {self.total}")

            if self.total == 0:
                self.logger.info("Nenhum usuario pendente para renomeacao.")
                return

            for row in usuarios:
                (
                    _id_registro,
                    cpf,
                    login,
                    _nome_antigo,
                    nome_novo,
                    user_dn_atual,
                    user_dn_renomeado,
                    _grupo_dn_atual,
                    _desc_funcao_nova,
                    _id_centro_custo_novo,
                    _centro_custo_novo,
                    _nm_funcao_nova,
                    _afastamento_novo,
                    renomear_ad,
                ) = row

                try:
                    if int(renomear_ad or 0) != 1:
                        continue

                    if not self._cpf_valido(cpf):
                        motivo = "CPF invalido para renomeacao"
                        self.falhas += 1
                        self.erros.append((cpf, login, motivo))
                        self.logger.error(
                            f"[FALHA] cpf={cpf} | login={login} | motivo={motivo}"
                        )
                        continue

                    cn_atual = extrair_cn(user_dn_atual)

                    self.logger.warning(
                        f"[RENOMEAR] cpf={cpf} | login={login} | cn_atual='{cn_atual}' | nome_novo='{nome_novo}'"
                    )

                    if self.modo.dry_run:
                        self.dry_run += 1
                        self.logger.info(
                            f"[DRY_RUN] Renomearia cpf={cpf} | login={login} | dn_atual='{user_dn_atual}' | dn_novo='{user_dn_renomeado}'"
                        )
                        continue

                    response = self.ad_service.renomear(
                        cpf=cpf,
                        novoNome=nome_novo,
                        userDnAtual=user_dn_atual,
                    )

                    if self._resposta_sucesso(response):
                        novo_dn_api = response.get("novo_dn") or user_dn_renomeado

                        self.repo.atualizar_user_dn_renomeado(cpf, novo_dn_api)

                        status_text = str(response.get("status", "")).lower()
                        if "ja estava" in status_text:
                            self.ja_estavam_corretos += 1
                        else:
                            self.renomeados += 1

                        self.logger.info(
                            f"[SUCESSO] cpf={cpf} | login={login} | usuario renomeado/validado no AD."
                        )
                    else:
                        motivo = self._detalhe_resposta(response)
                        self.falhas += 1
                        self.erros.append((cpf, login, motivo))
                        self.logger.error(
                            f"[FALHA] cpf={cpf} | login={login} | motivo={motivo}"
                        )

                except Exception as e_loop:
                    motivo = str(e_loop)
                    self.falhas += 1
                    self.erros.append((cpf, login, motivo))
                    self.logger.error(
                        f"[EXCEPTION] cpf={cpf} | login={login} | motivo={motivo}",
                        exc_info=True,
                    )

            self.logger.info("==== Resumo atualizacao de usuarios ====")
            self.logger.info(f"Total avaliados: {self.total}")
            self.logger.info(f"Renomeados: {self.renomeados}")
            self.logger.info(f"Ja estavam corretos: {self.ja_estavam_corretos}")
            self.logger.info(f"Simulados em DRY_RUN: {self.dry_run}")
            self.logger.info(f"Falhas: {self.falhas}")

            if self.erros:
                self.logger.error("==== Falhas na atualizacao de usuarios ====")
                for cpf_erro, login_erro, motivo in self.erros:
                    self.logger.error(
                        f"CPF={cpf_erro} | Login={login_erro} | Motivo={motivo}"
                    )

        except Exception as e:
            self.logger.error(
                f"Erro geral na atualizacao de usuarios: {e}",
                exc_info=True,
            )
