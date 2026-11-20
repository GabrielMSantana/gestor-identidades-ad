from src.domain.dn import normalizar_dn


class ModificarUsuarioMapper:
    def __init__(self, logger):
        self.logger = logger

    def normalizar_dns(self, userDnAntigo, userDnNovo, grupoAntigo, grupoNovo):
        try:
            return (
                normalizar_dn(userDnAntigo),
                normalizar_dn(userDnNovo),
                normalizar_dn(grupoAntigo),
                normalizar_dn(grupoNovo),
            )
        except Exception as e:
            self.logger.error(f"Erro ao normalizar DN: {e}")
            raise

    @staticmethod
    def normaliza_para_comparar(dn: str) -> str:
        """Usa o normalizador oficial e prepara o DN para comparação segura"""
        if not dn:
            return ""
        dn = normalizar_dn(dn)
        return dn.replace(" ", "").strip().lower()
