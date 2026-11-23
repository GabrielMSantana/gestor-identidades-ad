"""Active Directory real: escrita pela API interna e leitura via LDAP (ldap3)."""
import re

from src.config.settings import ConfigAD


def _escapar(valor) -> str:
    """Escapa caracteres especiais de filtro LDAP (RFC 4515): * ( ) \\ NUL."""
    from ldap3.utils.conv import escape_filter_chars

    return escape_filter_chars(str(valor))


class ADService:
    def __init__(self, config: ConfigAD, logger, api=None, dry_run=False):
        """
        api=None desliga as escritas pela API (modo DRY_RUN e rotinas só de LDAP).
        dry_run=True também bloqueia a escrita de description via LDAP.
        """
        self.config = config
        self.logger = logger
        self.api = api
        self.dry_run = dry_run

    # Metodos de API
    def criar(self, nmUsuario, sobreNome, displayName, nmLogon, senha, userDn, grupoDn, cpf):
        if not self.api:
            self.logger.info(f"[DRY_RUN] API AD desabilitada. Criaria usuario '{nmLogon}' CPF='{cpf}' em '{userDn}'.")
            return {"status": "DRY_RUN"}
        return self.api.criar_usuario(nmUsuario, sobreNome, displayName, nmLogon, senha, userDn, grupoDn, cpf)

    def modificar(self, userDnAntigo, grupoDnAntigo, userDnNovo, grupoDnNovo):
        if not self.api:
            self.logger.info(f"[DRY_RUN] API AD desabilitada. Moveria '{userDnAntigo}' para '{userDnNovo}'.")
            return {"status": "DRY_RUN"}
        return self.api.modificar_usuario(userDnAntigo, grupoDnAntigo, userDnNovo, grupoDnNovo)

    def renomear(self, cpf, novoNome, userDnAtual=None):
        if not self.api:
            self.logger.info(
                f"[DRY_RUN] API AD desabilitada. Renomearia CPF='{cpf}' para '{novoNome}'."
            )
            return {"status": "DRY_RUN"}
        return self.api.renomear_usuario(cpf, novoNome, userDnAtual)

    def desativar(self, userDn: str, cpf=None):
        if not self.api:
            self.logger.info(f"[DRY_RUN] API AD desabilitada. Desativaria '{userDn}' CPF='{cpf}'.")
            return {"status": "DRY_RUN"}
        return self.api.desativar_usuario(userDn, cpf)

    # Metodos LDAP
    def _conectar(self):
        from ldap3 import ALL, Connection, Server

        server = Server(self.config.servidor, get_info=ALL)
        return Connection(
            server,
            user=self.config.usuario,
            password=self.config.senha,
            auto_bind=True
        )

    def _buscar(self, search_filter, attributes, search_base=None):
        """Abre conexão, pesquisa e sempre fecha (unbind), devolvendo as entries."""
        from ldap3 import SUBTREE

        conn = self._conectar()
        try:
            conn.search(
                search_base=search_base or self.config.base_dn,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=attributes
            )
            return list(conn.entries)
        finally:
            conn.unbind()

    @staticmethod
    def _texto(entry, atributo):
        valores = entry.entry_attributes_as_dict.get(atributo) or []
        return str(valores[0]) if valores else ""

    def _usuario(self, entry):
        return {
            "dn": self._texto(entry, "distinguishedName"),
            "login": self._texto(entry, "sAMAccountName").lower(),
            "description": self._texto(entry, "description"),
            "displayName": self._texto(entry, "displayName"),
            "cn": self._texto(entry, "cn"),
            "name": self._texto(entry, "name"),
        }

    def buscar_multiplos_por_nome(self, nome):
        """
        Retorna TODOS os usuários com displayName ou cn exatamente iguais ao nome.
        """
        try:
            nome = _escapar(nome)
            search_filter = f"(&(objectClass=user)(|(displayName={nome})(cn={nome})))"
            entries = self._buscar(search_filter, ["distinguishedName", "sAMAccountName"])

            return [
                {"dn": self._texto(e, "distinguishedName"), "login": self._texto(e, "sAMAccountName").lower()}
                for e in entries
            ]

        except Exception as e:
            self.logger.error(f"Erro ao buscar multiplos usuarios com nome {nome}: {e}")
            return []

    def buscar_usuarios_por_nome_exato(self, nome):
        """
        Retorna usuarios cujo displayName ou cn batem exatamente com o nome informado.
        Usado somente para correcoes conservadoras de login.
        """
        try:
            nome = _escapar(nome)
            search_filter = f"(&(objectClass=user)(|(displayName={nome})(cn={nome})))"
            entries = self._buscar(
                search_filter, ["distinguishedName", "sAMAccountName", "displayName", "cn", "name"]
            )
            return [self._usuario(e) for e in entries]

        except Exception as e:
            self.logger.error(f"Erro ao buscar usuarios por nome exato {nome}: {e}")
            return []

    def buscar_user_dn_por_login_exato(self, login):
        """
        Busca DN usando apenas sAMAccountName exatamente igual ao login.
        Sem wildcard no CN para evitar matches incorretos.
        """
        try:
            search_filter = f"(&(objectClass=user)(sAMAccountName={_escapar(login)}))"
            entries = self._buscar(search_filter, ["distinguishedName"])

            if not entries:
                return None

            return self._texto(entries[0], "distinguishedName")

        except Exception as e:
            self.logger.error(f"Erro ao buscar login exato {login}: {e}")
            return None

    def buscar_usuario_por_login_exato(self, login):
        """
        Busca um unico usuario pelo sAMAccountName exato e retorna dados basicos.
        Usado em rotinas sensiveis que nao podem depender de nome parecido.
        """
        try:
            search_filter = f"(&(objectClass=user)(sAMAccountName={_escapar(login)}))"
            entries = self._buscar(
                search_filter,
                ["distinguishedName", "sAMAccountName", "description", "displayName", "cn", "name"]
            )

            if len(entries) != 1:
                self.logger.warning(f"Login exato '{login}' retornou {len(entries)} resultado(s) no AD.")
                return None

            return self._usuario(entries[0])

        except Exception as e:
            self.logger.error(f"Erro ao buscar usuario por login exato {login}: {e}")
            return None

    def buscar_usuarios_por_cpf_descricao(self, cpf):
        """
        Busca usuarios no AD cujo campo description seja exatamente o CPF.
        Retorna lista para permitir detectar duplicidade.
        """
        try:
            cpf = "".join(ch for ch in str(cpf) if ch.isdigit())

            search_filter = f"(&(objectClass=user)(description={cpf}))"
            entries = self._buscar(
                search_filter,
                ["distinguishedName", "sAMAccountName", "description", "displayName", "cn", "name"]
            )
            return [self._usuario(e) for e in entries]

        except Exception as e:
            self.logger.error(f"Erro ao buscar usuarios por CPF na description {cpf}: {e}")
            return []

    def atualizar_descricao_usuario(self, dn_usuario: str, descricao: str):
        """Atualiza o campo description de um usuario do AD via LDAP."""
        if self.dry_run:
            self.logger.info(f"[DRY_RUN] Atualizaria description de '{dn_usuario}' para '{descricao}'.")
            return True

        try:
            from ldap3 import MODIFY_REPLACE

            conn = self._conectar()
            try:
                conn.modify(dn_usuario, {"description": (MODIFY_REPLACE, [descricao])})
                sucesso = conn.result.get("description") == "success"
            finally:
                conn.unbind()

            if not sucesso:
                self.logger.error(f"Falha ao atualizar description de '{dn_usuario}': {conn.result}")

            return sucesso

        except Exception as e:
            self.logger.error(f"Erro ao atualizar description de '{dn_usuario}': {e}")
            return False

    def buscar_grupo_atual(self, dn_usuario: str):
        """
        Retorna o grupo atual (memberOf) do usuário no AD.
        A API exige esse valor para remover o colaborador do grupo antigo.
        """
        try:
            from ldap3 import BASE

            conn = self._conectar()
            try:
                conn.search(
                    search_base=dn_usuario,
                    search_filter="(objectClass=user)",
                    search_scope=BASE,
                    attributes=["memberOf"]
                )
                entries = list(conn.entries)
            finally:
                conn.unbind()

            if not entries:
                return None

            grupos = entries[0].memberOf

            if not grupos:
                return None

            return str(grupos[0])

        except Exception as e:
            self.logger.error(f"Erro ao buscar grupo atual de {dn_usuario}: {e}")
            return None

    def esta_em_desligados(self, dn_usuario: str) -> bool:
        """Verifica se o DN do usuario contem o caminho da pasta de desligados"""
        if not dn_usuario:
            return False
        return re.search(re.escape(self.config.pasta_desligados), dn_usuario, re.IGNORECASE) is not None
