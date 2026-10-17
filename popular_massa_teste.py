from datetime import datetime, timedelta
import os
import random
import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

# Nomes próprios reais para o primeiro nome
primeiros_nomes = [
    'Ana', 'Carlos', 'Mariana', 'José', 'Juliana', 'Lucas', 'Fernanda', 'Marcos',
    'Camila', 'Bruno', 'Beatriz', 'Gabriel', 'Larissa', 'Rafael', 'Patrícia', 'Matheus',
    'Luciana', 'Rodrigo', 'Amanda', 'Felipe', 'Bruna', 'Thiago', 'Vanessa', 'Daniel',
    'Renata', 'Alexandre', 'Tatiane', 'Eduardo', 'Camila', 'Leandro', 'Simone', 'Diego'
]

# Sobrenomes inspirados em medicamentos e frutas (mantendo o toque original)
sobrenomes_fantasia = [
    'Paracetamol', 'Dipirona', 'Ibuprofeno', 'Omeprazol', 'Amoxicilina',
    'Losartana', 'Simvastatina', 'Metformina', 'Enalapril', 'Azitromicina',
    'Loratadina', 'Clonazepam', 'Banana', 'Morango', 'Abacaxi', 'Maracujá',
    'Melancia', 'Uva', 'Laranja', 'Acerola', 'Limão', 'Pera', 'Manga', 'Goiaba'
]

sexos = ['Feminino', 'Masculino']

# Novos CBOs para integrar na base se não existirem
novos_cbos = [
    {'codigo': '3222-05', 'ocupacao': 'Técnico de Enfermagem', 'min': 0, 'max': 120, 'conselho': 'COREN'},
    {'codigo': '4110-10', 'ocupacao': 'Assistente Administrativo', 'min': 18, 'max': 120, 'conselho': 'MTE'}
]

def gerar_cpf():
    n = [random.randint(0, 9) for _ in range(9)]
    s1 = sum(n[i] * (10 - i) for i in range(9))
    d1 = 11 - (s1 % 11)
    d1 = 0 if d1 >= 10 else d1
    n.append(d1)
    s2 = sum(n[i] * (11 - i) for i in range(10))
    d2 = 11 - (s2 % 11)
    d2 = 0 if d2 >= 10 else d2
    n.append(d2)
    return ''.join(map(str, n))

def gerar_sus():
    return ''.join([str(random.randint(0, 9)) for _ in range(15)])

def popular_massa():
    if not os.path.exists(DB_PATH):
        print('Erro: database.db não encontrado. Execute o init_db.py primeiro.')
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()

    # 1. Garantir inserção dos novos CBOs
    for cbo in novos_cbos:
        existe = cursor.execute('SELECT id FROM cbos WHERE codigo = ?', (cbo['codigo'],)).fetchone()
        if not existe:
            cursor.execute(
                """
                INSERT INTO cbos (codigo, ocupacao, profissao, idade_minima, idade_maxima, sigla_conselho, meses_assiduidade)
                VALUES (?, ?, ?, ?, ?, ?, 6)
                """,
                (cbo['codigo'], cbo['ocupacao'], cbo['ocupacao'], cbo['min'], cbo['max'], cbo['conselho'])
            )
    conn.commit()

    # Carregar estabelecimentos e CBOs atualizados
    estabelecimentos = [
        dict(row) for row in cursor.execute('SELECT id, nome FROM estabelecimentos WHERE ativo = 1').fetchall()
    ]
    cids = [dict(row) for row in cursor.execute('SELECT id FROM cids').fetchall()]
    cbos = [
        dict(row) for row in cursor.execute('SELECT id, ocupacao, idade_minima, idade_maxima, sigla_conselho FROM cbos').fetchall()
    ]

    if not estabelecimentos or not cbos:
        print('Erro: Unidades ou CBOs não encontrados no banco.')
        conn.close()
        return

    # 2. Criar 2 Profissionais (Nível I ou II) vinculados a CADA uma das unidades de saúde
    print('Criando 2 profissionais por unidade de saúde...')
    senha_padrao_hash = generate_password_hash('Senha123')
    perfis_possiveis = ['NIVEL_I', 'NIVEL_II']

    for est in estabelecimentos:
        for p_idx in range(1, 3):
            cbo_adequado = random.choice(cbos)
            nome_prof = f'{random.choice(primeiros_nomes)} {random.choice(sobrenomes_fantasia)}'
            cpf_prof = gerar_cpf()
            email_prof = f'prof.{est["id"]}.{p_idx}.{random.randint(100,999)}@saude.sp.gov.br'.lower()
            registro_prof = f'{random.randint(10000, 99999)}/{cbo_adequado["sigla_conselho"]}'
            perfil_escolhido = random.choice(perfis_possiveis)

            try:
                cursor.execute(
                    """
                    INSERT INTO profissionais (
                        nome, cpf, email, senha_hash, perfil, 
                        registro_profissional, permite_terceirizadas, ativo, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (nome_prof, cpf_prof, email_prof, senha_padrao_hash, perfil_escolhido, registro_prof)
                )
                prof_id = cursor.lastrowid
                
                # Criar vínculo na tabela profissional_unidades
                cursor.execute(
                    """
                    INSERT INTO profissional_unidades (profissional_id, estabelecimento_id, cbo_id, ativo)
                    VALUES (?, ?, ?, 1)
                    """,
                    (prof_id, est['id'], cbo_adequado['id'])
                )
            except Exception:
                pass

    conn.commit()

    # Buscar todos os profissionais criados para associar nas ações
    profissionais_cadastrados = [
        dict(row) for row in cursor.execute('SELECT id FROM profissionais WHERE ativo = 1').fetchall()
    ]

    if not profissionais_cadastrados:
        print('Erro: Nenhum profissional foi gerado.')
        conn.close()
        return

    # 3. Inserção de 1000 pacientes com nomes próprios e sobrenomes fantasiados
    print('Iniciando a inserção de 1000 pacientes...')
    novos_usuarios_ids = []

    for i in range(1, 1001):
        nome = f'{random.choice(primeiros_nomes)} {random.choice(sobrenomes_fantasia)} {random.choice(sobrenomes_fantasia)}'
        prontuario = f'P{7000 + i}'
        cpf = gerar_cpf()
        sus = gerar_sus()

        tipo_idade = random.choices(
            ['infantil', 'adolescente', 'adulto', 'idoso'], weights=[15, 20, 50, 15]
        )[0]
        ano_atual = datetime.now().year
        if tipo_idade == 'infantil':
            ano = random.randint(ano_atual - 9, ano_atual)
        elif tipo_idade == 'adolescente':
            ano = random.randint(ano_atual - 17, ano_atual - 10)
        elif tipo_idade == 'adulto':
            ano = random.randint(ano_atual - 59, ano_atual - 18)
        else:
            ano = random.randint(ano_atual - 90, ano_atual - 60)

        data_nasc = f"{ano}-{str(random.randint(1,12)).zfill(2)}-{str(random.randint(1,28)).zfill(2)}"
        sexo = random.choice(sexos)
        mae = f'{random.choice(primeiros_nomes)} da Silva {random.choice(sobrenomes_fantasia)}'
        tel1 = f"119{random.randint(40000000, 99999999)}"
        tel2 = f"119{random.randint(40000000, 99999999)}" if random.choice([True, False]) else ''
        est_id = random.choice(estabelecimentos)['id']
        prof_resp_id = random.choice(profissionais_cadastrados)['id']

        try:
            cursor.execute(
                """
                INSERT INTO usuarios (
                    numero_prontuario, nome, cpf, cartao_sus, data_nascimento, sexo, nome_mae,
                    telefone_principal, telefone_recado, unidade_referencia_id, 
                    criado_por_profissional_id, atualizado_por_profissional_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (prontuario, nome, cpf, sus, data_nasc, sexo, mae, tel1, tel2, est_id, prof_resp_id, prof_resp_id)
            )
            novos_usuarios_ids.append(cursor.lastrowid)
        except Exception:
            pass

    conn.commit()
    print(f'Sucesso! {len(novos_usuarios_ids)} pacientes cadastrados.')

    # 4. Inserção de 800 registros na Lista de Espera diversificados
    print('Iniciando a inserção de 800 registros na Lista de Espera...')
    todos_usuarios = [
        dict(row) for row in cursor.execute('SELECT id, data_nascimento FROM usuarios').fetchall()
    ]

    status_opcoes = ['Aguardando', 'Em Atendimento', 'Atendido / Finalizado', 'Cancelado / Desistência']
    pesos_status = [45, 25, 20, 10]
    niveis_servico = ['CAPS', 'AMBULATORIAL']

    inseridos_fila = 0
    tentativas = 0
    while inseridos_fila < 800 and tentativas < 4000 and todos_usuarios:
        tentativas += 1
        paciente = random.choice(todos_usuarios)
        nasc_str = paciente['data_nascimento']
        if not nasc_str:
            continue

        nasc_date = datetime.strptime(nasc_str.split()[0], '%Y-%m-%d')
        idade = (datetime.now() - nasc_date).days // 365

        cbos_compativeis = []
        for cbo in cbos:
            min_i = cbo['idade_minima'] if cbo['idade_minima'] is not None else 0
            max_i = cbo['idade_maxima'] if cbo['idade_maxima'] is not None else 150
            if min_i <= idade <= max_i:
                cbos_compativeis.append(cbo['ocupacao'])

        if not cbos_compativeis:
            continue

        modalidade = random.choice(cbos_compativeis)

        cursor.execute(
            "SELECT id FROM lista_espera WHERE usuario_id = ? AND modalidade_atendimento = ? AND status IN ('Aguardando', 'Em Atendimento')",
            (paciente['id'], modalidade)
        )
        if cursor.fetchone():
            continue

        est_solicitante = random.choice(estabelecimentos)['id']
        cid_id = random.choice(cids)['id'] if cids else None
        prof_sorteado_id = random.choice(profissionais_cadastrados)['id']
        status_atual = random.choices(status_opcoes, weights=pesos_status)[0]
        nivel_servico = random.choice(niveis_servico)

        dias_passados = random.randint(1, 400)
        data_entrada = (datetime.now() - timedelta(days=dias_passados)).strftime('%Y-%m-%d %H:%M:%S')

        try:
            cursor.execute(
                """
                INSERT INTO lista_espera (
                    usuario_id, profissional_triagem_id, profissional_atendimento_id, 
                    modalidade_atendimento, nivel_servico, unidade_solicitante_id, 
                    cid_id, status, data_entrada, observacao_atendimento
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    paciente['id'], prof_sorteado_id, prof_sorteado_id, 
                    modalidade, nivel_servico, est_solicitante, 
                    cid_id, status_atual, data_entrada, 
                    'Encaminhamento automatizado com diversificação de perfil.'
                )
            )
            inseridos_fila += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    print(f'Processo concluído com sucesso! {inseridos_fila} registros injetados na Lista de Espera.')

if __name__ == '__main__':
    popular_massa()