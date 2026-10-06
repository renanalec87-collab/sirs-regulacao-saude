from datetime import datetime, timedelta
import os
import random
import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

# Nomes fantasiados (Frutas e Remédios)
nomes_base = [
    'Paracetamol',
    'Dipirona',
    'Ibuprofeno',
    'Omeprazol',
    'Amoxicilina',
    'Losartana',
    'Simvastatina',
    'Metformina',
    'Enalapril',
    'Azitromicina',
    'Loratadina',
    'Clonazepam',
]
sobrenomes_fantasia = [
    'Banana',
    'Morango',
    'Abacaxi',
    'Maracujá',
    'Melancia',
    'Uva',
    'Laranja',
    'Acerola',
    'Limão',
    'Pera',
    'Manga',
    'Goiaba',
]
sexos = ['Feminino', 'Masculino']


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
    print(
        'Erro: database.db não encontrado. Execute o init_db.py primeiro para'
        ' criar a base.'
    )
    return

  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  conn.execute('PRAGMA foreign_keys = ON;')
  cursor = conn.cursor()

  # Carregar dados já existentes criados pelo init_db
  estabelecimentos = [
      dict(row)
      for row in cursor.execute(
          'SELECT id, nome FROM estabelecimentos WHERE ativo = 1'
      ).fetchall()
  ]
  cids = [
      dict(row) for row in cursor.execute('SELECT id FROM cids').fetchall()
  ]
  cbos = [
      dict(row)
      for row in cursor.execute(
          'SELECT id, ocupacao, idade_minima, idade_maxima, sigla_conselho FROM cbos'
      ).fetchall()
  ]

  if not estabelecimentos or not cbos:
    print('Erro: Unidades ou CBOs não encontrados no banco.')
    conn.close()
    return

  # 1. Criar 1 Profissional de Nível II para CADA uma das unidades de saúde
  print(
      'Criando 1 profissional de Nível II vinculado a cada unidade de saúde...'
  )
  senha_padrao_hash = generate_password_hash('Senha123')

  for est in estabelecimentos:
    cbo_adequado = random.choice(cbos)
    nome_prof = f'Dr(a). {random.choice(nomes_base)} {random.choice(sobrenomes_fantasia)}'
    cpf_prof = gerar_cpf()
    email_prof = f'prof.{est["id"]}.{random.randint(100,999)}@saude.sp.gov.br'.lower()
    registro_prof = f'{random.randint(10000, 99999)}/{cbo_adequado["sigla_conselho"]}'

    try:
      cursor.execute(
          """
                INSERT INTO profissionais (
                    nome, cpf, email, senha_hash, perfil, cbo_id, estabelecimento_id, 
                    registro_profissional, permite_terceirizadas, ativo, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'NIVEL_II', ?, ?, ?, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
          (
              nome_prof,
              cpf_prof,
              email_prof,
              senha_padrao_hash,
              cbo_adequado['id'],
              est['id'],
              registro_prof,
          ),
      )
    except Exception:
      pass

  conn.commit()

  profissionais_nivel_ii = [
      dict(row)
      for row in cursor.execute(
          "SELECT id FROM profissionais WHERE perfil = 'NIVEL_II'"
      ).fetchall()
  ]

  if not profissionais_nivel_ii:
    print('Erro: Nenhum profissional de Nível II foi gerado.')
    conn.close()
    return

  # 2. Inserção de 800 pacientes com nomes fantasiados
  print('Iniciando a inserção de 800 pacientes com nomes fantasiados...')
  novos_usuarios_ids = []
  prof_padrao_id = profissionais_nivel_ii[0]['id']

  for i in range(1, 801):
    nome = f'{random.choice(nomes_base)} {random.choice(sobrenomes_fantasia)} {random.choice(sobrenomes_fantasia)}'
    prontuario = f'F{5000 + i}'
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
    mae = f'{random.choice(nomes_base)} da Silva {random.choice(sobrenomes_fantasia)}'
    tel1 = f"119{random.randint(40000000, 99999999)}"
    tel2 = (
        f"119{random.randint(40000000, 99999999)}"
        if random.choice([True, False])
        else ''
    )
    est_id = random.choice(estabelecimentos)['id']

    try:
      cursor.execute(
          """
                INSERT INTO usuarios (
                    numero_prontuario, nome, cpf, cartao_sus, data_nascimento, sexo, nome_mae,
                    telefone_principal, telefone_recado, unidade_referencia_id, 
                    criado_por_profissional_id, atualizado_por_profissional_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
          (
              prontuario,
              nome,
              cpf,
              sus,
              data_nasc,
              sexo,
              mae,
              tel1,
              tel2,
              est_id,
              prof_padrao_id,
              prof_padrao_id,
          ),
      )
      novos_usuarios_ids.append(cursor.lastrowid)
    except Exception:
      pass

  conn.commit()
  print(f'Sucesso! {len(novos_usuarios_ids)} pacientes cadastrados.')

  # 3. Inserção de 600 registros na Lista de Espera compatíveis por idade
  print('Iniciando a inserção de 600 registros na Lista de Espera...')
  todos_usuarios = [
      dict(row)
      for row in cursor.execute(
          'SELECT id, data_nascimento FROM usuarios'
      ).fetchall()
  ]

  status_opcoes = [
      'Aguardando',
      'Em Atendimento',
      'Atendido / Finalizado',
      'Cancelado / Desistência',
  ]
  pesos_status = [50, 20, 20, 10]

  inseridos_fila = 0
  tentativas = 0
  while inseridos_fila < 600 and tentativas < 3000 and todos_usuarios:
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
        (paciente['id'], modalidade),
    )
    if cursor.fetchone():
      continue

    est_solicitante = random.choice(estabelecimentos)['id']
    cid_id = random.choice(cids)['id'] if cids else None
    prof_nivel_ii_id = random.choice(profissionais_nivel_ii)['id']
    status_atual = random.choices(status_opcoes, weights=pesos_status)[0]

    dias_passados = random.randint(1, 350)
    data_entrada = (
        datetime.now() - timedelta(days=dias_passados)
    ).strftime('%Y-%m-%d %H:%M:%S')

    try:
      cursor.execute(
          """
                INSERT INTO lista_espera (
                    usuario_id, profissional_triagem_id, profissional_atendimento_id, 
                    modalidade_atendimento, nivel_servico, unidade_solicitante_id, 
                    cid_id, status, data_entrada, observacao_atendimento
                ) VALUES (?, ?, ?, ?, 'CAPS', ?, ?, ?, ?, ?)
            """,
          (
              paciente['id'],
              prof_nivel_ii_id,
              prof_nivel_ii_id,
              modalidade,
              est_solicitante,
              cid_id,
              status_atual,
              data_entrada,
              'Encaminhamento gerado via massa automatizada (Nível II).',
          ),
      )
      inseridos_fila += 1
    except Exception:
      pass

  conn.commit()
  conn.close()
  print(
      f'Processo concluído com sucesso! {inseridos_fila} registros injetados'
      ' na Lista de Espera.'
  )


if __name__ == '__main__':
  popular_massa()