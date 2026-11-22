-- Versões SIMPLIFICADAS das procedures que alimentam o robô.
-- Servem para mostrar o contrato (o que cada uma devolve). As regras reais de
-- login, função genérica e afastamento são mais longas e ficam no banco.
-- O mesmo comportamento está simulado em Python no repositório em memória
-- (src/infrastructure/repositories/memoria_identidades_repository.py).

-- 1) Batimento: RH -> colaboradores ativos
CREATE OR ALTER PROCEDURE identidade.PROC_BATIMENTO_COLABORADORES
AS
BEGIN
    SET NOCOUNT ON;

    MERGE identidade.TB_COLABORADOR_ATIVO AS destino
    USING (
        SELECT NU_CPF, NM_FUNCIONARIO, ID_CENTRO_CUSTO, NM_CENTRO_CUSTO, NM_FUNCAO, DS_FUNCAO, FL_AFASTADO
        FROM rh.VW_FUNCIONARIO_ATIVO           -- view sobre o ERP
    ) AS origem
       ON destino.NU_CPF_COLABORADOR = origem.NU_CPF
    WHEN MATCHED THEN UPDATE SET
        NM_COLABORADOR  = origem.NM_FUNCIONARIO,
        ID_CENTRO_CUSTO = origem.ID_CENTRO_CUSTO,
        CENTRO_CUSTO    = origem.NM_CENTRO_CUSTO,
        NM_FUNCAO       = origem.NM_FUNCAO,
        DESC_FUNCAO     = origem.DS_FUNCAO,
        AFASTAMENTO     = origem.FL_AFASTADO,
        DT_ATUALIZACAO  = GETDATE()
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (NU_CPF_COLABORADOR, NM_COLABORADOR, ID_CENTRO_CUSTO, CENTRO_CUSTO, NM_FUNCAO, DESC_FUNCAO, AFASTAMENTO)
        VALUES (origem.NU_CPF, origem.NM_FUNCIONARIO, origem.ID_CENTRO_CUSTO, origem.NM_CENTRO_CUSTO,
                origem.NM_FUNCAO, origem.DS_FUNCAO, origem.FL_AFASTADO)
    WHEN NOT MATCHED BY SOURCE THEN DELETE;
END
GO

-- 2) Fila de criação: admitidos que ainda não estão na tabela de controle
CREATE OR ALTER PROCEDURE identidade.PROC_GERAR_FILA_CRIACAO
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO identidade.TB_USUARIO_AD
        (NM_COLABORADOR, NM_LOGIN, NU_CPF_COLABORADOR, ID_CENTRO_CUSTO, CENTRO_CUSTO, NM_FUNCAO, DESC_FUNCAO,
         USER_DN, GRUPO_DN, TP_STATUS)
    SELECT
        C.NM_COLABORADOR,
        -- primeiro.ultimo (a versão real trata acentos e logins repetidos)
        UPPER(LEFT(C.NM_COLABORADOR, CHARINDEX(' ', C.NM_COLABORADOR) - 1) + '.' +
              RIGHT(C.NM_COLABORADOR, CHARINDEX(' ', REVERSE(C.NM_COLABORADOR)) - 1)),
        C.NU_CPF_COLABORADOR, C.ID_CENTRO_CUSTO, C.CENTRO_CUSTO, C.NM_FUNCAO, C.DESC_FUNCAO,
        ISNULL('cn=' + C.NM_COLABORADOR + ',' + P.OU_DN, 'CENTRO_CUSTO INVALIDO'),
        ISNULL(P.GRUPO_DN, 'CENTRO_CUSTO INVALIDO'),
        0
    FROM identidade.TB_COLABORADOR_ATIVO AS C
    LEFT JOIN identidade.TB_CENTRO_CUSTO_AD AS P ON P.ID_CENTRO_CUSTO = C.ID_CENTRO_CUSTO
    WHERE NOT EXISTS (
        SELECT 1 FROM identidade.TB_USUARIO_AD AS U
        WHERE U.NU_CPF_COLABORADOR = C.NU_CPF_COLABORADOR AND U.TP_STATUS IN (0, 1)
    );
END
GO

-- 3) Desligamentos: ativo na tabela de controle, mas fora do RH
CREATE OR ALTER PROCEDURE identidade.PROC_LISTAR_DESLIGAMENTOS
AS
BEGIN
    SET NOCOUNT ON;

    SELECT U.ID, U.NM_COLABORADOR, U.NM_LOGIN, U.USER_DN, U.GRUPO_DN, U.NU_CPF_COLABORADOR
    FROM identidade.TB_USUARIO_AD AS U WITH (NOLOCK)
    WHERE U.TP_STATUS = 1
      AND NOT EXISTS (
          SELECT 1 FROM identidade.TB_COLABORADOR_ATIVO AS C WITH (NOLOCK)
          WHERE C.NU_CPF_COLABORADOR = U.NU_CPF_COLABORADOR
      );
END
GO

-- PROC_ATUALIZAR_CADASTRO e PROC_GERAR_FILA_MOVIMENTACAO seguem a mesma ideia:
-- comparam TB_COLABORADOR_ATIVO com TB_USUARIO_AD e devolvem/enfileiram só o que mudou
-- (nome diferente do CN -> renomear; OU ou grupo diferente -> mover).
