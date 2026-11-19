from collections.abc import Callable

from src.application.modo_execucao import ModoExecucao
from src.application.ports import CriacaoRepository, DiretorioAD
from src.application.use_cases.criar_usuario.criar_usuario_interpretador import CriarUsuarioInterpretador
from src.application.use_cases.criar_usuario.criar_usuario_mapper import CriarUsuarioMapper
from src.application.use_cases.criar_usuario.criar_usuario_validator import CriarUsuarioValidator
from src.domain.senha import gerar_senha_temporaria


class CriarUsuarioService:
    def __init__(
        self,
        repo: CriacaoRepository,
        ad_service: DiretorioAD,
        logger,
        modo: ModoExecucao,
        gerador_senha: Callable[[], str] = gerar_senha_temporaria,
    ):
        self.repo = repo
        self.ad_service = ad_service
        self.logger = logger
        self.modo = modo
        self.gerador_senha = gerador_senha

        # Auxiliares organizados
        self.validator = CriarUsuarioValidator(logger)
        self.mapper = CriarUsuarioMapper(logger)
        self.interp = CriarUsuarioInterpretador(logger)

    def executar(self):
        self.logger.info("==== Iniciando criacao de novos usuarios ====")

        try:
            if self.modo.dry_run and not self.modo.executar_procs:
                self.logger.warning("[DRY_RUN] Pulando geracao da fila de criacao porque DRY_RUN_EXECUTE_PROCS=false.")
            else:
                # 1) Executa a PROC
                self.logger.info("Gerando fila de criacao (procedure)...")
                if self.modo.dry_run:
                    self.logger.warning("[DRY_RUN] Executando procedure para alimentar fila; criacao no AD e update de status seguem bloqueados.")
                self.repo.gerar_fila_criacao()

            # 2) Busca usuários pendentes
            usuarios = self.repo.listar_pendentes_criacao()
            total = len(usuarios) if usuarios else 0
            self.logger.info(f"Total de usuarios a criar: {total}")

            if not usuarios:
                self.logger.info("Nenhum usuario para criar.")
                return False

            erros = []

            # 3) Loop principal
            for row in usuarios:
                (
                    id_tabela,
                    displayName,
                    nmUsuario,
                    sobreNome,
                    nmLogon,
                    cpf,
                    userDn,
                    grupoDn,
                ) = row

                try:
                    self.logger.info(
                        f"Iniciando criacao no AD para login '{nmLogon}' (ID={id_tabela})"
                    )

                    cpf = self.validator.validar_dados_criacao(
                        id_tabela,
                        nmLogon,
                        cpf,
                        userDn,
                        grupoDn
                    )

                    # Normalizar DN
                    userDn, grupoDn = self.mapper.normalizar_dns(userDn, grupoDn)

                    if self.modo.dry_run:
                        self.logger.info(
                            f"[DRY_RUN] Criaria usuario '{nmLogon}' (ID={id_tabela}, CPF={cpf}) em USER_DN='{userDn}' e GRUPO_DN='{grupoDn}'."
                        )
                        continue

                    # Montar payload da API AD (senha temporária aleatória)
                    payload = self.mapper.montar_payload(
                        nmUsuario, sobreNome, displayName, nmLogon, self.gerador_senha(), userDn, grupoDn, cpf
                    )

                    # Enviar para AD API
                    resp = self.ad_service.criar(**payload)

                    # Interpretar retorno
                    status, detalhe = self.interp.interpretar(resp)

                    # Atualizar banco conforme retorno
                    self.repo.atualizar_status_criacao(id_tabela, nmLogon, status)

                    if status == "erro":
                        erros.append(nmLogon)
                        self.logger.warning(
                            f"Falha ao criar usuario '{nmLogon}'. Detalhe: {detalhe}"
                        )

                except Exception as e_loop:
                    erros.append(nmLogon)
                    self.logger.error(
                        f"Erro inesperado ao processar '{nmLogon}': {e_loop}",
                        exc_info=True
                    )

            if erros:
                self.logger.error(f"Erros ao criar: {erros}")
            else:
                self.logger.info("Todos os usuarios criados ou ja existentes.")

            return True

        except Exception as e:
            self.logger.error(f"Erro geral na criacao de usuarios: {e}", exc_info=True)
            return False
