class CriarUsuarioValidator:
    def __init__(self, logger):
        self.logger = logger

    def normalizar_cpf(self, cpf):
        if cpf is None:
            return ""
        return "".join(ch for ch in str(cpf) if ch.isdigit())

    def validar_dados_criacao(self, id_tabela, nmLogon, cpf, userDn, grupoDn):
        if not id_tabela:
            raise ValueError("ID da tabela invalido.")

        if not nmLogon:
            raise ValueError("Login (nmLogon) invalido.")

        cpf = self.normalizar_cpf(cpf)
        if len(cpf) != 11:
            raise ValueError(f"CPF invalido para login '{nmLogon}': '{cpf}'")

        if not userDn:
            raise ValueError("USER_DN invalido.")

        if userDn in ("CENTRO_CUSTO INVALIDO", "NAO POSSUI CAMINHO (FUNCAO GENERICA)"):
            raise ValueError(f"USER_DN sem caminho valido para login '{nmLogon}': '{cpf}'")

        if not grupoDn:
            raise ValueError("GRUPO_DN invalido.")

        return cpf
