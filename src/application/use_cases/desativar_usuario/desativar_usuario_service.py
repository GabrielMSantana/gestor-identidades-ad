from src.application.modo_execucao import ModoExecucao
from src.application.ports import DesligamentoRepository, DiretorioAD
from src.application.use_cases.desativar_usuario.desativar_usuario_interpretador import DesativarUsuarioInterpretador
from src.application.use_cases.sincronizar_usuarios.sincronizar_usuarios_busca_dn import SincronizarUsuarioBuscaDN
from src.domain.dn import normalizar_dn
from src.domain.excecoes import CpfDuplicadoADException


class DesativarUsuarioService:
    """Desativa e move para a OU de desligados quem saiu do RH."""

    def __init__(self, repo: DesligamentoRepository, ad_service: DiretorioAD, logger, modo: ModoExecucao):
        self.repo = repo
        self.ad_service = ad_service
        self.logger = logger
        self.modo = modo

        self.interp = DesativarUsuarioInterpretador(logger)
        self.busca = SincronizarUsuarioBuscaDN(ad_service, logger)
        self._resetar_contadores()

    def _resetar_contadores(self):
        self.total = 0
        self.desativados = 0
        self.ja_em_desligados = 0
        self.dry_run = 0
        self.erros = []

    def _dn_valido_para_desativar(self, dn):
        if not dn:
            return False

        dn_norm = str(dn).strip().lower()

        caminhos_invalidos = (
            "centro_custo invalido",
            "nao possui caminho",
        )

        if any(valor in dn_norm for valor in caminhos_invalidos):
            return False

        return dn_norm.startswith("cn=")

    def executar(self):
        self.logger.info("==== Iniciando desativacao de usuarios desligados ====")
        self._resetar_contadores()

        try:
            usuarios = self.repo.listar_desligamentos()
            total = len(usuarios)
            self.total = total
            self.logger.info(f"Usuarios encontrados para desativacao: {total}")

            if total == 0:
                return

            erros = self.erros

            # LOOP PRINCIPAL
            for row in usuarios:
                id_registro, nome, login, user_dn_tabela, _grupo_dn, cpf = row
                user_dn_tabela = normalizar_dn(user_dn_tabela)

                try:
                    dn_real_ad = self.busca.buscar_dn(login, nome, cpf)

                    if dn_real_ad:
                        dn_real_ad = normalizar_dn(dn_real_ad)

                    if dn_real_ad and self.ad_service.esta_em_desligados(dn_real_ad):
                        if self.modo.dry_run:
                            self.dry_run += 1
                            self.logger.info(
                                f"[DRY_RUN] '{login}' ja esta em Desligados. "
                                f"Atualizaria banco para TP_STATUS=2 com DN='{dn_real_ad}'."
                            )
                        else:
                            self.logger.info(
                                f"'{login}' ja esta em Desligados. Atualizando banco para TP_STATUS=2."
                            )
                            atualizou = self.repo.atualizar_desativado(id_registro, dn_real_ad, login)
                            if atualizou:
                                self.ja_em_desligados += 1
                            else:
                                motivo = "Falha ao atualizar banco para TP_STATUS=2"
                                erros.append((cpf, login, motivo))
                        continue

                    dn_para_desativar = dn_real_ad or user_dn_tabela

                    if not self._dn_valido_para_desativar(dn_para_desativar):
                        motivo = f"DN invalido para desativacao: {dn_para_desativar}"
                        self.logger.error(
                            f"[BLOQUEADO] {login} | CPF={cpf} | {motivo}"
                        )
                        erros.append((cpf, login, motivo))
                        continue

                    if not dn_real_ad:
                        self.logger.warning(
                            f"[FALLBACK_TABELA] Usuario nao localizado no AD por CPF/nome/login. "
                            f"Usando USER_DN da tabela para tentativa de desativacao. "
                            f"login={login} | CPF={cpf} | USER_DN={user_dn_tabela}"
                        )

                    if self.modo.dry_run:
                        self.dry_run += 1
                        self.logger.info(
                            f"[DRY_RUN] Desativaria '{login}' (CPF={cpf}) usando DN='{dn_para_desativar}' "
                            f"e depois marcaria TP_STATUS=2."
                        )
                        continue

                    response = self.ad_service.desativar(dn_para_desativar, cpf)
                    status, detalhe = self.interp.interpretar(response)

                    if status == "sucesso":
                        novo_dn = response.get("novo_dn", dn_para_desativar)
                        atualizou = self.repo.atualizar_desativado(id_registro, novo_dn, login)
                        if atualizou:
                            self.desativados += 1
                        else:
                            motivo = "Usuario desativado no AD, mas falhou ao atualizar banco"
                            erros.append((cpf, login, motivo))
                        continue

                    motivo = f"Falha API desativar: {detalhe}"
                    self.logger.warning(
                        f"[FALHA] Nao foi possivel desativar {login} | CPF={cpf} | {motivo}"
                    )
                    erros.append((cpf, login, motivo))

                except CpfDuplicadoADException as e:
                    motivo = str(e)
                    self.logger.error(
                        f"[BLOQUEADO] CPF duplicado no AD para desligamento. "
                        f"login={login} | CPF={cpf} | motivo={motivo}"
                    )
                    erros.append((cpf, login, motivo))

                except Exception as e_loop:
                    motivo = str(e_loop)
                    self.logger.error(
                        f"Erro inesperado ao desativar {login} | CPF={cpf}: {motivo}",
                        exc_info=True,
                    )
                    erros.append((cpf, login, motivo))

            if erros:
                self.logger.error("==== Falhas no desligamento ====")
                for cpf, login, motivo in erros:
                    self.logger.error(f"CPF={cpf} | Login={login} | Motivo={motivo}")
            else:
                self.logger.info("Todos os usuarios foram desativados com sucesso.")

        except Exception as e:
            self.logger.error(f"Erro geral na desativacao: {e}", exc_info=True)
