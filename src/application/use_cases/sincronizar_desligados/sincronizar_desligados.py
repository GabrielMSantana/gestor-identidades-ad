from src.application.modo_execucao import ModoExecucao
from src.application.ports import DesligamentoRepository, DiretorioAD
from src.application.use_cases.desativar_usuario.desativar_usuario_interpretador import (
    DesativarUsuarioInterpretador,
)
from src.application.use_cases.sincronizar_usuarios.sincronizar_usuarios_busca_dn import (
    SincronizarUsuarioBuscaDN,
)
from src.domain.dn import mesmo_dn, normalizar_dn
from src.domain.excecoes import CpfDuplicadoADException


class SincronizarDesligadosUseCase:
    def __init__(
        self,
        repo: DesligamentoRepository,
        ad_service: DiretorioAD,
        logger,
        modo: ModoExecucao,
        pasta_desligados: str,
    ):
        self.repo = repo
        self.ad_service = ad_service
        self.logger = logger
        self.modo = modo
        self.pasta_desligados = pasta_desligados

        self.busca = SincronizarUsuarioBuscaDN(ad_service, logger)
        self.interp = DesativarUsuarioInterpretador(logger)

        self._resetar_contadores()

    def _resetar_contadores(self):
        self.total = 0
        self.erros = []
        self.ja_corretos = 0
        self.corrigidos_banco = 0
        self.movidos_desligados = 0
        self.nao_encontrados = 0
        self.simulados = 0

    def executar(self):
        self._resetar_contadores()
        self.logger.warning("==== Iniciando rotina manual: sincronizar usuarios desligados no AD ====")

        if not self.pasta_desligados:
            self.logger.error("AD_PASTA_DESLIGADOS nao configurado no .env. Rotina bloqueada.")
            return

        registros = self._buscar_usuarios_desligados()
        self.total = len(registros) if registros else 0

        if not registros:
            self.logger.info("Nenhum usuario com TP_STATUS=2 encontrado para sincronizar.")
            self._log_resumo()
            return

        self.logger.info(f"Total de usuarios desligados para validar: {self.total}")

        for row in registros:
            id_registro, nome, login, cpf, user_dn_banco = row

            try:
                dn_real_ad = self.busca.buscar_dn(login, nome, cpf)

                if not dn_real_ad:
                    motivo = "Usuario nao encontrado no AD"
                    self.nao_encontrados += 1
                    self.logger.warning(f"[NAO_ENCONTRADO] login={login} | cpf={cpf}")
                    self.erros.append((cpf, login, motivo))
                    continue

                dn_real_ad = normalizar_dn(dn_real_ad)
                user_dn_banco = normalizar_dn(user_dn_banco)

                if self.ad_service.esta_em_desligados(dn_real_ad):
                    self._tratar_usuario_ja_em_desligados(
                        id_registro=id_registro,
                        login=login,
                        cpf=cpf,
                        dn_real_ad=dn_real_ad,
                        user_dn_banco=user_dn_banco,
                    )
                    continue

                self._mover_usuario_para_desligados(
                    id_registro=id_registro,
                    login=login,
                    cpf=cpf,
                    dn_real_ad=dn_real_ad,
                )

            except CpfDuplicadoADException as e:
                motivo = str(e)
                self.logger.error(
                    f"[BLOQUEADO] CPF duplicado no AD: login={login} | cpf={cpf} | motivo={motivo}"
                )
                self.erros.append((cpf, login, motivo))

            except Exception as e:
                motivo = str(e)
                self.logger.error(
                    f"[EXCEPTION] Erro ao sincronizar desligado: login={login} | cpf={cpf} | motivo={motivo}",
                    exc_info=True,
                )
                self.erros.append((cpf, login, motivo))

        self._log_resumo()

    def _buscar_usuarios_desligados(self):
        return self.repo.listar_desligados()

    def _tratar_usuario_ja_em_desligados(
        self,
        id_registro,
        login,
        cpf,
        dn_real_ad,
        user_dn_banco,
    ):
        if self._mesmo_dn(dn_real_ad, user_dn_banco):
            self.ja_corretos += 1
            return

        self.logger.warning(
            f"[CORRIGIR_BANCO] Usuario ja esta em Desligados no AD, mas USER_DN da tabela esta diferente. "
            f"login={login} | cpf={cpf} | banco='{user_dn_banco}' | ad='{dn_real_ad}'"
        )

        self.repo.atualizar_desativado(id_registro, dn_real_ad, login)
        self.corrigidos_banco += 1

    def _mover_usuario_para_desligados(self, id_registro, login, cpf, dn_real_ad):
        self.logger.warning(
            f"[MOVER_DESLIGADOS] Usuario TP_STATUS=2 esta fora de Desligados no AD. "
            f"login={login} | cpf={cpf} | dn_atual='{dn_real_ad}'"
        )

        if self.modo.dry_run:
            self.logger.info(
                f"[DRY_RUN] Desativaria/moveria para Desligados: login={login} | cpf={cpf} | dn='{dn_real_ad}'"
            )
            self.simulados += 1
            return

        response = self.ad_service.desativar(dn_real_ad, cpf)
        status, detalhe = self.interp.interpretar(response)

        if status != "sucesso":
            motivo = f"Falha API desativar: {detalhe}"
            self.logger.error(
                f"[FALHA] Nao foi possivel mover para Desligados: login={login} | cpf={cpf} | motivo={motivo}"
            )
            self.erros.append((cpf, login, motivo))
            return

        novo_dn = response.get("novo_dn", dn_real_ad)
        self.repo.atualizar_desativado(id_registro, novo_dn, login)
        self.movidos_desligados += 1

        self.logger.info(
            f"[SUCESSO] Usuario movido para Desligados: login={login} | cpf={cpf} | novo_dn='{novo_dn}'"
        )

    def _mesmo_dn(self, dn_a, dn_b):
        return mesmo_dn(dn_a, dn_b)

    def _log_resumo(self):
        self.logger.warning("==== Resumo rotina manual: sincronizar usuarios desligados no AD ====")
        self.logger.warning(f"Total avaliados: {self.total}")
        self.logger.warning(f"Ja corretos: {self.ja_corretos}")
        self.logger.warning(f"Corrigidos somente no banco: {self.corrigidos_banco}")
        self.logger.warning(f"Movidos para Desligados: {self.movidos_desligados}")
        self.logger.warning(f"Nao encontrados no AD: {self.nao_encontrados}")
        self.logger.warning(f"Simulados em DRY_RUN: {self.simulados}")
        self.logger.warning(f"Erros/bloqueados: {len(self.erros)}")

        if self.erros:
            self.logger.warning("==== Detalhes dos erros/bloqueios ====")
            for cpf, login, motivo in self.erros:
                self.logger.warning(f"CPF={cpf} | Login={login} | Motivo={motivo}")

        self.logger.warning("==== Fim rotina manual: sincronizar usuarios desligados no AD ====")
