class ModificarUsuarioInterpretador:
    def __init__(self, logger):
        self.logger = logger

    def interpretar(self, resp):
        if not isinstance(resp, dict):
            return "erro", str(resp).lower()

        bruto = (
            f"{resp.get('status','')} "
            f"{resp.get('erro','')} "
            f"{resp.get('error','')}"
        ).lower()

        if "sucesso" in bruto or "movimentado" in bruto:
            return "sucesso", bruto

        return "erro", bruto
