from src.application.modo_execucao import ModoExecucao
from src.application.ports import DiretorioAD, MovimentacaoRepository
from src.application.use_cases.modificar_usuario.modificar_usuario_interpretador import ModificarUsuarioInterpretador
from src.application.use_cases.modificar_usuario.modificar_usuario_mapper import ModificarUsuarioMapper
from src.application.use_cases.sincronizar_usuarios.sincronizar_usuarios_busca_dn import SincronizarUsuarioBuscaDN
from src.domain.excecoes import CpfDuplicadoADException


class ModificarUsuarioService:
    """Move no AD quem mudou de OU ou de grupo (troca de centro de custo/função)."""

    def __init__(self, repo: MovimentacaoRepository, ad_service: DiretorioAD, logger, modo: ModoExecucao):
        self.repo = repo
        self.ad_service = ad_service
        self.logger = logger
        self.modo = modo
        self.mapper = ModificarUsuarioMapper(logger)
        self.interp = ModificarUsuarioInterpretador(logger)
        self.busca = SincronizarUsuarioBuscaDN(ad_service, logger)
        self._resetar_contadores()

    def _resetar_contadores(self):
        self.total = 0
        self.ja_no_destino = 0
        self.movidos = 0
        self.dry_run_movimentos = 0
        self.bloqueados = 0
        self.falhas = 0
        self.erros = []

    def _dn_valido_para_movimentar(self, dn, tipo):
        if not dn:
            return f"{tipo} vazio"

        dn_norm = str(dn).strip().lower()
        caminhos_invalidos = (
            "centro_custo invalido",
            "nao possui caminho",
        )

        if any(valor in dn_norm for valor in caminhos_invalidos):
            return f"{tipo} invalido: {dn}"

        if not dn_norm.startswith("cn="):
            return f"{tipo} nao parece ser DN valido: {dn}"

        return None

    def usuario_ja_na_pasta_destino(self, nuCpf, nome, login, userDnNovo, grupoDnNovo):
        """
        Verifica no AD se o usuario ja esta de fato no DN e grupo de destino.
        """
        try:
            dn_atual_ad = self.busca.buscar_dn(login, nome, nuCpf)

            if not dn_atual_ad:
                return False

            dn_atual_norm = self.mapper.normaliza_para_comparar(dn_atual_ad)
            dn_destino_norm = self.mapper.normaliza_para_comparar(userDnNovo)

            if dn_atual_norm != dn_destino_norm:
                return False

            grupo_atual_ad = self.ad_service.buscar_grupo_atual(dn_atual_ad)

            if not grupo_atual_ad:
                return False

            grupo_atual_norm = self.mapper.normaliza_para_comparar(grupo_atual_ad)
            grupo_destino_norm = self.mapper.normaliza_para_comparar(grupoDnNovo)

            if grupo_atual_norm == grupo_destino_norm:
                self.logger.debug(
                    f"CPF {nuCpf} ja esta no DN e grupo de destino. AD: {dn_atual_ad}"
                )
                return True

            return False

        except CpfDuplicadoADException:
            raise
        except Exception as e:
            self.logger.error(
                f"Erro ao verificar DN/grupo de destino para CPF {nuCpf}: {e}",
                exc_info=True
            )
            return False

    def executar(self):
        self.logger.info("==== Iniciando modificacao de usuarios ====")
        self._resetar_contadores()

        try:
            if self.modo.dry_run and not self.modo.executar_procs:
                self.logger.warning("[DRY_RUN] Pulando geracao da fila de movimentacao porque DRY_RUN_EXECUTE_PROCS=false.")
            else:
                if self.modo.dry_run:
                    self.logger.warning("[DRY_RUN] Gerando fila de movimentacao; movimentacao no AD e updates finais seguem bloqueados.")

                # 1) Limpa a fila e executa a PROC que calcula os destinos
                self.logger.info("Gerando fila de movimentacao (procedure)...")
                self.repo.gerar_fila_movimentacao()

            # 2) Busca pendentes
            modificacoes = self.repo.listar_movimentacoes_pendentes()
            total = len(modificacoes)
            self.total = total
            self.logger.info(f"Total de usuarios para movimentacao: {total}")

            if total == 0:
                self.logger.info("Nenhum usuario pendente para movimentacao.")
                return

            # 3) Loop de movimentação
            for row in modificacoes:
                (
                    nuCpf,
                    nome,
                    login,
                    userDnAntigo,
                    grupoDnAntigo,
                    userDnNovo,
                    grupoDnNovo
                ) = row

                try:
                    # Normalizar DNs
                    userDnAntigo, userDnNovo, grupoDnAntigo, grupoDnNovo = \
                        self.mapper.normalizar_dns(userDnAntigo, userDnNovo, grupoDnAntigo, grupoDnNovo)

                    motivo_destino_invalido = (
                        self._dn_valido_para_movimentar(userDnNovo, "USER_DN_NOVO")
                        or self._dn_valido_para_movimentar(grupoDnNovo, "GRUPO_DN_NOVO")
                    )

                    if motivo_destino_invalido:
                        self.bloqueados += 1
                        self.logger.error(
                            f"[BLOQUEADO] cpf={nuCpf} | login={login} | motivo={motivo_destino_invalido}"
                        )
                        self.erros.append((nuCpf, login, motivo_destino_invalido))
                        continue

                    # Se ja está no destino, apenas atualiza o banco
                    if self.usuario_ja_na_pasta_destino(nuCpf, nome, login, userDnNovo, grupoDnNovo):

                        self.repo.atualizar_fila_movimentacao(nuCpf, userDnNovo, grupoDnNovo)

                        self.repo.atualizar_tabela_usuarios(nuCpf, userDnNovo, grupoDnNovo)

                        self.ja_no_destino += 1
                        self.logger.info(
                            f"[ATUALIZADO] cpf={nuCpf} | login={login} | AD ja estava no destino; banco atualizado."
                        )
                        continue

                    self.logger.warning(
                        f"[MOVER] cpf={nuCpf} | login={login} | atual='{userDnAntigo}' | destino='{userDnNovo}'"
                    )

                    if self.modo.dry_run:
                        self.dry_run_movimentos += 1
                        self.logger.info(
                            f"[DRY_RUN] Moveria cpf={nuCpf} | login={login} | grupo_atual='{grupoDnAntigo}' | grupo_destino='{grupoDnNovo}'"
                        )
                        continue

                    # Chamada API AD
                    resp = self.ad_service.modificar(
                        userDnAntigo, grupoDnAntigo,
                        userDnNovo, grupoDnNovo
                    )

                    # Interpretar resposta
                    status, detalhe = self.interp.interpretar(resp)

                    if status == "sucesso":
                        # Atualiza tabelas
                        self.repo.atualizar_fila_movimentacao(nuCpf, userDnNovo, grupoDnNovo)
                        self.repo.atualizar_tabela_usuarios(nuCpf, userDnNovo, grupoDnNovo)
                        self.movidos += 1
                        self.logger.info(
                            f"[SUCESSO] cpf={nuCpf} | login={login} | movimentado e tabelas atualizadas."
                        )
                    else:
                        self.falhas += 1
                        motivo = f"Falha API: {detalhe}"
                        self.logger.error(
                            f"[FALHA] cpf={nuCpf} | login={login} | motivo={motivo}"
                        )
                        self.erros.append((nuCpf, login, motivo))

                except CpfDuplicadoADException as e_dup:
                    self.bloqueados += 1
                    motivo = str(e_dup)
                    self.logger.error(
                        f"[BLOQUEADO] cpf={nuCpf} | login={login} | motivo={motivo}"
                    )
                    self.erros.append((nuCpf, login, motivo))
                except Exception as e_loop:
                    self.falhas += 1
                    motivo = str(e_loop)
                    self.logger.error(
                        f"[EXCEPTION] cpf={nuCpf} | login={login} | motivo={motivo}",
                        exc_info=True
                    )
                    self.erros.append((nuCpf, login, motivo))

            self.logger.info("==== Resumo modificacao de usuarios ====")
            self.logger.info(f"Total avaliados: {self.total}")
            self.logger.info(f"Movidos: {self.movidos}")
            self.logger.info(f"Ja estavam no destino: {self.ja_no_destino}")
            self.logger.info(f"Simulados em DRY_RUN: {self.dry_run_movimentos}")
            self.logger.info(f"Bloqueados: {self.bloqueados}")
            self.logger.info(f"Falhas: {self.falhas}")

            if self.erros:
                self.logger.error("==== Falhas/bloqueios na movimentacao ====")
                for cpf, login_erro, motivo in self.erros:
                    self.logger.error(f"CPF={cpf} | Login={login_erro} | Motivo={motivo}")
            else:
                self.logger.info("Todos os usuarios foram movimentados com sucesso.")

        except Exception as e:
            self.logger.error(f"Erro geral na modificacao de usuarios: {e}", exc_info=True)
