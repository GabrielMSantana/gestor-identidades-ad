# Modo seguro operacional (DRY_RUN)

As flags abaixo começaram como medida de proteção durante o desenvolvimento e viraram recurso **permanente** do robô: mexer em contas de ~1.300 pessoas sem poder simular antes é arriscado demais.

## As duas flags

| Flag | O que faz |
|---|---|
| `DRY_RUN=true` | Calcula tudo e registra no log o que faria, mas **não chama a API do AD, não grava description e não faz UPDATE** nas tabelas. |
| `DRY_RUN_EXECUTE_PROCS=true` | Com `DRY_RUN=true`, as procedures que montam as filas (batimento, fila de criação, atualização cadastral, fila de movimentação) **continuam rodando**. Assim a simulação usa os candidatos reais de hoje. |

## Combinações

| DRY_RUN | DRY_RUN_EXECUTE_PROCS | Uso |
|---|---|---|
| `true` | `true` | **Simulação recomendada**: filas reais, nenhuma ação final. |
| `true` | `false` | Mais conservador: nem as procedures rodam. Serve para validar conexões e o fluxo geral. |
| `false` | `true` | Execução real. |

## Onde o DRY_RUN é checado

Em **duas camadas**, de propósito:

1. **Casos de uso:** antes de chamar a API do AD (`[DRY_RUN] Moveria...`, `[DRY_RUN] Criaria...`).
2. **Repositórios (SQL e memória) e AD:** antes de qualquer `UPDATE` ou escrita de description. Se um fluxo novo esquecer a checagem, o repositório ainda bloqueia.

Os testes cobrem as duas: `test_dry_run_no_repositorio_sql_nao_executa_update` e os testes `*_dry_run_*` de cada fluxo. A demo confere que o AD fica idêntico depois da simulação.

## Checklist antes de uma execução real depois de mudanças

- Rodar pelo menos um ciclo completo com `DRY_RUN=true` e ler o log.
- Conferir uma amostra de candidatos a criação, movimentação, sincronização e desativação.
- Validar que os retornos da API estão sendo interpretados corretamente.
- Validar a renovação do token.
- Fazer a primeira execução real em janela acompanhada e conferir uma amostra no AD e nas tabelas.
- Voltar para `DRY_RUN=true` ao começar uma nova rodada de desenvolvimento.

## Rotinas manuais

- `validar_cpf_descricao_ad`: só auditoria, nunca altera nada.
- `sincronizar_cpf_descricao`: respeita `DRY_RUN` (description no AD e `NM_LOGIN` no banco).
- `sincronizar_desligados`: respeita `DRY_RUN` (move para Desligados e atualiza o banco).
