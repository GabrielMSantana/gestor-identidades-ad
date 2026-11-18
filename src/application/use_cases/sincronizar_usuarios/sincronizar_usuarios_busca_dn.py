from src.application.ports import DiretorioAD
from src.domain.dn import normalizar_cpf, normalizar_dn
from src.domain.excecoes import CpfDuplicadoADException

# Mantido aqui também para os imports antigos continuarem funcionando.
__all__ = ["SincronizarUsuarioBuscaDN", "CpfDuplicadoADException"]


class SincronizarUsuarioBuscaDN:
    def __init__(self, ad_service: DiretorioAD, logger):
        self.ad_service = ad_service
        self.logger = logger

    def buscar_dn(self, login, nome, cpf=None):
        """
         Busca segura:
        1) CPF na description do AD, quando informado
        2) Nome exato
        3) Login quando houver multiplos por nome
        4) Ultimo sobrenome como apoio legado
        5) Fallback por login exato
        """

        dn_por_cpf = self._buscar_dn_por_cpf(cpf, login)
        if dn_por_cpf:
            return dn_por_cpf

        return self._buscar_dn_legado(login, nome)

    def _buscar_dn_por_cpf(self, cpf, login):
        cpf = normalizar_cpf(cpf)

        if not cpf:
            return None

        encontrados = self.ad_service.buscar_usuarios_por_cpf_descricao(cpf)
        total = len(encontrados)

        if total == 0:
            self.logger.debug(
                f"[AD][CPF] Nenhum usuario encontrado por CPF na description. login={login} | cpf={cpf}. Usando fallback por nome/login."
            )
            return None

        if total > 1:
            self.logger.error(
                f"[AD][CPF_DUPLICADO] CPF {cpf} retornou {total} usuarios no AD. login_tabela={login}. Movimentacao deve ser bloqueada pelo fluxo chamador."
            )
            for item in encontrados:
                self.logger.error(
                    f"[AD][CPF_DUPLICADO_DETALHE] cpf={cpf} | login_ad={item.get('login')} | dn={item.get('dn')}"
                )
            raise CpfDuplicadoADException(
                f"CPF {cpf} retornou {total} usuarios no AD. Movimentacao bloqueada."
            )

        usuario = encontrados[0]
        dn = usuario.get("dn")

        if not dn:
            self.logger.warning(
                f"[AD][CPF] Usuario encontrado por CPF, mas sem DN. login={login} | cpf={cpf}"
            )
            return None

        if self.ad_service.esta_em_desligados(dn):
            self.logger.warning(
                f"[AD][CPF] Usuario encontrado por CPF esta em Desligados. login={login} | cpf={cpf} | dn={dn}"
            )
        else:
            self.logger.debug(
                f"[AD][CPF] Usuario localizado por CPF na description. login={login} | cpf={cpf} | dn={dn}"
            )

        return normalizar_dn(dn)

    def _buscar_dn_legado(self, login, nome):
        """
        Fluxo legado:
        1) Busca todos por nome
        2) Se houver somente um, retorna
        3) Se houver varios, escolhe por sAMAccountName = login
        4) Se nenhum combinar, tenta ultimo sobrenome
        5) Fallback por login exato
        """

        encontrados = self.ad_service.buscar_multiplos_por_nome(nome)

        if not encontrados:
            return self._fallback_login(login)

        if len(encontrados) == 1:
            dn = encontrados[0]["dn"]
            self.logger.debug(
                f"[AD][NOME] Usuario localizado por nome unico. login={login} | nome={nome} | dn={dn}"
            )
            return normalizar_dn(dn)

        login_lower = str(login).lower()

        for item in encontrados:
            if item["login"] == login_lower:
                dn = item["dn"]
                self.logger.debug(
                    f"[AD][NOME_LOGIN] Usuario localizado por nome multiplo + login. login={login} | nome={nome} | dn={dn}"
                )
                return normalizar_dn(dn)

        try:
            ultimo_sobrenome = str(nome).strip().split(" ")[-1].lower()
            for item in encontrados:
                dn_lower = item["dn"].lower()
                if ultimo_sobrenome in dn_lower:
                    dn = item["dn"]
                    self.logger.warning(
                        f"[AD][NOME_SOBRENOME] Usuario localizado por ultimo sobrenome. login={login} | nome={nome} | dn={dn}"
                    )
                    return normalizar_dn(dn)
        except Exception:
            pass

        self.logger.warning(
            f"[AD] Nome '{nome}' retornou varios resultados, mas nenhum com login '{login}'. Tentando fallback por login exato..."
        )

        return self._fallback_login(login)

    def _fallback_login(self, login):
        dn = self.ad_service.buscar_user_dn_por_login_exato(login)
        if dn:
            self.logger.debug(
                f"[AD][LOGIN] Usuario localizado por login exato. login={login} | dn={dn}"
            )
            return normalizar_dn(dn)
        return None
