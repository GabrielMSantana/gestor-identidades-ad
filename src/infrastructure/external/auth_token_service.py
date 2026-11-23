from src.infrastructure.external.auth_api_client import AuthAPIClient


class AuthTokenService:
    """Obtém o JWT da API interna do AD.

    As credenciais da API ficam criptografadas no próprio SQL Server
    (chave simétrica + certificado) e são lidas uma única vez por execução.
    O token também fica em cache até a API responder 401.
    """

    _token_cache = None
    _cred_cache = None

    # Nomes genéricos: no ambiente real vêm do banco de credenciais da empresa.
    QUERY_CREDENCIAL = """
        OPEN SYMMETRIC KEY KEY_CREDENCIAIS_API
        DECRYPTION BY CERTIFICATE CERT_CREDENCIAIS_API;

        SELECT CONVERT(VARCHAR(MAX), DecryptByKey([USERNAME])) AS USERNAME,
               CONVERT(VARCHAR(MAX), DecryptByKey([PASSWORD])) AS PASSWORD
        FROM seguranca.TB_CREDENCIAL_API
        WHERE ID = ?
    """

    def __init__(self, db_credenciais, url_api, id_credencial, logger, auth_api=None):
        self.logger = logger
        self.db = db_credenciais
        self.id_credencial = id_credencial
        self.auth_api = auth_api or AuthAPIClient(url_api)

    def _carregar_credenciais(self):
        """Lê credenciais do banco apenas UMA vez."""
        if AuthTokenService._cred_cache:
            return AuthTokenService._cred_cache

        resultado = self.db.execute(self.QUERY_CREDENCIAL, (self.id_credencial,))

        if not resultado or not isinstance(resultado, list):
            self.logger.error(f"Nenhuma credencial encontrada para ID={self.id_credencial}.")
            return None

        AuthTokenService._cred_cache = resultado[0]
        return AuthTokenService._cred_cache

    def obter_token_ad(self, forcar_renovacao=False):
        """Retorna o token JWT, gerando apenas se necessário."""

        # Reaproveita o token se já existir (a não ser que tenha expirado)
        if AuthTokenService._token_cache and not forcar_renovacao:
            return AuthTokenService._token_cache

        try:
            credencial = self._carregar_credenciais()
            if not credencial:
                return None

            username, password = credencial

            token = self.auth_api.obter_token(username, password)

            if token:
                self.logger.info("Token JWT recuperado com sucesso.")
                AuthTokenService._token_cache = token
            else:
                self.logger.warning("Falha ao recuperar token JWT.")

            return token

        except Exception as e:
            self.logger.error(f"Erro ao obter token de autenticação: {e}")
            return None
