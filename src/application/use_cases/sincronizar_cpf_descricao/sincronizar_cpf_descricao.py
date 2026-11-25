import unicodedata

from src.application.modo_execucao import ModoExecucao
from src.application.ports import CpfDescricaoRepository, DiretorioAD
from src.domain.dn import normalizar_cpf


class SincronizarCpfDescricaoUseCase:
    def __init__(
        self,
        repo: CpfDescricaoRepository,
        ad_service: DiretorioAD,
        logger,
        modo: ModoExecucao,
        sobrescrever_descricao=False,
        corrigir_login_por_nome=False,
        somente_desligados=False,
    ):
        self.repo = repo
        self.modo = modo
        self.ad_service = ad_service
        self.logger = logger
        self.sobrescrever_descricao = sobrescrever_descricao
        self.corrigir_login_por_nome = corrigir_login_por_nome
        self.somente_desligados = somente_desligados

        self._resetar_contadores()

    def _resetar_contadores(self):
        self.total = 0
        self.atualizados = 0
        self.ja_preenchidos = 0
        self.ignorados = 0
        self.erros = 0
        self.logins_corrigidos = 0
        self.lista_ignorados = []
        self.lista_erros = []
        self.lista_logins_corrigidos = []

    def executar(self):
        self._resetar_contadores()
        tipo_candidato = "desligados" if self.somente_desligados else "ativos"
        self.logger.warning(
            f"==== Iniciando rotina manual: sincronizar CPF na description do AD ({tipo_candidato}) ===="
        )

        if self.modo.dry_run:
            self.logger.warning("[DRY_RUN] Nenhuma description sera alterada no AD.")

        registros = self._buscar_usuarios()
        self.total = len(registros) if registros else 0

        self.logger.info(f"Total de usuarios {tipo_candidato} candidatos: {self.total}")

        if not registros:
            return

        for row in registros:
            id_registro, nome, login, cpf = row
            cpf = self._normalizar_cpf(cpf)
            descricao_esperada = cpf

            try:
                if not cpf or not login:
                    self._ignorar(id_registro, login, cpf, "CPF ou login vazio")
                    continue

                usuario_ad = self.ad_service.buscar_usuario_por_login_exato(login)

                if not usuario_ad:
                    usuario_corrigido = self._tentar_corrigir_login_por_nome(
                        id_registro,
                        nome,
                        login,
                        cpf,
                    )

                    if usuario_corrigido:
                        usuario_ad = usuario_corrigido
                        login = usuario_ad["login"].upper()
                    else:
                        self._ignorar(id_registro, login, cpf, "login exato nao encontrado no AD")
                        continue

                dn = usuario_ad["dn"]
                descricao_atual = usuario_ad.get("description") or ""

                nome_compativel, nome_ad = self._nome_ad_compativel(nome, usuario_ad)
                if not nome_compativel:
                    usuario_corrigido = self._tentar_corrigir_login_por_nome(
                        id_registro,
                        nome,
                        login,
                        cpf,
                    )

                    if usuario_corrigido:
                        usuario_ad = usuario_corrigido
                        login = usuario_ad["login"].upper()
                        dn = usuario_ad["dn"]
                        descricao_atual = usuario_ad.get("description") or ""
                    else:
                        self._ignorar(
                            id_registro,
                            login,
                            cpf,
                            f"nome do AD nao confere com a tabela. tabela='{nome}' | ad='{nome_ad}' | dn={dn}"
                        )
                        continue

                if self.ad_service.esta_em_desligados(dn) and not self.somente_desligados:
                    self._ignorar(
                        id_registro,
                        login,
                        cpf,
                        f"usuario esta em Desligados: {dn}"
                    )
                    continue

                if descricao_atual.strip() == descricao_esperada:
                    self.ja_preenchidos += 1
                    continue

                if descricao_atual.strip() and not self.sobrescrever_descricao:
                    self._ignorar(
                        id_registro,
                        login,
                        cpf,
                        f"description ja preenchida com outro valor: '{descricao_atual}'"
                    )
                    continue

                atualizado = self.ad_service.atualizar_descricao_usuario(dn, descricao_esperada)

                if atualizado:
                    self.atualizados += 1
                    self.logger.info(f"[ATUALIZADO] login={login} | cpf={descricao_esperada} | dn={dn}")
                else:
                    self.erros += 1
                    self._registrar_erro(
                        id_registro,
                        login,
                        cpf,
                        f"falha ao atualizar description no AD. DN={dn}"
                    )
                    self.logger.error(f"[ERRO] Falha ao atualizar description de {login} | DN={dn}")

            except Exception as e:
                self.erros += 1
                self._registrar_erro(id_registro, login, cpf, str(e))
                self.logger.error(
                    f"[ERRO] Excecao ao processar ID={id_registro}, login={login}, cpf={cpf}: {e}",
                    exc_info=True
                )

        self._log_resumo()

    def _buscar_usuarios(self):
        return self.repo.listar_candidatos_cpf_descricao(self.somente_desligados)

    def _normalizar_cpf(self, cpf):
        return normalizar_cpf(cpf)

    def _tentar_corrigir_login_por_nome(self, id_registro, nome, login_atual, cpf):
        if not self.corrigir_login_por_nome:
            return None

        encontrados = self.ad_service.buscar_usuarios_por_nome_exato(nome)

        if len(encontrados) != 1:
            self.logger.warning(
                f"[LOGIN_NAO_CORRIGIDO] ID={id_registro} | login_atual={login_atual} | cpf={cpf} | nome='{nome}' | encontrados={len(encontrados)}"
            )
            return None

        usuario_ad = encontrados[0]
        login_novo = usuario_ad["login"]
        login_novo_banco = login_novo.upper()

        if self.ad_service.esta_em_desligados(usuario_ad["dn"]) and not self.somente_desligados:
            self.logger.warning(
                f"[LOGIN_NAO_CORRIGIDO] ID={id_registro} | login_atual={login_atual} | cpf={cpf} | motivo=usuario encontrado por nome esta em Desligados | dn={usuario_ad['dn']}"
            )
            return None

        if login_novo == str(login_atual).lower():
            return usuario_ad

        if self._atualizar_login_tabela(id_registro, cpf, login_atual, login_novo_banco):
            self.logins_corrigidos += 1
            self.lista_logins_corrigidos.append({
                "id": id_registro,
                "login_antigo": login_atual,
                "login_novo": login_novo_banco,
                "cpf": cpf,
                "dn": usuario_ad["dn"],
            })
            self.logger.warning(
                f"[LOGIN_CORRIGIDO] ID={id_registro} | cpf={cpf} | {login_atual} -> {login_novo_banco} | dn={usuario_ad['dn']}"
            )
            return usuario_ad

        return None

    def _atualizar_login_tabela(self, id_registro, cpf, login_antigo, login_novo):
        if self.modo.dry_run:
            self.logger.warning(
                f"[DRY_RUN] Atualizaria NM_LOGIN na tabela ID={id_registro}, CPF={cpf}: '{login_antigo}' -> '{login_novo}'."
            )
            return True

        return self.repo.atualizar_login(id_registro, cpf, login_novo)

    def _nome_ad_compativel(self, nome_banco, usuario_ad):
        nomes_ad = [
            usuario_ad.get("displayName") or "",
            usuario_ad.get("cn") or "",
            usuario_ad.get("name") or "",
        ]

        nome_banco_norm = self._normalizar_nome(nome_banco)

        for nome_ad in nomes_ad:
            nome_ad_norm = self._normalizar_nome(nome_ad)

            if not nome_ad_norm:
                continue

            if nome_ad_norm == nome_banco_norm:
                return True, nome_ad

            # Aceita truncamento no final do nome do AD. Ex:
            # MARIA APARECIDA SOUZ -> MARIA APARECIDA SOUZA
            if len(nome_ad_norm) >= 10 and nome_banco_norm.startswith(nome_ad_norm):
                return True, nome_ad

        nomes_validos = [nome for nome in nomes_ad if nome]
        return False, " | ".join(nomes_validos) if nomes_validos else "sem nome no AD"

    def _normalizar_nome(self, nome):
        if not nome:
            return ""

        nome = unicodedata.normalize("NFKD", str(nome))
        nome = "".join(ch for ch in nome if not unicodedata.combining(ch))
        nome = " ".join(nome.upper().strip().split())
        return nome

    def _ignorar(self, id_registro, login, cpf, motivo):
        self.ignorados += 1
        self.lista_ignorados.append({
            "id": id_registro,
            "login": login,
            "cpf": cpf,
            "motivo": motivo,
        })
        self.logger.warning(
            f"[IGNORADO] ID={id_registro} | login={login} | cpf={cpf} | motivo={motivo}"
        )

    def _registrar_erro(self, id_registro, login, cpf, motivo):
        self.lista_erros.append({
            "id": id_registro,
            "login": login,
            "cpf": cpf,
            "motivo": motivo,
        })

    def _log_resumo(self):
        tipo_candidato = "desligados" if self.somente_desligados else "ativos"
        self.logger.warning(f"==== Resumo sincronizacao CPF description ({tipo_candidato}) ====")
        self.logger.warning(f"Total candidatos: {self.total}")
        self.logger.warning(f"Atualizados: {self.atualizados}")
        self.logger.warning(f"Ja preenchidos: {self.ja_preenchidos}")
        self.logger.warning(f"Ignorados: {self.ignorados}")
        self.logger.warning(f"Erros: {self.erros}")
        self.logger.warning(f"Logins corrigidos: {self.logins_corrigidos}")

        if self.lista_logins_corrigidos:
            self.logger.warning("---- Logins corrigidos ----")
            for item in self.lista_logins_corrigidos:
                self.logger.warning(
                    f"LOGIN_CORRIGIDO | ID={item['id']} | cpf={item['cpf']} | login_antigo={item['login_antigo']} | login_novo={item['login_novo']} | dn={item['dn']}"
                )
            self.logger.warning(
                f"CPFS_LOGINS_CORRIGIDOS_IN = {self._formatar_cpfs_para_sql(self.lista_logins_corrigidos)}"
            )

        if self.lista_ignorados:
            self.logger.warning("---- CPFs ignorados ----")
            for item in self.lista_ignorados:
                self.logger.warning(
                    f"IGNORADO | ID={item['id']} | login={item['login']} | cpf={item['cpf']} | motivo={item['motivo']}"
                )
            self.logger.warning(
                f"CPFS_IGNORADOS_IN = {self._formatar_cpfs_para_sql(self.lista_ignorados)}"
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

        self.logger.warning(f"==== Fim sincronizacao CPF description ({tipo_candidato}) ====")

    def _formatar_cpfs_para_sql(self, itens):
        cpfs = []
        for item in itens:
            cpf = item.get("cpf")
            if cpf:
                cpfs.append(f"'{cpf}'")

        return f"({', '.join(cpfs)})"
