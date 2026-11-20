class DesativarUsuarioInterpretador:
    def __init__(self, logger):
        self.logger = logger

    def interpretar(self, resp):
        if not isinstance(resp, dict):
            return "erro", str(resp).lower()

        bruto = (
            f"{resp.get('status','')} "
            f"{resp.get('mensagem','')} "
            f"{resp.get('novo_dn','')} "
            f"{resp.get('error','')} "
            f"{resp.get('detalhe','')} "
            f"{resp.get('novo_dn_tentado','')} "
            f"{resp.get('novo_dn_alternativo_tentado','')}"
        ).lower()

        if "success" in bruto or "sucesso" in bruto:
            return "sucesso", bruto

        if "error" in bruto:
            return "erro", bruto

        return "erro", bruto
