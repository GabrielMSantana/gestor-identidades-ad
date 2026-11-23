import requests

from src.domain.dn import normalizar_cpf


class ADAPIClient:
    """Cliente da API interna que executa as escritas no AD (criar, mover, renomear, desativar)."""

    def __init__(self, base_url, auth_service, logger=None, token=None, sessao=None):
        self.base_url = base_url.rstrip("/")
        self.logger = logger
        self.auth_service = auth_service
        self.http = sessao or requests
        self.token = token or auth_service.obter_token_ad()
        self._atualizar_headers()

    def _atualizar_headers(self):
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def _renovar_token(self):
        novo_token = self.auth_service.obter_token_ad(forcar_renovacao=True)
        if novo_token:
            self.token = novo_token
            self._atualizar_headers()
            if self.logger:
                self.logger.info("Token renovado automaticamente.")
            return True
        else:
            if self.logger:
                self.logger.error("Falha ao renovar token.")
            return False

    def _post(self, endpoint, payload, retry=False):
        """Funcao generica para envio de requisicao POST"""
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.http.post(url, headers=self.headers, json=payload, timeout=60)

            # TOKEN EXPIRADO → tenta renovar uma vez
            if response.status_code == 401:
                if not retry:
                    if self.logger:
                        self.logger.warning("Token expirado. Renovando e tentando novamente...")

                    if self._renovar_token():
                        return self._post(endpoint, payload, retry=True)

                return {"error": "TOKEN_EXPIRED"}

            # erros da API
            if response.status_code >= 400:
                try:
                    return response.json()
                except ValueError:
                    return {"error": response.text}

            return response.json()

        except Exception as e:
            if self.logger:
                self.logger.error(f"Erro ao chamar endpoint {endpoint}: {e}")
            return {"error": str(e)}

    def criar_usuario(self, nmUsuario, sobreNome, displayName, nmLogon, senha, userDn, grupoDn, cpf):
        payload = {
            "nmUsuario": nmUsuario,
            "sobreNome": sobreNome,
            "displayName": displayName,
            "nmLogon": nmLogon,
            "senha": senha,
            "userDn": userDn,
            "grupoDn": grupoDn,
            "cpf": cpf
        }
        return self._post("/ad/criacaoUsuarios", payload)

    def modificar_usuario(self, userDnAntigo, grupoDnAntigo, userDnNovo, grupoDnNovo):
        payload = {
            "userDnAntigo": userDnAntigo,
            "grupoDnAntigo": grupoDnAntigo,
            "userDnNovo": userDnNovo,
            "grupoDnNovo": grupoDnNovo,
        }
        return self._post("/ad/modificaUsuarios", payload)

    def desativar_usuario(self, userDn, cpf=None):
        payload = {"userDn": userDn}

        if cpf:
            payload["cpf"] = normalizar_cpf(cpf)

        return self._post("/ad/desativaUsuario", payload)

    def renomear_usuario(self, cpf, novoNome, userDnAtual=None):
        payload = {
            "cpf": normalizar_cpf(cpf),
            "novoNome": novoNome,
        }

        if userDnAtual:
            payload["userDnAtual"] = userDnAtual

        return self._post("/ad/renomeiaUsuario", payload)
