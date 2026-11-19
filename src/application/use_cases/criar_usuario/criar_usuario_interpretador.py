class CriarUsuarioInterpretador:
    def __init__(self, logger):
        self.logger = logger

    def interpretar(self, resp):
        """
        Normaliza o retorno da API AD para três estados:
        - sucesso
        - existente
        - erro
        """

        if not isinstance(resp, dict):
            texto = str(resp).lower()
            return "erro", texto

        bruto = (
            f"{resp.get('status', '')} "
            f"{resp.get('retorno', '')} "
            f"{resp.get('erro', '')} "
            f"{resp.get('error', '')}"
        ).lower()

        if any(p in bruto for p in ["sucesso", "success", "criado"]):
            return "sucesso", bruto

        if any(p in bruto for p in ["existente", "entryalreadyexists", "already exists"]):
            return "existente", bruto

        return "erro", bruto
