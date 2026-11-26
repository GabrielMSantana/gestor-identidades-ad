"""RH falso: cadastro de colaboradores no lugar do ERP (TOTVS Protheus).

Também traz o organograma de exemplo (centro de custo -> OU e grupo do AD),
que no ambiente real é calculado pelas procedures a partir de tabelas de
parâmetro.
"""
import random
from dataclasses import dataclass, field

from src.domain.dn import CAMINHOS_INVALIDOS

BASE_DN = "dc=empresa,dc=local"
PASTA_DESLIGADOS = f"ou=Desligados,ou=Usuarios,{BASE_DN}"
GRUPO_DESLIGADOS = f"cn=GRP_DESATIVADOS,ou=Grupos,{BASE_DN}"


@dataclass
class Colaborador:
    cpf: str
    nome: str
    id_centro_custo: str
    centro_custo: str
    funcao: str
    ativo: bool = True
    afastamento: str = "N"

    @property
    def desc_funcao(self) -> str:
        return self.funcao.title()


@dataclass
class Organograma:
    """centro de custo -> (OU do usuário, grupo do AD)"""
    destinos: dict[str, tuple[str, str]] = field(default_factory=dict)

    def destino(self, id_centro_custo: str) -> tuple[str, str]:
        if id_centro_custo not in self.destinos:
            return CAMINHOS_INVALIDOS[0], CAMINHOS_INVALIDOS[0]
        return self.destinos[id_centro_custo]


AREAS = {
    "2101": "Financeiro",
    "2102": "Atendimento",
    "2103": "Operacoes",
    "2104": "Tecnologia",
    "2105": "Recursos Humanos",
    "2106": "Comercial",
    "2107": "Juridico",
    "2108": "Qualidade",
}

FUNCOES = ["ANALISTA", "ASSISTENTE", "OPERADOR", "SUPERVISOR", "COORDENADOR", "ESPECIALISTA"]


def organograma_exemplo() -> Organograma:
    destinos = {}
    for id_cc, area in AREAS.items():
        ou = f"ou={area},ou=Usuarios,{BASE_DN}"
        grupo = f"cn=GRP_{area.upper().replace(' ', '_')},ou=Grupos,{BASE_DN}"
        destinos[id_cc] = (ou, grupo)
    return Organograma(destinos)


class RHFalso:
    def __init__(self, colaboradores: list[Colaborador] | None = None):
        self.colaboradores: dict[str, Colaborador] = {c.cpf: c for c in (colaboradores or [])}

    def adicionar(self, colaborador: Colaborador) -> Colaborador:
        self.colaboradores[colaborador.cpf] = colaborador
        return colaborador

    def ativos(self) -> list[Colaborador]:
        return [c for c in self.colaboradores.values() if c.ativo]


# ---------------------------------------------------------------- dados falsos

_PRIMEIROS = [
    "ANA", "BRUNO", "CARLA", "DANIEL", "EDUARDO", "FERNANDA", "GABRIELA", "HELENA", "IGOR", "JULIANA",
    "KAIQUE", "LARISSA", "MARCOS", "NATALIA", "OTAVIO", "PAULA", "RAFAEL", "SABRINA", "TIAGO", "VANESSA",
    "WAGNER", "YASMIN", "LUCAS", "MARIANA", "PEDRO", "BEATRIZ", "RENATO", "CAMILA", "DIEGO", "LETICIA",
]
_MEIOS = ["", "", "APARECIDA", "CRISTINA", "HENRIQUE", "AUGUSTO", "LUIZA", "VITOR", "ROBERTA", "MIGUEL"]
_SOBRENOMES = [
    "SILVA", "SANTOS", "OLIVEIRA", "SOUZA", "RODRIGUES", "FERREIRA", "ALVES", "PEREIRA", "LIMA", "GOMES",
    "COSTA", "RIBEIRO", "MARTINS", "CARVALHO", "ALMEIDA", "LOPES", "SOARES", "VIEIRA", "BARBOSA", "ROCHA",
    "DIAS", "NASCIMENTO", "ANDRADE", "MOREIRA", "NUNES", "MARQUES", "MACHADO", "MENDES", "FREITAS", "CARDOSO",
]


def gerar_cpf(rng: random.Random) -> str:
    """CPF fictício com dígitos verificadores válidos."""
    numeros = [rng.randint(0, 9) for _ in range(9)]
    for _ in range(2):
        soma = sum(n * p for n, p in zip(numeros, range(len(numeros) + 1, 1, -1), strict=True))
        numeros.append((soma * 10 % 11) % 10)
    return "".join(map(str, numeros))


def gerar_nome(rng: random.Random) -> str:
    partes = [rng.choice(_PRIMEIROS), rng.choice(_MEIOS), rng.choice(_SOBRENOMES), rng.choice(_SOBRENOMES)]
    return " ".join(p for p in partes if p)


def gerar_colaboradores(quantidade: int, rng: random.Random, centros: list[str] | None = None) -> list[Colaborador]:
    centros = centros or list(AREAS)
    nomes, cpfs, colaboradores = set(), set(), []
    while len(colaboradores) < quantidade:
        nome, cpf = gerar_nome(rng), gerar_cpf(rng)
        if nome in nomes or cpf in cpfs:
            continue
        nomes.add(nome)
        cpfs.add(cpf)
        id_cc = rng.choice(centros)
        colaboradores.append(Colaborador(cpf, nome, id_cc, AREAS.get(id_cc, "SEM AREA"), rng.choice(FUNCOES)))
    return colaboradores
