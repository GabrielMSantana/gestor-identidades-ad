"""Senha temporária de novos usuários.

No sistema original a senha inicial seguia um padrão fixo derivado do nome.
Aqui ela é aleatória (módulo `secrets`) e atende à política de complexidade
padrão do AD: maiúscula, minúscula, número e símbolo.
"""
import secrets
import string

_SIMBOLOS = "@#$%&*!?"


def gerar_senha_temporaria(tamanho: int = 14) -> str:
    if tamanho < 8:
        raise ValueError("A senha temporaria precisa de pelo menos 8 caracteres.")

    obrigatorios = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(_SIMBOLOS),
    ]
    alfabeto = string.ascii_letters + string.digits + _SIMBOLOS
    resto = [secrets.choice(alfabeto) for _ in range(tamanho - len(obrigatorios))]

    caracteres = obrigatorios + resto
    secrets.SystemRandom().shuffle(caracteres)
    return "".join(caracteres)
