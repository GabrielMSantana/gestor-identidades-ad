"""Orquestra o ciclo diário do robô (antigo UserService.run)."""
from dataclasses import dataclass

from src.application.modo_execucao import ModoExecucao
from src.application.ports import BatimentoRepository
from src.application.use_cases.atualizar_usuario.atualizar_usuario_service import AtualizarUsuarioService
from src.application.use_cases.criar_usuario.criar_usuario_service import CriarUsuarioService
from src.application.use_cases.desativar_usuario.desativar_usuario_service import DesativarUsuarioService
from src.application.use_cases.modificar_usuario.modificar_usuario_service import ModificarUsuarioService
from src.application.use_cases.relatorios.enviar_relatorio_criacao import EnviarRelatorioCriacao
from src.application.use_cases.sincronizar_usuarios.sincronizar_usuarios import SincronizarUsuariosUseCase


@dataclass
class CicloDiario:
    batimento: BatimentoRepository
    criar: CriarUsuarioService
    atualizar: AtualizarUsuarioService
    modificar: ModificarUsuarioService
    sincronizar: SincronizarUsuariosUseCase
    desativar: DesativarUsuarioService
    logger: object
    modo: ModoExecucao
    relatorio: EnviarRelatorioCriacao | None = None

    def run(self):
        self.logger.info("Iniciando execução do robô AD...")

        if self.modo.dry_run:
            self.logger.warning("DRY_RUN ativo: nenhuma chamada de API AD ou update final sera executado.")

        try:
            if self.modo.dry_run and not self.modo.executar_procs:
                self.logger.warning("[DRY_RUN] Pulando batimento de colaboradores porque DRY_RUN_EXECUTE_PROCS=false.")
            else:
                # Executa a proc de Batimento (RH -> colaboradores ativos)
                self.logger.info("Executando batimento de colaboradores...")
                if self.modo.dry_run:
                    self.logger.warning("[DRY_RUN] Executando batimento para preparar dados; acoes de AD/updates finais seguem bloqueadas.")
                self.batimento.executar_batimento()

            # Fluxos organizados (a ordem importa: renomear antes de mover)
            self.criar.executar()
            self.atualizar.executar()
            self.modificar.executar()
            self.sincronizar.executar()
            self.desativar.executar()

            if self.relatorio:
                self.relatorio.executar()

            self.logger.info("Execução concluída com sucesso.")

        except Exception as e:
            self.logger.error(f"Erro durante execução: {e}", exc_info=True)
