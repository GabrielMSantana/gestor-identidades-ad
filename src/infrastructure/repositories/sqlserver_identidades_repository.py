"""Repositório SQL Server de todos os fluxos (implementa os contratos de ports.py).

As queries são as do robô original, com nomes de tabelas e procedures
genéricos e parâmetros (?) no lugar de valores concatenados na string.

O DRY_RUN também é checado aqui (além dos casos de uso): é a última barreira
antes de qualquer UPDATE.
"""
from collections.abc import Sequence

from src.domain.dn import CAMINHOS_INVALIDOS, normalizar_cpf, normalizar_dn
from src.infrastructure.database.sqlserver_repository import ACAO_REALIZADA

T_USUARIOS = "identidade.TB_USUARIO_AD"
T_FILA_MOVIMENTACAO = "identidade.TB_FILA_MOVIMENTACAO_AD"

# Centro de custo que não entra na movimentação automática (ex.: diretoria)
CENTRO_CUSTO_FORA_MOVIMENTACAO = "1000"


def _lista(retorno) -> list[tuple]:
    return retorno if isinstance(retorno, list) else []


class SqlServerIdentidadesRepository:
    def __init__(self, db, logger, dry_run: bool):
        self.db = db
        self.logger = logger
        self.dry_run = dry_run

    # ------------------------------------------------------------ batimento
    def executar_batimento(self) -> None:
        self.db.execute("EXEC identidade.PROC_BATIMENTO_COLABORADORES")

    # ------------------------------------------------------------ criação
    def gerar_fila_criacao(self) -> None:
        self.db.execute("EXEC identidade.PROC_GERAR_FILA_CRIACAO")

    def listar_pendentes_criacao(self):
        query = f"""
            SELECT
                ID,
                displayName = RTRIM(LTRIM(NM_COLABORADOR)),
                nmUsuario = RTRIM(LTRIM(SUBSTRING(NM_COLABORADOR, 1, CHARINDEX(' ', NM_COLABORADOR)))),
                sobreNome = RTRIM(LTRIM(REVERSE(SUBSTRING(REVERSE(NM_COLABORADOR), 1, CHARINDEX(' ', REVERSE(NM_COLABORADOR)))))),
                nmLogon = LOWER(NM_LOGIN),
                cpf = RTRIM(LTRIM(NU_CPF_COLABORADOR)),
                userDn = USER_DN,
                grupoDn = GRUPO_DN
            FROM {T_USUARIOS} WITH(NOLOCK)
            WHERE TP_STATUS = 0
            AND USER_DN NOT IN (?, ?)
            AND GRUPO_DN NOT IN (?, ?)
        """
        return _lista(self.db.execute(query, CAMINHOS_INVALIDOS * 2))

    def atualizar_status_criacao(self, id_tabela, nmLogon, status) -> None:
        """
        Atualiza o banco conforme o status retornado da API.
        """
        if self.dry_run:
            self.logger.info(
                f"[DRY_RUN] Nao atualizaria {T_USUARIOS} para '{nmLogon}' (ID={id_tabela}, status={status})."
            )
            return

        if status in ["sucesso", "existente"]:
            update = f"""
                UPDATE {T_USUARIOS}
                SET TP_STATUS = 1,
                    DT_ATUALIZACAO = GETDATE()
                WHERE ID = ?
            """
            self.db.execute(update, (int(id_tabela),))
            self.logger.info(
                f"Usuario '{nmLogon}' marcado como CRIADO/EXISTENTE (TP_STATUS=1)."
            )
        else:
            self.logger.warning(
                f"Usuario '{nmLogon}' permaneceu com problemas. Nenhuma atualizacao no banco."
            )

    # ------------------------------------------------------------ atualização / renomeação
    def atualizar_cadastro_e_listar_renomeacoes(self):
        return _lista(self.db.execute("EXEC identidade.PROC_ATUALIZAR_CADASTRO"))

    def atualizar_user_dn_renomeado(self, cpf, user_dn_novo) -> None:
        if self.dry_run:
            self.logger.info(
                f"[DRY_RUN] Nao atualizaria USER_DN na {T_USUARIOS} para CPF {cpf}: {user_dn_novo}"
            )
            return

        query = f"""
            UPDATE {T_USUARIOS}
            SET
                USER_DN = ?,
                DT_ATUALIZACAO = GETDATE()
            WHERE NU_CPF_COLABORADOR = ?
        """

        self.db.execute(query, (user_dn_novo, str(cpf)))
        self.logger.info(f"USER_DN atualizado apos renomeacao. cpf={cpf}")

    # ------------------------------------------------------------ movimentação
    def gerar_fila_movimentacao(self) -> None:
        # Limpa a tabela antes de gerar novos registros
        self.db.execute(f"TRUNCATE TABLE {T_FILA_MOVIMENTACAO}")
        self.db.execute("EXEC identidade.PROC_GERAR_FILA_MOVIMENTACAO")

    def listar_movimentacoes_pendentes(self):
        query = f"""
            SELECT DISTINCT
                A.NU_CPF_COLABORADOR,
                B.NM_COLABORADOR,
                B.NM_LOGIN,
                USER_DN_ANTIGO = B.USER_DN,
                GRUPO_DN_ANTIGO = B.GRUPO_DN,
                USER_DN_NOVO = A.USER_DN,
                GRUPO_DN_NOVO = A.GRUPO
            FROM {T_FILA_MOVIMENTACAO} AS A WITH(NOLOCK)
            INNER JOIN {T_USUARIOS} AS B WITH(NOLOCK)
                ON A.NU_CPF_COLABORADOR = B.NU_CPF_COLABORADOR
            WHERE A.TP_STATUS = 0
              AND (A.DT_ATUALIZACAO IS NULL)
              AND A.ID_CENTRO_CUSTO != ?
        """
        return _lista(self.db.execute(query, (CENTRO_CUSTO_FORA_MOVIMENTACAO,)))

    def atualizar_fila_movimentacao(self, nuCpf, userDnNovo, grupoDnNovo) -> None:
        if self.dry_run:
            self.logger.info(
                f"[DRY_RUN] Nao atualizaria {T_FILA_MOVIMENTACAO} para CPF {nuCpf} -> USER_DN='{userDnNovo}', GRUPO='{grupoDnNovo}'."
            )
            return

        query = f"""
            UPDATE {T_FILA_MOVIMENTACAO}
            SET
                TP_STATUS = 1,
                USER_DN = ?,
                GRUPO = ?,
                DT_ATUALIZACAO = GETDATE()
            WHERE NU_CPF_COLABORADOR = ?
        """
        self.db.execute(query, (userDnNovo, grupoDnNovo, str(nuCpf)))
        self.logger.info(f"{T_FILA_MOVIMENTACAO} atualizado para CPF {nuCpf}")

    def atualizar_tabela_usuarios(self, nuCpf, userDnNovo, grupoDnNovo) -> None:
        if self.dry_run:
            self.logger.info(
                f"[DRY_RUN] Nao atualizaria {T_USUARIOS} para CPF {nuCpf} -> USER_DN='{userDnNovo}', GRUPO_DN='{grupoDnNovo}'."
            )
            return

        query = f"""
            UPDATE {T_USUARIOS}
            SET
                USER_DN       = ?,
                GRUPO_DN      = ?,
                DT_ATUALIZACAO = GETDATE()
            WHERE NU_CPF_COLABORADOR = ?
        """
        self.db.execute(query, (userDnNovo, grupoDnNovo, str(nuCpf)))
        self.logger.info(f"{T_USUARIOS} atualizado para CPF {nuCpf}")

    # ------------------------------------------------------------ sincronização
    def listar_ativos_para_sincronia(self, cpfs_ignorados: Sequence[str]):
        cpfs = [normalizar_cpf(c) for c in cpfs_ignorados if normalizar_cpf(c)]
        filtro = ""
        if cpfs:
            filtro = f"AND NU_CPF_COLABORADOR NOT IN ({', '.join('?' for _ in cpfs)})"

        query = f"""
            SELECT
                ID,
                NM_COLABORADOR,
                NM_LOGIN,
                USER_DN,
                GRUPO_DN,
                NU_CPF_COLABORADOR
            FROM {T_USUARIOS} WITH(NOLOCK)
            WHERE TP_STATUS = 1
            {filtro}
        """
        return _lista(self.db.execute(query, tuple(cpfs)))

    # ------------------------------------------------------------ desligamento
    def listar_desligamentos(self):
        return _lista(self.db.execute("EXEC identidade.PROC_LISTAR_DESLIGAMENTOS"))

    def listar_desligados(self):
        query = f"""
            SELECT
                ID,
                NM_COLABORADOR,
                NM_LOGIN,
                NU_CPF_COLABORADOR,
                USER_DN
            FROM {T_USUARIOS} WITH(NOLOCK)
            WHERE TP_STATUS = 2
            ORDER BY NM_COLABORADOR;
        """
        return _lista(self.db.execute(query))

    def atualizar_desativado(self, id_registro, novo_dn, login) -> bool:
        novo_dn = normalizar_dn(novo_dn)

        if self.dry_run:
            self.logger.info(
                f"[DRY_RUN] Nao atualizaria {T_USUARIOS} para '{login}' (ID={id_registro}) como TP_STATUS=2, DN='{novo_dn}'."
            )
            return True

        query = f"""
            UPDATE {T_USUARIOS}
            SET TP_STATUS = 2,
                USER_DN = ?,
                DT_ATUALIZACAO = GETDATE()
            WHERE ID = ?
        """

        retorno = self.db.execute(query, (novo_dn, int(id_registro)))

        if retorno != ACAO_REALIZADA:
            self.logger.error(
                f"[ERRO] Falha ao atualizar banco para {login} -> TP_STATUS=2 | DN={novo_dn}"
            )
            return False

        self.logger.info(
            f"[OK] Banco atualizado para {login} -> TP_STATUS=2 | DN={novo_dn}"
        )
        return True

    # ------------------------------------------------------------ CPF na description
    def listar_candidatos_cpf_descricao(self, somente_desligados: bool):
        query = f"""
            SELECT
                ID,
                NM_COLABORADOR = RTRIM(LTRIM(NM_COLABORADOR)),
                NM_LOGIN = LOWER(RTRIM(LTRIM(NM_LOGIN))),
                NU_CPF_COLABORADOR = RTRIM(LTRIM(NU_CPF_COLABORADOR))
            FROM {T_USUARIOS} WITH(NOLOCK)
            WHERE TP_STATUS = ?
            AND NU_CPF_COLABORADOR IS NOT NULL
            AND NM_LOGIN IS NOT NULL
            ORDER BY NM_COLABORADOR
        """
        return _lista(self.db.execute(query, (2 if somente_desligados else 1,)))

    def listar_ativos_com_cpf(self):
        query = f"""
            SELECT
                ID,
                NM_COLABORADOR = RTRIM(LTRIM(NM_COLABORADOR)),
                NM_LOGIN = RTRIM(LTRIM(NM_LOGIN)),
                NU_CPF_COLABORADOR = RTRIM(LTRIM(NU_CPF_COLABORADOR))
            FROM {T_USUARIOS} WITH(NOLOCK)
            WHERE TP_STATUS = 1
              AND NU_CPF_COLABORADOR IS NOT NULL
            ORDER BY NM_COLABORADOR
        """
        return _lista(self.db.execute(query))

    def atualizar_login(self, id_registro, cpf, login_novo) -> bool:
        if self.dry_run:
            self.logger.warning(
                f"[DRY_RUN] Atualizaria NM_LOGIN na tabela ID={id_registro}, CPF={cpf} para '{login_novo}'."
            )
            return True

        query = f"""
            UPDATE {T_USUARIOS}
            SET NM_LOGIN = ?,
                DT_ATUALIZACAO = GETDATE()
            WHERE ID = ?
              AND NU_CPF_COLABORADOR = ?
        """
        retorno = self.db.execute(query, (login_novo, int(id_registro), str(cpf)))
        return retorno == ACAO_REALIZADA

    # ------------------------------------------------------------ relatório
    def listar_criados_hoje(self):
        query = f"""
            SELECT
                NM_COLABORADOR = RTRIM(LTRIM(NM_COLABORADOR)),
                NM_LOGIN = LOWER(NM_LOGIN),
                NM_FUNCAO,
                CENTRO_CUSTO
            FROM {T_USUARIOS} WITH(NOLOCK)
            WHERE CAST(DT_ATUALIZACAO AS DATE) = CAST(GETDATE() AS DATE)
                  AND TP_STATUS = 1
        """
        return _lista(self.db.execute(query))
