import base64
import logging

import requests

logger = logging.getLogger("gestor_identidades_ad")


class AuthAPIClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.auth_url = f"{self.base_url}/auth/token"

    def obter_token(self, username, password):
        """Obtém o token JWT via Basic Auth"""
        try:
            # Monta o header Basic Auth manualmente
            credenciais = f"{username}:{password}"
            encoded = base64.b64encode(credenciais.encode()).decode()
            headers = {"Authorization": f"Basic {encoded}"}

            response = requests.get(self.auth_url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            token = data.get("token")
            expira_em = data.get("expira_em")

            if not token:
                raise ValueError("Token não encontrado na resposta da API")

            logger.info(f"Token obtido com sucesso. Expira em: {expira_em}")
            return token

        except Exception as e:
            logger.error(f"Erro ao obter token JWT: {e}")
            return None
