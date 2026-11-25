# Rotinas manuais

Scripts de apoio que **não** fazem parte do ciclo diário (`main.py executar`). Servem para auditoria, saneamento pontual e manutenção.

Todas usam o mesmo `.env` do robô e respeitam `DRY_RUN`.

## validar_cpf_descricao_ad

Audita se os usuários ativos (`TP_STATUS = 1`) têm o CPF na `description` do AD.

- Só consulta banco e AD. **Não altera nada.**
- Classifica cada CPF em: encontrado, não encontrado, duplicado no AD ou encontrado em Desligados.
- No resumo final, devolve as listas prontas em formato SQL `IN (...)`, para investigar direto no banco.

## sincronizar_cpf_descricao

Preenche a `description` do usuário no AD com o CPF da tabela de controle. É o que torna possível a busca por CPF dos outros fluxos.

Regras de segurança:

- Localiza a conta pelo **login exato** e confere se o **nome no AD bate** com o da tabela (aceita nome truncado no AD, a partir de 10 caracteres).
- **Não sobrescreve** uma description que já tenha outro valor.
- Ignora contas que estão em Desligados (a não ser que a rotina rode no modo `somente_desligados`).
- Com `CPF_DESCRICAO_CORRIGIR_LOGIN=true`, se o login da tabela estiver errado e o nome tiver **um único** match no AD, corrige o `NM_LOGIN` na tabela.

## sincronizar_desligados

Audita quem está com `TP_STATUS = 2` e garante que esteja na OU de Desligados.

- Já em Desligados e com o `USER_DN` certo na tabela: só conta no resumo.
- Já em Desligados, mas com `USER_DN` diferente na tabela: corrige o banco.
- Fora de Desligados: desativa/move pela API e atualiza o banco.
- Bloqueia tudo se `AD_PASTA_DESLIGADOS` não estiver configurado.

## Como rodar

```bat
rotinas_manuais\validar_cpf_descricao_ad.bat
rotinas_manuais\sincronizar_cpf_descricao.bat
rotinas_manuais\sincronizar_desligados.bat
```
