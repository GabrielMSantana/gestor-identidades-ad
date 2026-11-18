from collections.abc import Sequence

from src.application.modo_execucao import ModoExecucao
from src.application.ports import DiretorioAD, SincroniaRepository
from src.application.use_cases.sincronizar_usuarios.sincronizar_usuarios_busca_dn import SincronizarUsuarioBuscaDN
from src.domain.dn import normalizar_dn
from src.domain.excecoes import CpfDuplicadoADException


class SincronizarUsuariosUseCase:
    """Confere se cada ativo está no caminho certo do AD e corrige desvios.

    Pega mudanças feitas à mão no AD (alguém arrastou o usuário para outra OU)
    que a fila de movimentação não enxerga, porque o banco já estava certo.
    """

    def __init__(
        self,
        repo: SincroniaRepository,
        ad_service: DiretorioAD,
        logger,
        modo: ModoExecucao,
        cpfs_ignorados: Sequence[str] = (),
    ):
        self.repo = repo
        self.ad_service = ad_service
        self.logger = logger
        self.modo = modo
        # Contas que não devem ser mexidas pelo robô (diretoria, contas especiais).
        # No original era uma lista fixa na query; agora vem do .env.
        self.cpfs_ignorados = tuple(cpfs_ignorados)
        self.busca = SincronizarUsuarioBuscaDN(ad_service, logger)
        self._resetar_contadores()

    def _resetar_contadores(self):
        self.erros = []
        self.total = 0
        self.ja_corretos = 0
        self.movidos = 0
        self.dry_run_movimentos = 0
        self.replicacao = 0
        self.bloqueados = 0
        self.nao_encontrados = 0
        self.falhas = 0

    def _validar_destino_tabela(self, login, user_dn_banco, grupo_dn_banco):
        if not user_dn_banco:
            return "USER_DN vazio na tabela"

        if not grupo_dn_banco:
            return "GRUPO_DN vazio na tabela"

        user_dn_norm = normalizar_dn(user_dn_banco).strip().lower()
        grupo_dn_norm = normalizar_dn(grupo_dn_banco).strip().lower()

        caminhos_invalidos = (
            "centro_custo invalido",
            "nao possui caminho"
        )

        if any(valor in user_dn_norm for valor in caminhos_invalidos):
            return f"USER_DN invalido na tabela: {user_dn_banco}"

        if any(valor in grupo_dn_norm for valor in caminhos_invalidos):
            return f"GRUPO_DN invalido na tabela: {grupo_dn_banco}"

        if not user_dn_norm.startswith("cn="):
            return f"USER_DN nao parece ser DN de usuario: {user_dn_banco}"

        if not grupo_dn_norm.startswith("cn="):
            return f"GRUPO_DN nao parece ser DN de grupo: {grupo_dn_banco}"

        return None

    def executar(self):
        self.logger.info("==== Iniciando sincronizacao de usuarios ativos ====")
        self._resetar_contadores()

        registros = self.repo.listar_ativos_para_sincronia(self.cpfs_ignorados)
        self.total = len(registros) if registros else 0
        self.logger.info(f"Total de usuarios ativos para sincronizar: {self.total}")

        if not registros:
            self.logger.info("Nenhum usuario ativo encontrado para sincronizar.")
            return

        for row in registros:
            (
                id_registro,
                nome,
                login,
                user_dn_banco,
                grupo_dn_banco,
                cpf
            ) = row

            try:
                # Busca DN atual no AD via LDAP, priorizando CPF na description
                dn_atual_ad = self.busca.buscar_dn(login, nome, cpf)

                if not dn_atual_ad:
                    motivo = "Usuario nao encontrado no AD"
                    self.nao_encontrados += 1
                    self.logger.warning(f"[NAO_ENCONTRADO] ID={id_registro} | login={login} | cpf={cpf}")
                    self.erros.append((cpf, login, motivo))
                    continue

                motivo_destino_invalido = self._validar_destino_tabela(
                    login,
                    user_dn_banco,
                    grupo_dn_banco
                )

                if motivo_destino_invalido:
                    self.bloqueados += 1
                    self.logger.error(
                        f"[BLOQUEADO] ID={id_registro} | login={login} | cpf={cpf} | motivo={motivo_destino_invalido}"
                    )
                    self.erros.append((cpf, login, motivo_destino_invalido))
                    continue

                # Normalização
                dn_atual_norm = normalizar_dn(dn_atual_ad).replace(" ", "").lower()
                dn_banco_norm = normalizar_dn(user_dn_banco).replace(" ", "").lower()

                # SE JÁ ESTÁ NO CAMINHO CORRETO
                if dn_atual_norm == dn_banco_norm:
                    self.ja_corretos += 1
                    continue

                # AD AINDA REPLICANDO
                if dn_banco_norm in dn_atual_norm:
                    self.replicacao += 1
                    self.logger.info(
                        f"[REPLICA] ID={id_registro} | login={login} | cpf={cpf} | aguardando propagacao."
                    )
                    continue

                # Necessario mover
                self.logger.warning(
                    f"[MOVER] ID={id_registro} | login={login} | cpf={cpf} | atual='{dn_atual_ad}' | destino='{user_dn_banco}'"
                )

                # Grupo atual
                grupo_atual = self.ad_service.buscar_grupo_atual(dn_atual_ad)

                if not grupo_atual:
                    motivo = "Nao foi possivel identificar o grupo atual"
                    self.falhas += 1
                    self.logger.error(f"[FALHA] ID={id_registro} | login={login} | cpf={cpf} | motivo={motivo}")
                    self.erros.append((cpf, login, motivo))
                    continue

                grupo_correto = grupo_dn_banco

                if self.modo.dry_run:
                    self.dry_run_movimentos += 1
                    self.logger.info(
                        f"[DRY_RUN] Moveria ID={id_registro} | login={login} | cpf={cpf} | atual='{dn_atual_ad}' | destino='{user_dn_banco}'"
                    )
                    continue

                # Chamada à API
                response = self.ad_service.modificar(
                    userDnAntigo=dn_atual_ad,
                    grupoDnAntigo=grupo_atual,
                    userDnNovo=user_dn_banco,
                    grupoDnNovo=grupo_correto
                )

                resp = str(response).lower()

                if (
                    not response
                    or response.get("status") is False
                    or "erro" in resp
                ):
                    motivo = f"Falha API: {response}"
                    self.falhas += 1
                    self.logger.error(f"[FALHA] ID={id_registro} | login={login} | cpf={cpf} | motivo={motivo}")
                    self.erros.append((cpf, login, motivo))
                    continue


                # Sucesso
                self.movidos += 1
                self.logger.info(f"[SUCESSO] ID={id_registro} | login={login} | cpf={cpf} | movido para o caminho correto.")

            except CpfDuplicadoADException as e:
                motivo = str(e)
                self.bloqueados += 1
                self.logger.error(f"[BLOQUEADO] ID={id_registro} | login={login} | cpf={cpf} | motivo={motivo}")
                self.erros.append((cpf, login, motivo))

            except Exception as e:
                motivo = str(e)
                self.falhas += 1
                self.logger.error(f"[EXCEPTION] ID={id_registro} | login={login} | cpf={cpf} | motivo={motivo}")
                self.erros.append((cpf, login, motivo))

        # RESUMO FINAL
        self.logger.info("==== Resumo sincronizacao de usuarios ====")
        self.logger.info(f"Total avaliados: {self.total}")
        self.logger.info(f"Ja corretos: {self.ja_corretos}")
        self.logger.info(f"Movidos: {self.movidos}")
        self.logger.info(f"Simulados em DRY_RUN: {self.dry_run_movimentos}")
        self.logger.info(f"Aguardando replicacao: {self.replicacao}")
        self.logger.info(f"Nao encontrados: {self.nao_encontrados}")
        self.logger.info(f"Bloqueados: {self.bloqueados}")
        self.logger.info(f"Falhas: {self.falhas}")

        if self.erros:
            self.logger.warning("=== RESUMO DE ERROS NA SINCRONIZACAO ===")
            for cpf, login, motivo in self.erros:
                self.logger.warning(f"CPF: {cpf} | Login: {login} | Motivo: {motivo}")
            self.logger.warning("=== FIM DO RESUMO ===")

            if self.modo.dry_run:
                self.logger.warning("DRY_RUN concluido com erros na sincronizacao.")
        else:
            if self.modo.dry_run:
                self.logger.info("DRY_RUN concluido: sincronizacao simulada sem erros.")
            else:
                self.logger.info("Sincronizacao concluida sem erros.")
