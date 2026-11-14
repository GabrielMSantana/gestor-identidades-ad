"""Situação do usuário na tabela de controle (coluna TP_STATUS)."""
from enum import IntEnum


class StatusUsuario(IntEnum):
    PENDENTE = 0   # na fila de criação
    ATIVO = 1      # criado no AD (ou já existia)
    DESLIGADO = 2  # desativado e movido para a OU de desligados
