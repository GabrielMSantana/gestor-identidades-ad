from src.application.ports import CpfDescricaoRepository, DiretorioAD
from src.domain.dn import normalizar_cpf


class ValidarCpfDescricaoADUseCase:
    """Auditoria: so consulta banco e AD, nunca altera nada."""

    def __init__(self, repo: CpfDescricaoRepository, ad_service: DiretorioAD, logger):
        self.repo = repo
        self.ad_service = ad_service
        self.logger = logger

        self._resetar_contadores()

    def _resetar_contadores(self):
        self.total = 0
        self.encontrados = 0
        self.nao_encontrados = 0
        self.duplicados = 0
        self.em_desligados = 0
        self.erros = 0

        self.lista_nao_encontrados = []
        self.lista_duplicados = []
        self.lista_em_desligados = []
        self.lista_erros = []

    def executar(self):
        self._resetar_contadores()
        self.logger.warning("==== Iniciando rotina manual: validar CPF na description do AD (ativos) ====")

        registros = self._buscar_usuarios_ativos()
        self.total = len(registros) if registros else 0
        self.logger.info(f"Total de usuarios ativos na tabela: {self.total}")

        if not registros:
            self._log_resumo()
            return

        for row in registros:
            id_registro, nome, login, cpf = row
            cpf = self._normalizar_cpf(cpf)

            try:
                if not cpf:
                    self._registrar_erro(id_registro, login, cpf, "CPF vazio")
                    continue

                encontrados = self.ad_service.buscar_usuarios_por_cpf_descricao(cpf)
                total_encontrados = len(encontrados)

                if total_encontrados == 0:
                    self.nao_encontrados += 1
                    self.lista_nao_encontrados.append({
                        "id": id_registro,
                        "nome": nome,
                        "login": login,
                        "cpf": cpf,
                    })
                    continue

                if total_encontrados > 1:
                    self.duplicados += 1
                    self.lista_duplicados.append({
                        "id": id_registro,
                        "nome": nome,
                        "login": login,
                        "cpf": cpf,
                        "dns": [item["dn"] for item in encontrados],
                    })
                    continue

                usuario_ad = encontrados[0]

                if self.ad_service.esta_em_desligados(usuario_ad["dn"]):
                    self.em_desligados += 1
                    self.lista_em_desligados.append({
                        "id": id_registro,
                        "nome": nome,
                        "login": login,
                        "cpf": cpf,
                        "dn": usuario_ad["dn"],
                        "login_ad": usuario_ad["login"],
                    })
                    continue

                self.encontrados += 1

            except Exception as e:
                self._registrar_erro(id_registro, login, cpf, str(e))

        self._log_resumo()

    def _buscar_usuarios_ativos(self):
        return self.repo.listar_ativos_com_cpf()

    def _normalizar_cpf(self, cpf):
        return normalizar_cpf(cpf)

    def _registrar_erro(self, id_registro, login, cpf, motivo):
        self.erros += 1
        self.lista_erros.append({
            "id": id_registro,
            "login": login,
            "cpf": cpf,
            "motivo": motivo,
        })
        self.logger.error(
            f"[ERRO] ID={id_registro} | login={login} | cpf={cpf} | motivo={motivo}"
        )

    def _log_resumo(self):
        self.logger.warning("==== Resumo validacao CPF description AD (ativos) ====")
        self.logger.warning(f"Total ativos na tabela: {self.total}")
        self.logger.warning(f"Encontrados por CPF no AD: {self.encontrados}")
        self.logger.warning(f"Nao encontrados: {self.nao_encontrados}")
        self.logger.warning(f"Duplicados no AD: {self.duplicados}")
        self.logger.warning(f"Encontrados em Desligados: {self.em_desligados}")
        self.logger.warning(f"Erros: {self.erros}")

        if self.lista_nao_encontrados:
            self.logger.warning("---- CPFs nao encontrados ----")
            for item in self.lista_nao_encontrados:
                self.logger.warning(
                    f"NAO_ENCONTRADO | ID={item['id']} | login={item['login']} | cpf={item['cpf']} | nome={item['nome']}"
                )
            self.logger.warning(
                f"CPFS_NAO_ENCONTRADOS_IN = {self._formatar_cpfs_para_sql(self.lista_nao_encontrados)}"
            )

        if self.lista_duplicados:
            self.logger.warning("---- CPFs duplicados no AD ----")
            for item in self.lista_duplicados:
                self.logger.warning(
                    f"DUPLICADO | ID={item['id']} | login={item['login']} | cpf={item['cpf']} | nome={item['nome']}"
                )
            self.logger.warning(
                f"CPFS_DUPLICADOS_IN = {self._formatar_cpfs_para_sql(self.lista_duplicados)}"
            )

        if self.lista_em_desligados:
            self.logger.warning("---- CPFs encontrados em Desligados ----")
            for item in self.lista_em_desligados:
                self.logger.warning(
                    f"EM_DESLIGADOS | ID={item['id']} | login={item['login']} | cpf={item['cpf']} | login_ad={item['login_ad']} | dn={item['dn']}"
                )
            self.logger.warning(
                f"CPFS_EM_DESLIGADOS_IN = {self._formatar_cpfs_para_sql(self.lista_em_desligados)}"
            )

        if self.lista_erros:
            self.logger.warning("---- CPFs com erro ----")
            for item in self.lista_erros:
                self.logger.warning(
                    f"ERRO | ID={item['id']} | login={item['login']} | cpf={item['cpf']} | motivo={item['motivo']}"
                )
            self.logger.warning(
                f"CPFS_ERROS_IN = {self._formatar_cpfs_para_sql(self.lista_erros)}"
            )

        self.logger.warning("==== Fim validacao CPF description AD (ativos) ====")

    def _formatar_cpfs_para_sql(self, itens):
        cpfs = []
        for item in itens:
            cpf = item.get("cpf")
            if cpf:
                cpfs.append(f"'{cpf}'")

        return f"({', '.join(cpfs)})"
