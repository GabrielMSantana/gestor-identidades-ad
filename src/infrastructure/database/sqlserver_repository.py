import logging

from src.config.settings import ConfigBanco

logger = logging.getLogger("gestor_identidades_ad")

ACAO_REALIZADA = "ACAO REALIZADA COM SUCESSO"


class SQLServerRepository:
    """Conexão com o SQL Server com reconexão automática.

    execute() devolve as linhas quando a query tem resultado e a constante
    ACAO_REALIZADA quando é um comando sem retorno (UPDATE, EXEC sem SELECT).
    """

    def __init__(self, server, database, user, password, driver="ODBC Driver 17 for SQL Server"):
        self.server = server
        self.database = database
        self.user = user
        self.password = password
        self.driver = driver
        self.conn = None
        self.cursor = None
        self._conectar()

    @classmethod
    def a_partir_da_config(cls, config: ConfigBanco, banco: str | None = None):
        return cls(config.servidor, banco or config.banco, config.usuario, config.senha, config.driver)

    def _conectar(self):
        """Abre a conexão com o SQL Server."""
        import pyodbc  # import tardio: demo e testes não precisam do driver ODBC

        try:
            self.conn = pyodbc.connect(
                f"DRIVER={{{self.driver}}};"
                f"SERVER={self.server};DATABASE={self.database};"
                f"UID={self.user};PWD={self.password};TrustServerCertificate=YES"
            )
            self.conn.autocommit = False
            self.cursor = self.conn.cursor()
            logger.info(f"Conectado ao banco {self.database}")
        except Exception as e:
            logger.error(f"Falha ao conectar ao banco: {e}", exc_info=True)
            raise

    def _reconectar(self):
        """Tenta reconectar automaticamente em caso de falha."""
        try:
            logger.warning("Conexão perdida. Tentando reconectar ao banco...")
            self._conectar()
            logger.info("Reconexão bem-sucedida.")
        except Exception as e:
            logger.critical(f"Erro ao tentar reconectar ao banco: {e}", exc_info=True)
            raise

    def execute(self, query, params=(), _tentativa=1):
        """Executa consultas e comandos SQL, com reconexão automática em falhas."""
        import pyodbc

        try:
            self.cursor.execute(query, params)

            try:
                result = self.cursor.fetchall()
                self.conn.commit()  # procedures que alteram dados e também devolvem linhas
                logger.debug(f"Query retornou {len(result)} linhas.")
                return [tuple(linha) for linha in result]
            except pyodbc.ProgrammingError:
                self.conn.commit()
                logger.debug("Query executada sem retorno (commit realizado).")
                return ACAO_REALIZADA

        except pyodbc.OperationalError as e:
            # Se a conexão caiu, reconecta e tenta de novo uma única vez
            if _tentativa > 1:
                raise
            logger.warning(f"Erro operacional no banco: {e}. Tentando reconectar...")
            self._reconectar()
            return self.execute(query, params, _tentativa=_tentativa + 1)

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Erro ao executar query no banco: {e}", exc_info=True)
            return []

    def close(self):
        """Fecha cursor e conexão."""
        try:
            if self.cursor:
                self.cursor.close()
            if self.conn:
                self.conn.close()
            logger.info("Conexao com o banco encerrada com sucesso.")
        except Exception as e:
            logger.warning(f"Falha ao encerrar conexao: {e}")
