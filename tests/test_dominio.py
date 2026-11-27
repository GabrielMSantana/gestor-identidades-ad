import pytest

from src.domain.dn import caminho_invalido, caminho_pai, extrair_cn, mesmo_dn, normalizar_cpf, normalizar_dn
from src.domain.senha import gerar_senha_temporaria


def test_normalizar_dn_deixa_cn_e_ou_em_minusculo():
    assert normalizar_dn("CN=Ana,OU=TI,DC=empresa") == "cn=Ana,ou=TI,DC=empresa"


def test_mesmo_dn_ignora_caixa_e_espacos():
    assert mesmo_dn("CN=Ana Lima, OU=TI,dc=empresa", "cn=ana lima,ou=ti,dc=empresa")
    assert not mesmo_dn("cn=Ana,ou=TI", "")


def test_extrair_cn_e_caminho_pai():
    dn = "cn=ANA LIMA,ou=Financeiro,dc=empresa,dc=local"
    assert extrair_cn(dn) == "ANA LIMA"
    assert caminho_pai(dn) == "ou=Financeiro,dc=empresa,dc=local"
    assert extrair_cn("sem-dn") == ""


def test_caminho_invalido():
    assert caminho_invalido("CENTRO_CUSTO INVALIDO")
    assert caminho_invalido("NAO POSSUI CAMINHO (FUNCAO GENERICA)")
    assert not caminho_invalido("cn=Ana,ou=TI")


def test_normalizar_cpf():
    assert normalizar_cpf("123.456.789-09") == "12345678909"
    assert normalizar_cpf(None) == ""


def test_senha_temporaria_atende_complexidade_e_varia():
    senhas = {gerar_senha_temporaria() for _ in range(50)}
    assert len(senhas) == 50
    for senha in senhas:
        assert len(senha) == 14
        assert any(c.isupper() for c in senha)
        assert any(c.islower() for c in senha)
        assert any(c.isdigit() for c in senha)
        assert any(not c.isalnum() for c in senha)


def test_senha_temporaria_curta_demais():
    with pytest.raises(ValueError):
        gerar_senha_temporaria(6)
