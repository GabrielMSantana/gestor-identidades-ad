from src.domain.dn import normalizar_dn


class CriarUsuarioMapper:
    def __init__(self, logger):
        self.logger = logger

    def normalizar_dns(self, userDn, grupoDn):
        try:
            userDn = normalizar_dn(userDn)
            grupoDn = normalizar_dn(grupoDn)
            return userDn, grupoDn
        except Exception as e:
            self.logger.error(f"Erro ao normalizar DN: {e}")
            raise

    def montar_payload(self, nmUsuario, sobreNome, displayName, nmLogon, senha, userDn, grupoDn, cpf):
        """
        Mantém exatamente o mesmo payload utilizado antes.
        """
        return {
            "nmUsuario": nmUsuario,
            "sobreNome": sobreNome,
            "displayName": displayName,
            "nmLogon": nmLogon,
            "senha": senha,
            "userDn": userDn,
            "grupoDn": grupoDn,
            "cpf": cpf
        }
