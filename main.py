"""Ponto de entrada.

    python main.py demo                  # ciclo completo sem AD e sem banco (dados falsos)
    python main.py demo --qtd 5000 -v    # cenário maior, com o log no console
    python main.py executar              # produção: ciclo diário (respeita DRY_RUN do .env)

Rotinas manuais (produção): pasta rotinas_manuais/.
"""
import argparse
import logging

from src.infrastructure.logger.logger_config import setup_logger


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestor de identidades: ciclo de vida de usuários no Active Directory")
    parser.add_argument("comando", choices=["demo", "executar"], nargs="?", default="executar")
    parser.add_argument("--qtd", type=int, default=1300, help="colaboradores no cenário da demo")
    parser.add_argument("--semente", type=int, default=42, help="semente do cenário da demo")
    parser.add_argument("-v", "--verbose", action="store_true", help="mostra o log da demo no console")
    args = parser.parse_args()

    if args.comando == "demo":
        from src.demo import executar_demo

        nivel = logging.INFO if args.verbose else logging.CRITICAL
        logger = setup_logger("demo", arquivo=None, console=True, nivel=nivel)
        executar_demo(quantidade=args.qtd, semente=args.semente, logger=logger)
        return

    from src.bootstrap import executar_producao

    logger = setup_logger()
    logger.info("==== Inicializando gestor de identidades AD ====")
    try:
        executar_producao(logger)
    except Exception as e:
        logger.error(f"Erro fatal no robo: {e}", exc_info=True)
    logger.info("==== Processo finalizado ====")


if __name__ == "__main__":
    main()
