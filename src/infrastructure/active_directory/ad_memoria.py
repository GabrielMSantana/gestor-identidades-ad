"""Active Directory em memória (demo e testes).

Simula o que importa para o robô: objetos de usuário com DN, login
(sAMAccountName), description (CPF), grupo (memberOf) e as respostas da API
interna no mesmo formato que os interpretadores esperam.
"""
import re
from dataclasses import dataclass, field

from src.domain.dn import caminho_pai, extrair_cn, normalizar_cpf, normalizar_dn, normalizar_para_comparar


@dataclass
class UsuarioAD:
    dn: str
    login: str
    nome: str
    description: str = ""
    grupos: list[str] = field(default_factory=list)
    ativo: bool = True

    def como_dict(self) -> dict[str, str]:
        return {
            "dn": self.dn,
            "login": self.login.lower(),
            "description": self.description,
            "displayName": self.nome,
            "cn": extrair_cn(self.dn),
            "name": extrair_cn(self.dn),
        }


class DiretorioADMemoria:
    def __init__(self, pasta_desligados: str, logger, dry_run: bool = False, grupo_desligados: str = ""):
        self.pasta_desligados = normalizar_dn(pasta_desligados)
        # Como no AD real: ao desativar, a conta entra num grupo que tira todas
        # as permissões (inclusive o login). Na readmissão, a sincronização
        # troca esse grupo pelo do cargo novo.
        self.grupo_desligados = normalizar_dn(grupo_desligados)
        self.logger = logger
        self.dry_run = dry_run
        self.usuarios: list[UsuarioAD] = []
        self.operacoes: list[tuple] = []  # (operacao, login) de cada escrita feita

    # ------------------------------------------------------------ montagem do cenário
    def adicionar(self, dn, login, nome, cpf="", grupo=None, ativo=True) -> UsuarioAD:
        usuario = UsuarioAD(normalizar_dn(dn), login.lower(), nome, cpf, [normalizar_dn(grupo)] if grupo else [], ativo)
        self.usuarios.append(usuario)
        return usuario

    def por_login(self, login) -> UsuarioAD | None:
        return next((u for u in self.usuarios if u.login == str(login).lower()), None)

    def snapshot(self):
        return sorted((u.dn, u.login, u.description, tuple(u.grupos), u.ativo) for u in self.usuarios)

    def _por_dn(self, dn) -> UsuarioAD | None:
        alvo = normalizar_para_comparar(dn)
        return next((u for u in self.usuarios if normalizar_para_comparar(u.dn) == alvo), None)

    def _bloqueado(self, acao):
        if self.dry_run:
            self.logger.info(f"[DRY_RUN] API AD desabilitada. {acao}")
            return {"status": "DRY_RUN"}
        return None

    # ------------------------------------------------------------ escrita (API)
    def criar(self, nmUsuario, sobreNome, displayName, nmLogon, senha, userDn, grupoDn, cpf):
        if (r := self._bloqueado(f"Criaria '{nmLogon}'.")):
            return r
        if self.por_login(nmLogon) or self._por_dn(userDn):
            return {"status": "erro", "erro": "entryAlreadyExists"}
        if len(senha or "") < 8:
            return {"status": "erro", "erro": "senha fora da politica"}
        self.adicionar(userDn, nmLogon, displayName, normalizar_cpf(cpf), grupoDn)
        self.operacoes.append(("criar", nmLogon.lower()))
        return {"status": "sucesso", "retorno": "Usuario criado"}

    def modificar(self, userDnAntigo, grupoDnAntigo, userDnNovo, grupoDnNovo):
        if (r := self._bloqueado(f"Moveria '{userDnAntigo}'.")):
            return r
        usuario = self._por_dn(userDnAntigo)
        if not usuario:
            return {"status": "erro", "erro": "noSuchObject"}
        usuario.dn = normalizar_dn(userDnNovo)
        usuario.grupos = [g for g in usuario.grupos if normalizar_para_comparar(g) != normalizar_para_comparar(grupoDnAntigo)]
        usuario.grupos.insert(0, normalizar_dn(grupoDnNovo))
        self.operacoes.append(("mover", usuario.login))
        return {"status": "sucesso", "mensagem": "Usuario movimentado"}

    def renomear(self, cpf, novoNome, userDnAtual=None):
        if (r := self._bloqueado(f"Renomearia CPF='{cpf}'.")):
            return r
        encontrados = [u for u in self.usuarios if u.description == normalizar_cpf(cpf)]
        if len(encontrados) != 1:
            return {"status": "erro", "erro": f"CPF retornou {len(encontrados)} usuarios"}
        usuario = encontrados[0]
        if extrair_cn(usuario.dn) == novoNome:
            return {"status": "ja estava com o nome correto", "novo_dn": usuario.dn}
        usuario.dn = f"cn={novoNome},{caminho_pai(usuario.dn)}"
        usuario.nome = novoNome
        self.operacoes.append(("renomear", usuario.login))
        return {"status": "sucesso", "novo_dn": usuario.dn}

    def desativar(self, userDn, cpf=None):
        if (r := self._bloqueado(f"Desativaria '{userDn}'.")):
            return r
        usuario = self._por_dn(userDn)
        if not usuario:
            return {"status": "error", "detalhe": "noSuchObject", "novo_dn_tentado": userDn}
        usuario.dn = f"cn={extrair_cn(usuario.dn)},{self.pasta_desligados}"
        usuario.grupos = [self.grupo_desligados] if self.grupo_desligados else []
        usuario.ativo = False
        self.operacoes.append(("desativar", usuario.login))
        return {"status": "success", "novo_dn": usuario.dn}

    # ------------------------------------------------------------ leitura (LDAP)
    def _mesmo_nome(self, usuario: UsuarioAD, nome) -> bool:
        alvo = str(nome or "").strip().lower()
        return alvo in (usuario.nome.lower(), extrair_cn(usuario.dn).lower())

    def buscar_multiplos_por_nome(self, nome):
        return [{"dn": u.dn, "login": u.login} for u in self.usuarios if self._mesmo_nome(u, nome)]

    def buscar_usuarios_por_nome_exato(self, nome):
        return [u.como_dict() for u in self.usuarios if self._mesmo_nome(u, nome)]

    def buscar_user_dn_por_login_exato(self, login):
        usuario = self.por_login(login)
        return usuario.dn if usuario else None

    def buscar_usuario_por_login_exato(self, login):
        usuario = self.por_login(login)
        return usuario.como_dict() if usuario else None

    def buscar_usuarios_por_cpf_descricao(self, cpf):
        cpf = normalizar_cpf(cpf)
        return [u.como_dict() for u in self.usuarios if cpf and u.description == cpf]

    def buscar_grupo_atual(self, dn_usuario):
        usuario = self._por_dn(dn_usuario)
        return usuario.grupos[0] if usuario and usuario.grupos else None

    def atualizar_descricao_usuario(self, dn_usuario, descricao):
        if self.dry_run:
            self.logger.info(f"[DRY_RUN] Atualizaria description de '{dn_usuario}' para '{descricao}'.")
            return True
        usuario = self._por_dn(dn_usuario)
        if not usuario:
            return False
        usuario.description = descricao
        self.operacoes.append(("description", usuario.login))
        return True

    def esta_em_desligados(self, dn_usuario):
        if not dn_usuario:
            return False
        return re.search(re.escape(self.pasta_desligados), dn_usuario, re.IGNORECASE) is not None
