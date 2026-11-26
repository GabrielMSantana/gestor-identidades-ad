"""Banco em memória (demo e testes).

Implementa os mesmos contratos do repositório SQL Server e simula, em Python,
o que as procedures fazem no banco real:

- batimento: copia os ativos do RH para a tabela de colaboradores ativos;
- fila de criação: calcula login, USER_DN e GRUPO_DN dos admitidos;
- atualização cadastral: atualiza nome/função/centro de custo e devolve
  quem precisa ser renomeado no AD;
- fila de movimentação: quem mudou de OU ou de grupo;
- desligamentos: quem está ativo na tabela, mas saiu do RH.
"""
import unicodedata
from collections.abc import Sequence
from datetime import date

from src.domain.dn import (
    CAMINHOS_INVALIDOS,
    caminho_invalido,
    caminho_pai,
    extrair_cn,
    normalizar_cpf,
    normalizar_dn,
    normalizar_para_comparar,
)
from src.domain.status import StatusUsuario
from src.infrastructure.repositories.sqlserver_identidades_repository import CENTRO_CUSTO_FORA_MOVIMENTACAO
from src.infrastructure.rh.rh_falso import Organograma, RHFalso


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(ch for ch in texto if not unicodedata.combining(ch))


class BancoIdentidadesMemoria:
    def __init__(self, rh: RHFalso, organograma: Organograma, logger, dry_run: bool = False):
        self.rh = rh
        self.organograma = organograma
        self.logger = logger
        self.dry_run = dry_run

        self.colaboradores_ativos: dict[str, object] = {}
        self.usuarios: dict[int, dict] = {}
        self.fila_movimentacao: list[dict] = []
        self._proximo_id = 1

    # ------------------------------------------------------------ montagem do cenário
    def inserir_usuario(self, nome, login, cpf, user_dn, grupo_dn, status=StatusUsuario.ATIVO,
                        id_centro_custo="", centro_custo="", funcao="") -> int:
        id_registro = self._proximo_id
        self._proximo_id += 1
        self.usuarios[id_registro] = {
            "ID": id_registro,
            "NM_COLABORADOR": nome,
            "NM_LOGIN": login.upper(),
            "NU_CPF_COLABORADOR": cpf,
            "USER_DN": user_dn,
            "GRUPO_DN": grupo_dn,
            "TP_STATUS": int(status),
            "ID_CENTRO_CUSTO": id_centro_custo,
            "CENTRO_CUSTO": centro_custo,
            "NM_FUNCAO": funcao,
            "DESC_FUNCAO": funcao.title(),
            "AFASTAMENTO": "N",
            "DT_ATUALIZACAO": None,
        }
        return id_registro

    def snapshot(self):
        return sorted(
            (u["ID"], u["NM_LOGIN"], u["USER_DN"], u["GRUPO_DN"], u["TP_STATUS"]) for u in self.usuarios.values()
        )

    def _por_cpf(self, cpf) -> list[dict]:
        return [u for u in self.usuarios.values() if u["NU_CPF_COLABORADOR"] == str(cpf)]

    def _tocar(self, usuario: dict) -> None:
        usuario["DT_ATUALIZACAO"] = date.today()

    def _gerar_login(self, nome: str) -> str:
        partes = _sem_acento(nome).lower().split()
        base = f"{partes[0]}.{partes[-1]}" if len(partes) > 1 else partes[0]
        existentes = {u["NM_LOGIN"].lower() for u in self.usuarios.values()}
        login, n = base, 2
        while login in existentes:
            login, n = f"{base}{n}", n + 1
        return login

    # ------------------------------------------------------------ batimento
    def executar_batimento(self) -> None:
        self.colaboradores_ativos = {c.cpf: c for c in self.rh.ativos()}

    # ------------------------------------------------------------ criação
    def gerar_fila_criacao(self) -> None:
        ja_na_tabela = {
            u["NU_CPF_COLABORADOR"] for u in self.usuarios.values()
            if u["TP_STATUS"] in (StatusUsuario.PENDENTE, StatusUsuario.ATIVO)
        }
        for colaborador in self.colaboradores_ativos.values():
            if colaborador.cpf in ja_na_tabela:
                continue
            ou, grupo = self.organograma.destino(colaborador.id_centro_custo)
            user_dn = ou if caminho_invalido(ou) else f"cn={colaborador.nome},{ou}"
            self.inserir_usuario(
                colaborador.nome, self._gerar_login(colaborador.nome), colaborador.cpf, user_dn, grupo,
                StatusUsuario.PENDENTE, colaborador.id_centro_custo, colaborador.centro_custo, colaborador.funcao,
            )

    def listar_pendentes_criacao(self):
        linhas = []
        for u in self.usuarios.values():
            if u["TP_STATUS"] != StatusUsuario.PENDENTE:
                continue
            if u["USER_DN"] in CAMINHOS_INVALIDOS or u["GRUPO_DN"] in CAMINHOS_INVALIDOS:
                continue
            partes = u["NM_COLABORADOR"].strip().split(" ")
            linhas.append((
                u["ID"], u["NM_COLABORADOR"].strip(), partes[0], partes[-1],
                u["NM_LOGIN"].lower(), u["NU_CPF_COLABORADOR"], u["USER_DN"], u["GRUPO_DN"],
            ))
        return linhas

    def atualizar_status_criacao(self, id_tabela, nmLogon, status) -> None:
        if self.dry_run:
            return
        if status in ["sucesso", "existente"]:
            usuario = self.usuarios[int(id_tabela)]
            usuario["TP_STATUS"] = int(StatusUsuario.ATIVO)
            self._tocar(usuario)

    # ------------------------------------------------------------ atualização / renomeação
    def atualizar_cadastro_e_listar_renomeacoes(self):
        linhas = []
        for u in self.usuarios.values():
            if u["TP_STATUS"] != StatusUsuario.ATIVO:
                continue
            colaborador = self.colaboradores_ativos.get(u["NU_CPF_COLABORADOR"])
            if not colaborador:
                continue

            nome_antigo = u["NM_COLABORADOR"]
            # A procedure atualiza os metadados cadastrais direto na tabela
            u.update({
                "NM_COLABORADOR": colaborador.nome,
                "ID_CENTRO_CUSTO": colaborador.id_centro_custo,
                "CENTRO_CUSTO": colaborador.centro_custo,
                "NM_FUNCAO": colaborador.funcao,
                "DESC_FUNCAO": colaborador.desc_funcao,
                "AFASTAMENTO": colaborador.afastamento,
            })

            if extrair_cn(u["USER_DN"]) == colaborador.nome:
                continue

            linhas.append((
                u["ID"], u["NU_CPF_COLABORADOR"], u["NM_LOGIN"], nome_antigo, colaborador.nome,
                u["USER_DN"], f"cn={colaborador.nome},{caminho_pai(u['USER_DN'])}", u["GRUPO_DN"],
                colaborador.desc_funcao, colaborador.id_centro_custo, colaborador.centro_custo,
                colaborador.funcao, colaborador.afastamento, 1,
            ))
        return linhas

    def atualizar_user_dn_renomeado(self, cpf, user_dn_novo) -> None:
        if self.dry_run:
            return
        for u in self._por_cpf(cpf):
            u["USER_DN"] = user_dn_novo
            self._tocar(u)

    # ------------------------------------------------------------ movimentação
    def gerar_fila_movimentacao(self) -> None:
        self.fila_movimentacao = []  # TRUNCATE
        for u in self.usuarios.values():
            if u["TP_STATUS"] != StatusUsuario.ATIVO:
                continue
            colaborador = self.colaboradores_ativos.get(u["NU_CPF_COLABORADOR"])
            if not colaborador:
                continue

            ou, grupo = self.organograma.destino(colaborador.id_centro_custo)
            mudou_ou = normalizar_para_comparar(caminho_pai(u["USER_DN"])) != normalizar_para_comparar(ou)
            mudou_grupo = normalizar_para_comparar(u["GRUPO_DN"]) != normalizar_para_comparar(grupo)
            if not (mudou_ou or mudou_grupo):
                continue

            user_dn = ou if caminho_invalido(ou) else f"cn={extrair_cn(u['USER_DN'])},{ou}"
            self.fila_movimentacao.append({
                "NU_CPF_COLABORADOR": u["NU_CPF_COLABORADOR"],
                "USER_DN": user_dn,
                "GRUPO": grupo,
                "TP_STATUS": 0,
                "DT_ATUALIZACAO": None,
                "ID_CENTRO_CUSTO": colaborador.id_centro_custo,
            })

    def listar_movimentacoes_pendentes(self):
        linhas = set()
        for item in self.fila_movimentacao:
            if item["TP_STATUS"] != 0 or item["DT_ATUALIZACAO"] is not None:
                continue
            if item["ID_CENTRO_CUSTO"] == CENTRO_CUSTO_FORA_MOVIMENTACAO:
                continue
            for u in self._por_cpf(item["NU_CPF_COLABORADOR"]):
                linhas.add((
                    item["NU_CPF_COLABORADOR"], u["NM_COLABORADOR"], u["NM_LOGIN"],
                    u["USER_DN"], u["GRUPO_DN"], item["USER_DN"], item["GRUPO"],
                ))
        return sorted(linhas)

    def atualizar_fila_movimentacao(self, nuCpf, userDnNovo, grupoDnNovo) -> None:
        if self.dry_run:
            return
        for item in self.fila_movimentacao:
            if item["NU_CPF_COLABORADOR"] == str(nuCpf):
                item.update({"TP_STATUS": 1, "USER_DN": userDnNovo, "GRUPO": grupoDnNovo, "DT_ATUALIZACAO": date.today()})

    def atualizar_tabela_usuarios(self, nuCpf, userDnNovo, grupoDnNovo) -> None:
        if self.dry_run:
            return
        for u in self._por_cpf(nuCpf):
            u["USER_DN"], u["GRUPO_DN"] = userDnNovo, grupoDnNovo
            self._tocar(u)

    # ------------------------------------------------------------ sincronização
    def listar_ativos_para_sincronia(self, cpfs_ignorados: Sequence[str]):
        ignorados = {normalizar_cpf(c) for c in cpfs_ignorados}
        return [
            (u["ID"], u["NM_COLABORADOR"], u["NM_LOGIN"], u["USER_DN"], u["GRUPO_DN"], u["NU_CPF_COLABORADOR"])
            for u in self.usuarios.values()
            if u["TP_STATUS"] == StatusUsuario.ATIVO and u["NU_CPF_COLABORADOR"] not in ignorados
        ]

    # ------------------------------------------------------------ desligamento
    def listar_desligamentos(self):
        return [
            (u["ID"], u["NM_COLABORADOR"], u["NM_LOGIN"], u["USER_DN"], u["GRUPO_DN"], u["NU_CPF_COLABORADOR"])
            for u in self.usuarios.values()
            if u["TP_STATUS"] == StatusUsuario.ATIVO and u["NU_CPF_COLABORADOR"] not in self.colaboradores_ativos
        ]

    def listar_desligados(self):
        linhas = [
            (u["ID"], u["NM_COLABORADOR"], u["NM_LOGIN"], u["NU_CPF_COLABORADOR"], u["USER_DN"])
            for u in self.usuarios.values() if u["TP_STATUS"] == StatusUsuario.DESLIGADO
        ]
        return sorted(linhas, key=lambda linha: linha[1])

    def atualizar_desativado(self, id_registro, novo_dn, login) -> bool:
        if self.dry_run:
            return True
        usuario = self.usuarios.get(int(id_registro))
        if not usuario:
            return False
        usuario["TP_STATUS"] = int(StatusUsuario.DESLIGADO)
        usuario["USER_DN"] = normalizar_dn(novo_dn)
        self._tocar(usuario)
        return True

    # ------------------------------------------------------------ CPF na description
    def listar_candidatos_cpf_descricao(self, somente_desligados: bool):
        status = StatusUsuario.DESLIGADO if somente_desligados else StatusUsuario.ATIVO
        linhas = [
            (u["ID"], u["NM_COLABORADOR"].strip(), u["NM_LOGIN"].strip().lower(), u["NU_CPF_COLABORADOR"])
            for u in self.usuarios.values()
            if u["TP_STATUS"] == status and u["NU_CPF_COLABORADOR"] and u["NM_LOGIN"]
        ]
        return sorted(linhas, key=lambda linha: linha[1])

    def listar_ativos_com_cpf(self):
        linhas = [
            (u["ID"], u["NM_COLABORADOR"].strip(), u["NM_LOGIN"].strip(), u["NU_CPF_COLABORADOR"])
            for u in self.usuarios.values()
            if u["TP_STATUS"] == StatusUsuario.ATIVO and u["NU_CPF_COLABORADOR"]
        ]
        return sorted(linhas, key=lambda linha: linha[1])

    def atualizar_login(self, id_registro, cpf, login_novo) -> bool:
        if self.dry_run:
            return True
        usuario = self.usuarios.get(int(id_registro))
        if not usuario or usuario["NU_CPF_COLABORADOR"] != str(cpf):
            return False
        usuario["NM_LOGIN"] = login_novo
        self._tocar(usuario)
        return True

    # ------------------------------------------------------------ relatório
    def listar_criados_hoje(self):
        return [
            (u["NM_COLABORADOR"].strip(), u["NM_LOGIN"].lower(), u["NM_FUNCAO"], u["CENTRO_CUSTO"])
            for u in self.usuarios.values()
            if u["TP_STATUS"] == StatusUsuario.ATIVO and u["DT_ATUALIZACAO"] == date.today()
        ]
