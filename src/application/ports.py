"""Contratos (portas) que a camada de aplicação usa.

Os casos de uso dependem só destas interfaces. Assim o mesmo robô roda com:
- SQL Server + LDAP + API do AD (produção)
- banco em memória + AD em memória + RH falso (demo e testes)

Os repositórios são separados por caso de uso (Interface Segregation): cada
fluxo enxerga só o que usa. As linhas devolvidas são tuplas na mesma ordem das
colunas das queries/procedures originais.
"""
from collections.abc import Sequence
from typing import Any, Protocol

Linha = tuple[Any, ...]


# ---------------------------------------------------------------- banco (RH x AD)

class BatimentoRepository(Protocol):
    def executar_batimento(self) -> None:
        """Sincroniza o cadastro do RH com a tabela de colaboradores ativos."""
        ...


class CriacaoRepository(Protocol):
    def gerar_fila_criacao(self) -> None:
        """Calcula login, USER_DN e GRUPO_DN dos admitidos e põe na fila (TP_STATUS=0)."""
        ...

    def listar_pendentes_criacao(self) -> list[Linha]:
        """(ID, displayName, nmUsuario, sobreNome, nmLogon, cpf, userDn, grupoDn)"""
        ...

    def atualizar_status_criacao(self, id_tabela, nmLogon, status: str) -> None: ...


class AtualizacaoRepository(Protocol):
    def atualizar_cadastro_e_listar_renomeacoes(self) -> list[Linha]:
        """Atualiza metadados do RH e devolve quem precisa ser renomeado no AD (14 colunas)."""
        ...

    def atualizar_user_dn_renomeado(self, cpf, user_dn_novo) -> None: ...


class MovimentacaoRepository(Protocol):
    def gerar_fila_movimentacao(self) -> None:
        """Limpa a fila e calcula quem mudou de OU ou de grupo."""
        ...

    def listar_movimentacoes_pendentes(self) -> list[Linha]:
        """(cpf, nome, login, userDnAntigo, grupoDnAntigo, userDnNovo, grupoDnNovo)"""
        ...

    def atualizar_fila_movimentacao(self, nuCpf, userDnNovo, grupoDnNovo) -> None: ...

    def atualizar_tabela_usuarios(self, nuCpf, userDnNovo, grupoDnNovo) -> None: ...


class SincroniaRepository(Protocol):
    def listar_ativos_para_sincronia(self, cpfs_ignorados: Sequence[str]) -> list[Linha]:
        """(ID, nome, login, USER_DN, GRUPO_DN, cpf) com TP_STATUS=1"""
        ...


class DesligamentoRepository(Protocol):
    def listar_desligamentos(self) -> list[Linha]:
        """Quem está ativo na tabela mas saiu do RH: (ID, nome, login, USER_DN, GRUPO_DN, cpf)"""
        ...

    def listar_desligados(self) -> list[Linha]:
        """(ID, nome, login, cpf, USER_DN) com TP_STATUS=2"""
        ...

    def atualizar_desativado(self, id_registro, novo_dn, login) -> bool: ...


class CpfDescricaoRepository(Protocol):
    def listar_candidatos_cpf_descricao(self, somente_desligados: bool) -> list[Linha]:
        """(ID, nome, login, cpf)"""
        ...

    def listar_ativos_com_cpf(self) -> list[Linha]:
        """(ID, nome, login, cpf)"""
        ...

    def atualizar_login(self, id_registro, cpf, login_novo) -> bool: ...


class RelatorioRepository(Protocol):
    def listar_criados_hoje(self) -> list[Linha]:
        """(NM_COLABORADOR, NM_LOGIN, NM_FUNCAO, CENTRO_CUSTO)"""
        ...


# ---------------------------------------------------------------- Active Directory

class DiretorioAD(Protocol):
    """Escrita pela API interna do AD; leitura e description via LDAP."""

    # escrita (API)
    def criar(self, nmUsuario, sobreNome, displayName, nmLogon, senha, userDn, grupoDn, cpf) -> dict[str, Any]: ...

    def modificar(self, userDnAntigo, grupoDnAntigo, userDnNovo, grupoDnNovo) -> dict[str, Any]: ...

    def renomear(self, cpf, novoNome, userDnAtual=None) -> dict[str, Any]: ...

    def desativar(self, userDn: str, cpf=None) -> dict[str, Any]: ...

    # leitura (LDAP)
    def buscar_multiplos_por_nome(self, nome) -> list[dict[str, str]]: ...

    def buscar_usuarios_por_nome_exato(self, nome) -> list[dict[str, str]]: ...

    def buscar_user_dn_por_login_exato(self, login) -> str | None: ...

    def buscar_usuario_por_login_exato(self, login) -> dict[str, str] | None: ...

    def buscar_usuarios_por_cpf_descricao(self, cpf) -> list[dict[str, str]]: ...

    def buscar_grupo_atual(self, dn_usuario: str) -> str | None: ...

    def atualizar_descricao_usuario(self, dn_usuario: str, descricao: str) -> bool: ...

    def esta_em_desligados(self, dn_usuario: str) -> bool: ...


# ---------------------------------------------------------------- e-mail

class EnviadorEmail(Protocol):
    def enviar_email(self, assunto, mensagem, anexo=None, cc=None, bcc=None) -> None: ...
