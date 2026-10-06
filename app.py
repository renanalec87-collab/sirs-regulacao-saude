from datetime import datetime, timedelta
from functools import wraps
import os
import random
import sqlite3
import unicodedata
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get(
    'SECRET_KEY', 'caps_ii_sao_roque_secret_key_local_dev_only'
)

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
ALLOWED_EXTENSIONS_PDF = {'pdf'}
ALLOWED_EXTENSIONS_IMG = {'png', 'jpg', 'jpeg', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def allowed_file(filename, allowed_set):
  return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set


# --- CONEXÃO COM O BANCO DE DADOS ---
def get_db_connection():
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  conn.execute('PRAGMA foreign_keys = ON;')
  return conn


# --- GARANTE AS COLUNAS DE AUDITORIA NAS TABELAS ---
def garantir_colunas_auditoria():
  conn = get_db_connection()
  cursor = conn.cursor()

  cols_prof = [
      col['name']
      for col in cursor.execute('PRAGMA table_info(profissionais)').fetchall()
  ]
  if 'criado_por_profissional_id' not in cols_prof:
    cursor.execute(
        'ALTER TABLE profissionais ADD COLUMN criado_por_profissional_id INTEGER'
    )
  if 'atualizado_por_profissional_id' not in cols_prof:
    cursor.execute(
        'ALTER TABLE profissionais ADD COLUMN'
        ' atualizado_por_profissional_id INTEGER'
    )
  if 'created_at' not in cols_prof:
    cursor.execute('ALTER TABLE profissionais ADD COLUMN created_at TIMESTAMP')
  if 'updated_at' not in cols_prof:
    cursor.execute('ALTER TABLE profissionais ADD COLUMN updated_at TIMESTAMP')

  cols_estab = [
      col['name']
      for col in cursor.execute('PRAGMA table_info(estabelecimentos)').fetchall()
  ]
  if 'criado_por_profissional_id' not in cols_estab:
    cursor.execute(
        'ALTER TABLE estabelecimentos ADD COLUMN'
        ' criado_por_profissional_id INTEGER'
    )
  if 'atualizado_por_profissional_id' not in cols_estab:
    cursor.execute(
        'ALTER TABLE estabelecimentos ADD COLUMN'
        ' atualizado_por_profissional_id INTEGER'
    )
  if 'created_at' not in cols_estab:
    cursor.execute('ALTER TABLE estabelecimentos ADD COLUMN created_at TIMESTAMP')
  if 'updated_at' not in cols_estab:
    cursor.execute(
        'ALTER TABLE estabelecimentos ADD COLUMN updated_at TIMESTAMP'
    )

  conn.commit()
  conn.close()


with app.app_context():
  garantir_colunas_auditoria()


# --- FILTROS DE FORMATAÇÃO DE DOCUMENTOS (JINJA2) ---
def formatar_cpf(cpf_limpo):
  if not cpf_limpo or len(str(cpf_limpo)) != 11:
    return cpf_limpo or ''
  cpf = str(cpf_limpo)
  return f'{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}'


def formatar_cartao_sus(sus_limpo):
  if not sus_limpo or len(str(sus_limpo)) != 15:
    return sus_limpo or ''
  sus = str(sus_limpo)
  return f'{sus[:3]} {sus[3:7]} {sus[7:11]} {sus[11:]}'


app.jinja_env.filters['cpf'] = formatar_cpf
app.jinja_env.filters['cartao_sus'] = formatar_cartao_sus


def padronizar_nome_proprio(texto):
  if not texto:
    return ''
  texto_normalizado = (
      unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
  )
  palavras = texto_normalizado.strip().title().split()
  preposicoes = {'De', 'Da', 'Do', 'Das', 'Dos', 'E'}
  resultado = []
  for index, palavra in enumerate(palavras):
    if index > 0 and palavra in preposicoes:
      resultado.append(palavra.lower())
    else:
      resultado.append(palavra)
  return ' '.join(resultado)


def login_required(f):
  @wraps(f)
  def decorated_function(*args, **kwargs):
    if 'usuario_id' not in session:
      flash('Por favor, faça login para acessar o sistema.', 'warning')
      return redirect(url_for('login'))
    return f(*args, **kwargs)

  return decorated_function


def nivel_i_required(f):
  @wraps(f)
  def decorated_function(*args, **kwargs):
    if session.get('perfil') != 'NIVEL_I':
      flash(
          'Acesso restrito à gestão e administração do sistema (Nível I).',
          'danger',
      )
      return redirect(url_for('dashboard'))
    return f(*args, **kwargs)

  return decorated_function


def nivel_ii_required(f):
  @wraps(f)
  def decorated_function(*args, **kwargs):
    if session.get('perfil') not in ['NIVEL_I', 'NIVEL_II']:
      flash('Ação restrita à equipe técnica/atendimento (Nível I e II).', 'warning')
      return redirect(url_for('dashboard'))
    return f(*args, **kwargs)

  return decorated_function


@app.route('/')
def index():
  if 'usuario_id' in session:
    return redirect(url_for('dashboard'))
  return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
  hoje_str = datetime.now().strftime('%Y-%m-%d')
  conn = get_db_connection()
  cursor = conn.cursor()

  campanhas = [
      dict(row)
      for row in cursor.execute(
          """
        SELECT * FROM campanhas_avisos 
        WHERE ativo = 1 AND ? BETWEEN data_inicio AND data_fim
        ORDER BY id DESC
        LIMIT 6
    """,
          (hoje_str,),
      ).fetchall()
  ]
  conn.close()

  if request.method == 'POST':
    login_input = request.form.get('login', '').strip()
    login_limpo = ''.join(filter(str.isdigit, login_input))
    senha = request.form.get('senha', '')

    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
            SELECT p.*, c.ocupacao, c.sigla_conselho, e.nome AS estabelecimento_nome, e.tipo AS estabelecimento_tipo
            FROM profissionais p
            JOIN cbos c ON p.cbo_id = c.id
            JOIN estabelecimentos e ON p.estabelecimento_id = e.id
            WHERE (p.cpf = ? OR p.cpf = ? OR p.email = ?) AND p.ativo = 1
        """
    cursor.execute(query, (login_input, login_limpo, login_input))
    profissional = cursor.fetchone()
    conn.close()

    if profissional and check_password_hash(profissional['senha_hash'], senha):
      session['usuario_id'] = profissional['id']
      session['nome'] = profissional['nome']
      session['perfil'] = profissional['perfil']
      session['permite_terceirizadas'] = profissional['permite_terceirizadas']
      session['ocupacao'] = profissional['ocupacao']
      session['sigla_conselho'] = profissional['sigla_conselho'] or ''
      session['registro_profissional'] = (
          profissional['registro_profissional'] or ''
      )
      session['estabelecimento'] = profissional['estabelecimento_nome']
      session['estabelecimento_id'] = profissional['estabelecimento_id']
      session['estabelecimento_tipo'] = profissional['estabelecimento_tipo']

      flash('Login efetuado com sucesso!', 'success')
      return redirect(url_for('dashboard'))
    else:
      flash('CPF/E-mail ou senha incorretos.', 'danger')

  return render_template('login.html', campanhas=campanhas)


@app.route('/logout')
def logout():
  session.clear()
  flash('Sessão encerrada com sucesso.', 'info')
  return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
  conn = get_db_connection()
  cursor = conn.cursor()
  estabelecimentos = [
      dict(row)
      for row in cursor.execute(
          'SELECT id, nome, tipo FROM estabelecimentos WHERE ativo = 1 ORDER BY'
          ' nome ASC'
      ).fetchall()
  ]
  cids = [
      dict(row)
      for row in cursor.execute(
          'SELECT id, codigo, descricao, versao FROM cids ORDER BY versao DESC,'
          ' codigo ASC'
      ).fetchall()
  ]
  cbos = [
      dict(row)
      for row in cursor.execute(
          'SELECT id, ocupacao, idade_minima, idade_maxima FROM cbos ORDER BY'
          ' ocupacao ASC'
      ).fetchall()
  ]
  conn.close()
  return render_template(
      'dashboard.html',
      estabelecimentos=estabelecimentos,
      cids=cids,
      cbos=cbos,
  )


# --- API DE BUSCA DE PACIENTE COM PAGINAÇÃO (50 REGISTROS) ---
@app.route('/api/paciente/buscar', methods=['GET'])
@login_required
def buscar_paciente():
  termo_doc = request.args.get('doc', '').strip() or request.args.get(
      'q', ''
  ).strip()
  termo_nome = request.args.get('nome', '').strip()
  page = int(request.args.get('page', 1))
  per_page = 50
  offset = (page - 1) * per_page

  conn = get_db_connection()
  cursor = conn.cursor()

  query_count = 'SELECT COUNT(DISTINCT u.id) FROM usuarios u WHERE 1=1'
  filtro_sql = ''
  params = []

  if termo_doc:
    doc_limpo = ''.join(filter(str.isdigit, termo_doc))
    if doc_limpo:
      filtro_sql += (
          ' AND (u.cpf LIKE ? OR u.cartao_sus LIKE ? OR u.numero_prontuario'
          ' LIKE ?)'
      )
      params.extend([f'%{doc_limpo}%', f'%{doc_limpo}%', f'%{doc_limpo}%'])
    else:
      palavras_doc = termo_doc.split()
      for palavra in palavras_doc:
        filtro_sql += ' AND (u.nome LIKE ? OR u.numero_prontuario LIKE ?)'
        params.extend([f'%{palavra}%', f'%{palavra}%'])

  if termo_nome:
    palavras = termo_nome.split()
    for palavra in palavras:
      filtro_sql += ' AND (u.nome LIKE ? OR u.nome_mae LIKE ?)'
      params.extend([f'%{palavra}%', f'%{palavra}%'])

  cursor.execute(query_count + filtro_sql, params)
  total_registros = cursor.fetchone()[0]
  total_paginas = (
      (total_registros + per_page - 1) // per_page
      if total_registros > 0
      else 1
  )

  query = """
        SELECT DISTINCT u.*, 
               e.nome AS unidade_referencia_nome,
               p_criou.nome AS criado_por_nome,
               p_at.nome AS atualizado_por_nome
        FROM usuarios u
        LEFT JOIN estabelecimentos e ON u.unidade_referencia_id = e.id
        LEFT JOIN profissionais p_criou ON u.criado_por_profissional_id = p_criou.id
        LEFT JOIN profissionais p_at ON u.atualizado_por_profissional_id = p_at.id
        WHERE 1=1
    """
  query += filtro_sql + ' ORDER BY u.nome ASC LIMIT ? OFFSET ?'
  params_query = params + [per_page, offset]

  cursor.execute(query, params_query)
  resultados = cursor.fetchall()
  conn.close()

  pacientes = [
      {
          'id': row['id'],
          'numero_prontuario': row['numero_prontuario'] or 'Não informado',
          'nome': row['nome'],
          'cpf': row['cpf'],
          'cpf_formatado': formatar_cpf(row['cpf']),
          'cartao_sus': row['cartao_sus'],
          'cartao_sus_formatado': formatar_cartao_sus(row['cartao_sus']),
          'data_nascimento': row['data_nascimento'],
          'sexo': row['sexo'],
          'nome_mae': row['nome_mae'],
          'telefone_principal': row['telefone_principal'],
          'telefone_recado': row['telefone_recado'],
          'unidade_referencia_id': row['unidade_referencia_id'],
          'unidade_referencia_nome': (
              row['unidade_referencia_nome'] or 'Não Informada'
          ),
          'created_at': row['created_at'],
          'criado_por_nome': row['criado_por_nome'] or 'Sistema',
          'updated_at': row['updated_at'],
          'atualizado_por_nome': row['atualizado_por_nome'] or 'Sistema',
      }
      for row in resultados
  ]

  if pacientes:
    return jsonify({
        'sucesso': True,
        'encontrado': True,
        'dados': pacientes,
        'pagina_atual': page,
        'total_paginas': total_paginas,
        'total_registros': total_registros,
    })
  else:
    return jsonify({
        'sucesso': True,
        'encontrado': False,
        'mensagem': 'Nenhum paciente encontrado com os critérios informados.',
    })


@app.route('/paciente/salvar', methods=['POST'])
@login_required
def salvar_paciente():
  paciente_id = request.form.get('id')
  perfil_usuario = session.get('perfil')

  if perfil_usuario == 'NIVEL_III':
    flash(
        'Acesso negado: Usuários de Nível III possuem apenas permissão de'
        ' consulta.',
        'danger',
    )
    return redirect(url_for('dashboard'))

  telefone_principal = request.form.get('telefone_principal', '').strip()
  telefone_recado = request.form.get('telefone_recado', '').strip()

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    numero_prontuario = request.form.get('numero_prontuario', '').strip()
    nome = padronizar_nome_proprio(request.form.get('nome', ''))
    nome_mae = padronizar_nome_proprio(request.form.get('nome_mae', ''))
    cpf = ''.join(filter(str.isdigit, request.form.get('cpf', '')))
    cartao_sus = ''.join(filter(str.isdigit, request.form.get('cartao_sus', '')))
    data_nascimento = request.form.get('data_nascimento')
    sexo = request.form.get('sexo')
    unidade_referencia_id = request.form.get('unidade_referencia_id')

    if paciente_id:
      query = """
                UPDATE usuarios SET
                    numero_prontuario = ?, nome = ?, cpf = ?, cartao_sus = ?, data_nascimento = ?, sexo = ?,
                    nome_mae = ?, telefone_principal = ?, telefone_recado = ?,
                    unidade_referencia_id = ?, atualizado_por_profissional_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
      cursor.execute(
          query,
          (
              numero_prontuario or None,
              nome,
              cpf or None,
              cartao_sus or None,
              data_nascimento,
              sexo,
              nome_mae,
              telefone_principal,
              telefone_recado,
              unidade_referencia_id or None,
              session['usuario_id'],
              paciente_id,
          ),
      )
      flash('Cadastro do paciente atualizado com sucesso!', 'success')
    else:
      query = """
                INSERT INTO usuarios (
                    numero_prontuario, nome, cpf, cartao_sus, data_nascimento, sexo, nome_mae,
                    telefone_principal, telefone_recado, unidade_referencia_id,
                    criado_por_profissional_id, atualizado_por_profissional_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
      cursor.execute(
          query,
          (
              numero_prontuario or None,
              nome,
              cpf or None,
              cartao_sus or None,
              data_nascimento,
              sexo,
              nome_mae,
              telefone_principal,
              telefone_recado,
              unidade_referencia_id or None,
              session['usuario_id'],
              session['usuario_id'],
          ),
      )
      flash('Novo paciente cadastrado com sucesso!', 'success')

    conn.commit()
  except sqlite3.IntegrityError:
    conn.rollback()
    flash(
        'Erro: Já existe um paciente cadastrado com este CPF, Cartão SUS ou Nº'
        ' de Prontuário.',
        'danger',
    )
  except Exception as e:
    conn.rollback()
    flash(f'Erro ao salvar paciente: {str(e)}', 'danger')
  finally:
    conn.close()

  return redirect(url_for('dashboard'))


@app.route('/api/paciente/<int:usuario_id>/historico', methods=['GET'])
@login_required
def api_historico_paciente(usuario_id):
  conn = get_db_connection()
  cursor = conn.cursor()

  query = """
        SELECT le.modalidade_atendimento, le.status, le.data_entrada, le.data_atualizacao, c.meses_assiduidade
        FROM lista_espera le
        LEFT JOIN cbos c ON c.ocupacao = le.modalidade_atendimento
        WHERE le.usuario_id = ?
        ORDER BY le.data_entrada DESC
    """
  cursor.execute(query, (usuario_id,))
  registros = cursor.fetchall()
  conn.close()

  hoje = datetime.now()
  historico_formatado = []

  for r in registros:
    meses_param = (
        r['meses_assiduidade'] if r['meses_assiduidade'] is not None else 6
    )
    assiduo = False

    status_fila = r['status']
    if status_fila in ['Atendido / Finalizado']:
      status_exibicao = 'Concluída'
    elif status_fila in ['Cancelado / Desistência']:
      status_exibicao = 'Cancelada'
    else:
      status_exibicao = 'Em andamento'

    if status_exibicao == 'Em andamento' and r['data_atualizacao']:
      try:
        dt_atualizacao = datetime.strptime(
            r['data_atualizacao'].split('.')[0], '%Y-%m-%d %H:%M:%S'
        )
        diferenca_dias = (hoje - dt_atualizacao).days
        if diferenca_dias <= (meses_param * 30):
          assiduo = True
      except:
        pass

    historico_formatado.append({
        'especialidade': r['modalidade_atendimento'],
        'status': status_exibicao,
        'data_inicio': r['data_entrada'] or '-',
        'meses_parametro': meses_param,
        'assiduo': assiduo,
    })

  return jsonify({'sucesso': True, 'historico': historico_formatado})


@app.route('/lista-espera/inserir', methods=['POST'])
@login_required
@nivel_ii_required
def inserir_lista_espera():
  usuario_id = request.form.get('usuario_id')
  modalidade = request.form.get('modalidade_atendimento')
  unidade_solicitante_id = session.get(
      'estabelecimento_id'
  ) or request.form.get('unidade_solicitante_id')

  if not unidade_solicitante_id:
    flash(
        'Erro: Unidade solicitante não identificada na sessão. Faça login'
        ' novamente.',
        'danger',
    )
    return redirect(url_for('dashboard'))

  cid_id = request.form.get('cid_id')
  observacao = request.form.get('observacao_atendimento', '').strip()

  conn = get_db_connection()
  cursor = conn.cursor()
  try:
    cursor.execute(
        """
            SELECT id, data_entrada FROM lista_espera 
            WHERE usuario_id = ? AND modalidade_atendimento = ? AND status IN ('Aguardando', 'Em Atendimento')
        """,
        (usuario_id, modalidade),
    )
    if cursor.fetchone():
      flash(
          'Bloqueio: Paciente já possui uma solicitação ativa para esta'
          ' modalidade.',
          'warning',
      )
      return redirect(url_for('dashboard'))

    nivel_servico = 'CAPS'
    cursor.execute(
        'SELECT tipo FROM estabelecimentos WHERE id = ?',
        (unidade_solicitante_id,),
    )
    est_info = cursor.fetchone()
    if est_info and est_info['tipo'] not in [
        'CAPS',
        'Centro de Atenção Psicossocial',
    ]:
      nivel_servico = 'AMBULATORIAL'

    cursor.execute(
        """
            INSERT INTO lista_espera (usuario_id, profissional_triagem_id, modalidade_atendimento, nivel_servico, unidade_solicitante_id, cid_id, observacao_atendimento, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Aguardando')
        """,
        (
            usuario_id,
            session['usuario_id'],
            modalidade,
            nivel_servico,
            unidade_solicitante_id,
            cid_id or None,
            observacao,
        ),
    )
    conn.commit()
    flash('Paciente inserido na Lista de Espera com sucesso!', 'success')
  except Exception as e:
    conn.rollback()
    flash(f'Erro ao inserir na lista de espera: {str(e)}', 'danger')
  finally:
    conn.close()
  return redirect(url_for('ver_lista_espera'))


@app.route('/lista-espera/atualizar-status', methods=['POST'])
@login_required
@nivel_ii_required
def atualizar_status_lista():
  lista_id = request.form.get('lista_id')
  novo_status = request.form.get('status')
  conn = get_db_connection()
  cursor = conn.cursor()
  row_atual = cursor.execute(
      'SELECT status, nivel_servico FROM lista_espera WHERE id = ?', (lista_id,)
  ).fetchone()

  if row_atual and row_atual['status'] in [
      'Atendido / Finalizado',
      'Cancelado / Desistência',
  ]:
    conn.close()
    flash('Erro: Esta solicitação já foi encerrada.', 'danger')
    return redirect(url_for('ver_lista_espera'))

  nivel_servico = (
      row_atual['nivel_servico']
      if session.get('perfil') == 'NIVEL_II'
      else (request.form.get('nivel_servico') or 'CAPS')
  )
  desfecho_triagem = request.form.get('desfecho_triagem', '').strip()

  try:
    cursor.execute(
        """
            UPDATE lista_espera SET status = ?, nivel_servico = ?, desfecho_triagem = ?, profissional_atendimento_id = ?, data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
        (
            novo_status,
            nivel_servico,
            desfecho_triagem or None,
            session['usuario_id'],
            lista_id,
        ),
    )
    conn.commit()
    flash('Status atualizado com sucesso!', 'success')
  except Exception as e:
    conn.rollback()
    flash(f'Erro ao atualizar status: {str(e)}', 'danger')
  finally:
    conn.close()
  return redirect(url_for('ver_lista_espera'))


@app.route('/guias-fluxo')
@login_required
def guias_fluxo():
  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute('SELECT * FROM guias_fluxos WHERE ativo = 1 ORDER BY titulo ASC')
  guias_raw = cursor.fetchall()
  guias = []
  for g in guias_raw:
    guia_dict = dict(g)
    cursor.execute('SELECT * FROM guias_anexos WHERE guia_id = ?', (g['id'],))
    guia_dict['anexos'] = [dict(a) for a in cursor.fetchall()]
    guias.append(guia_dict)
  conn.close()
  return render_template('guias_fluxo.html', guias=guias)


@app.route('/admin/profissionais', methods=['GET'])
@login_required
@nivel_i_required
def listar_profissionais():
  conn = get_db_connection()
  cursor = conn.cursor()
  profissionais = [
      dict(row)
      for row in cursor.execute("""
        SELECT p.*, 
               c.ocupacao AS cbo_ocupacao, 
               c.sigla_conselho AS cbo_conselho, 
               e.nome AS estabelecimento_nome,
               p_criou.nome AS criado_por_nome,
               p_at.nome AS atualizado_por_nome
        FROM profissionais p 
        JOIN cbos c ON p.cbo_id = c.id 
        JOIN estabelecimentos e ON p.estabelecimento_id = e.id
        LEFT JOIN profissionais p_criou ON p.criado_por_profissional_id = p_criou.id
        LEFT JOIN profissionais p_at ON p.atualizado_por_profissional_id = p_at.id
        ORDER BY p.nome ASC
    """).fetchall()
  ]
  cbos = [
      dict(row)
      for row in cursor.execute(
          'SELECT id, codigo, ocupacao, sigla_conselho FROM cbos ORDER BY'
          ' ocupacao ASC'
      ).fetchall()
  ]
  estabelecimentos = [
      dict(row)
      for row in cursor.execute(
          'SELECT id, nome FROM estabelecimentos WHERE ativo = 1 ORDER BY nome'
          ' ASC'
      ).fetchall()
  ]
  conn.close()
  return render_template(
      'admin_profissionais.html',
      profissionais=profissionais,
      cbos=cbos,
      estabelecimentos=estabelecimentos,
  )


@app.route('/admin/profissionais/salvar', methods=['POST'])
@login_required
@nivel_i_required
def salvar_profissional():
  profissional_id = request.form.get('id')
  nome = padronizar_nome_proprio(request.form.get('nome', ''))
  cpf = ''.join(filter(str.isdigit, request.form.get('cpf', '')))
  email = request.form.get('email', '').strip().lower()
  senha = request.form.get('senha', '')

  if senha:
    qtd_letras = sum(1 for c in senha if c.isalpha())
    if len(senha) != 8 or qtd_letras < 3:
      flash(
          'Erro: A senha deve ter exatamente 8 caracteres e conter pelo menos 3'
          ' letras.',
          'danger',
      )
      return redirect(url_for('listar_profissionais'))

  perfil = request.form.get('perfil', 'NIVEL_II')
  cbo_id = request.form.get('cbo_id')
  estabelecimento_id = request.form.get('estabelecimento_id')
  registro_profissional = request.form.get('registro_profissional', '').strip()
  permite_terceirizadas = (
      1 if request.form.get('permite_terceirizadas') == 'on' else 0
  )
  ativo = 1 if request.form.get('ativo', '1') == '1' else 0
  usuario_logado_id = session.get('usuario_id')

  conn = get_db_connection()
  cursor = conn.cursor()
  try:
    if profissional_id:
      if senha:
        senha_hash = generate_password_hash(senha)
        cursor.execute(
            """
                    UPDATE profissionais 
                    SET nome = ?, cpf = ?, email = ?, senha_hash = ?, perfil = ?, cbo_id = ?, 
                        estabelecimento_id = ?, registro_profissional = ?, permite_terceirizadas = ?, 
                        ativo = ?, atualizado_por_profissional_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
            (
                nome,
                cpf,
                email,
                senha_hash,
                perfil,
                cbo_id,
                estabelecimento_id,
                registro_profissional or None,
                permite_terceirizadas,
                ativo,
                usuario_logado_id,
                profissional_id,
            ),
        )
      else:
        cursor.execute(
            """
                    UPDATE profissionais 
                    SET nome = ?, cpf = ?, email = ?, perfil = ?, cbo_id = ?, 
                        estabelecimento_id = ?, registro_profissional = ?, permite_terceirizadas = ?, 
                        ativo = ?, atualizado_por_profissional_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
            (
                nome,
                cpf,
                email,
                perfil,
                cbo_id,
                estabelecimento_id,
                registro_profissional or None,
                permite_terceirizadas,
                ativo,
                usuario_logado_id,
                profissional_id,
            ),
        )
      flash('Profissional atualizado com sucesso!', 'success')
    else:
      if not senha:
        flash('Erro: A senha é obrigatória.', 'danger')
        return redirect(url_for('listar_profissionais'))
      senha_hash = generate_password_hash(senha)
      cursor.execute(
          """
                INSERT INTO profissionais (
                    nome, cpf, email, senha_hash, perfil, cbo_id, estabelecimento_id, 
                    registro_profissional, permite_terceirizadas, ativo, 
                    criado_por_profissional_id, atualizado_por_profissional_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
          (
              nome,
              cpf,
              email,
              senha_hash,
              perfil,
              cbo_id,
              estabelecimento_id,
              registro_profissional or None,
              permite_terceirizadas,
              ativo,
              usuario_logado_id,
              usuario_logado_id,
          ),
      )
      flash('Profissional cadastrado com sucesso!', 'success')
    conn.commit()
  except sqlite3.IntegrityError:
    conn.rollback()
    flash('Erro: CPF ou E-mail já cadastrado.', 'danger')
  except Exception as e:
    conn.rollback()
    flash(f'Erro: {str(e)}', 'danger')
  finally:
    conn.close()
  return redirect(url_for('listar_profissionais'))


@app.route('/admin/estabelecimentos', methods=['GET'])
@login_required
@nivel_i_required
def listar_estabelecimentos():
  conn = get_db_connection()
  cursor = conn.cursor()
  estabelecimentos = [
      dict(row)
      for row in cursor.execute("""
        SELECT e.*, 
               p_criou.nome AS criado_por_nome,
               p_at.nome AS atualizado_por_nome
        FROM estabelecimentos e
        LEFT JOIN profissionais p_criou ON e.criado_por_profissional_id = p_criou.id
        LEFT JOIN profissionais p_at ON e.atualizado_por_profissional_id = p_at.id
        ORDER BY e.nome ASC
    """).fetchall()
  ]
  conn.close()
  return render_template(
      'admin_estabelecimentos.html', estabelecimentos=estabelecimentos
  )


@app.route('/admin/estabelecimentos/salvar', methods=['POST'])
@login_required
@nivel_i_required
def salvar_estabelecimento():
  estab_id = request.form.get('id')
  cnes = request.form.get('cnes', '').strip()
  nome = request.form.get('nome', '').strip()
  tipo = request.form.get('tipo', 'UBS')
  ativo = 1 if request.form.get('ativo', '1') == '1' else 0
  usuario_logado_id = session.get('usuario_id')

  conn = get_db_connection()
  cursor = conn.cursor()
  try:
    if estab_id:
      cursor.execute(
          """
                UPDATE estabelecimentos 
                SET cnes = ?, nome = ?, tipo = ?, ativo = ?, 
                    atualizado_por_profissional_id = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """,
          (cnes or None, nome, tipo, ativo, usuario_logado_id, estab_id),
      )
      flash('Unidade atualizada com sucesso!', 'success')
    else:
      cursor.execute(
          """
                INSERT INTO estabelecimentos (
                    cnes, nome, tipo, ativo, 
                    criado_por_profissional_id, atualizado_por_profissional_id, created_at, updated_at
                ) 
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
          (
              cnes or None,
              nome,
              tipo,
              ativo,
              usuario_logado_id,
              usuario_logado_id,
          ),
      )
      flash('Unidade cadastrada com sucesso!', 'success')
    conn.commit()
  except sqlite3.IntegrityError:
    conn.rollback()
    flash('Erro: CNES já cadastrado.', 'danger')
  except Exception as e:
    conn.rollback()
    flash(f'Erro: {str(e)}', 'danger')
  finally:
    conn.close()
  return redirect(url_for('listar_estabelecimentos'))


@app.route('/relatorios', methods=['GET'])
@login_required
@nivel_i_required
def relatorios():
  data_inicio = request.args.get('data_inicio', '').strip()
  data_fim = request.args.get('data_fim', '').strip()
  unidade_filtro = request.args.get('unidade_filtro', '').strip()
  modalidade_filtro = request.args.get('modalidade_filtro', '').strip()

  conn = get_db_connection()
  cursor = conn.cursor()

  if unidade_filtro:
    query_pacientes_unidade = """
            SELECT COUNT(DISTINCT u.id) 
            FROM usuarios u
            JOIN lista_espera le ON le.usuario_id = u.id
            WHERE le.unidade_solicitante_id = ?
        """
    params_pacientes = [unidade_filtro]
    if data_inicio and data_fim:
      query_pacientes_unidade += ' AND le.data_entrada BETWEEN ? AND ?'
      params_pacientes.extend([data_inicio, data_fim + ' 23:59:59'])
    total_pacientes = cursor.execute(
        query_pacientes_unidade, params_pacientes
    ).fetchone()[0]
  else:
    total_pacientes = cursor.execute('SELECT COUNT(*) FROM usuarios').fetchone()[0]

  query_status = 'SELECT status, COUNT(*) AS quantidade FROM lista_espera WHERE 1=1'
  query_unidade = """
        SELECT 
            e.nome AS unidade,
            SUM(CASE WHEN le.status = 'Aguardando' THEN 1 ELSE 0 END) AS aguardando,
            SUM(CASE WHEN le.status = 'Em Atendimento' THEN 1 ELSE 0 END) AS em_atendimento,
            SUM(CASE WHEN le.status = 'Atendido / Finalizado' THEN 1 ELSE 0 END) AS atendido,
            SUM(CASE WHEN le.status = 'Cancelado / Desistência' THEN 1 ELSE 0 END) AS cancelado,
            COUNT(le.id) AS total
        FROM estabelecimentos e
        LEFT JOIN lista_espera le ON le.unidade_solicitante_id = e.id
    """
  query_modalidade = (
      'SELECT modalidade_atendimento, COUNT(*) AS quantidade FROM lista_espera'
      ' WHERE 1=1'
  )

  params = []
  params_unidade = []

  if data_inicio and data_fim:
    query_status += ' AND data_entrada BETWEEN ? AND ?'
    query_modalidade += ' AND data_entrada BETWEEN ? AND ?'
    query_unidade += (
        ' AND (le.data_entrada BETWEEN ? AND ? OR le.data_entrada IS NULL)'
    )
    params.extend([data_inicio, data_fim + ' 23:59:59'])
    params_unidade.extend([data_inicio, data_fim + ' 23:59:59'])

  if unidade_filtro:
    query_status += ' AND unidade_solicitante_id = ?'
    query_modalidade += ' AND unidade_solicitante_id = ?'
    query_unidade += ' AND e.id = ?'
    params.append(unidade_filtro)
    params_unidade.append(unidade_filtro)
  else:
    query_unidade += ' WHERE e.ativo = 1'

  if modalidade_filtro:
    query_status += ' AND modalidade_atendimento = ?'
    query_modalidade += ' AND modalidade_atendimento = ?'
    query_unidade += ' AND le.modalidade_atendimento = ?'
    params.append(modalidade_filtro)
    params_unidade.append(modalidade_filtro)

  query_status += ' GROUP BY status'
  query_unidade += ' GROUP BY e.id, e.nome ORDER BY total DESC'
  query_modalidade += ' GROUP BY modalidade_atendimento ORDER BY quantidade DESC'

  cursor.execute(query_status, params)
  status_counts = [dict(row) for row in cursor.fetchall()]

  cursor.execute(query_unidade, params_unidade if params_unidade else [])
  unidade_counts = [dict(row) for row in cursor.fetchall()]

  cursor.execute(query_modalidade, params)
  modalidade_counts = [dict(row) for row in cursor.fetchall()]

  total_geral_filtrado = sum([r['quantidade'] for r in status_counts])

  estabelecimentos = [
      dict(row)
      for row in cursor.execute(
          'SELECT id, nome FROM estabelecimentos WHERE ativo = 1 ORDER BY nome'
          ' ASC'
      ).fetchall()
  ]
  modalidades = [
      row['modalidade_atendimento']
      for row in cursor.execute(
          'SELECT DISTINCT modalidade_atendimento FROM lista_espera ORDER BY'
          ' modalidade_atendimento ASC'
      ).fetchall()
  ]
  conn.close()

  return render_template(
      'relatorios.html',
      status_counts=status_counts,
      unidade_counts=unidade_counts,
      modalidade_counts=modalidade_counts,
      total_pacientes=total_pacientes,
      total_geral_filtrado=total_geral_filtrado,
      data_inicio=data_inicio,
      data_fim=data_fim,
      unidade_filtro=unidade_filtro,
      modalidade_filtro=modalidade_filtro,
      estabelecimentos=estabelecimentos,
      modalidades=modalidades,
  )

# Rota Mapa
@app.route('/api/relatorios/mapa', methods=['GET'])
@login_required
@nivel_i_required
def api_relatorios_mapa():
    modalidade = request.args.get('modalidade', 'todos')
    status = request.args.get('status', 'Aguardando')

    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT e.nome AS unidade, e.id AS unidade_id, COUNT(le.id) AS total
        FROM estabelecimentos e
        LEFT JOIN lista_espera le ON le.unidade_solicitante_id = e.id AND le.status = ?
    """
    params = [status]

    if modalidade != 'todos':
        query += ' AND le.modalidade_atendimento = ?'
        params.append(modalidade)

    query += ' GROUP BY e.id, e.nome'
    dados = [dict(row) for row in cursor.execute(query, params).fetchall()]
    conn.close()

    # Coordenadas fixas distribuídas para os bairros e unidades de São Roque - SP
    coordenadas_fixas = {
        '192 - RESGATE': [-23.5320, -47.1350],             # Avenida Bernardino de Lucca, Jd. Carambei
        'CENTRAL DE REGULACAO': [-23.5320, -47.1335],      # Avenida John Kennedy, 509
        'CANGUERA': [-23.6042, -47.1633],                  # Rua Sorocabana, 601
        'CAPS II': [-23.5300, -47.1320],                   # Rua Alfredo Salvetti, 91
        'CAPS II-AD': [-23.5312, -47.1350],                   # Rua Santa Isabel, 46
        'CARMO': [-23.5360, -47.1400],                     # Bairro do Carmo
        'CENTRAL - ESPECIALIDADES': [-23.5318, -47.1345],  # Rua Santana, 349
        'CENTRAL - IRIS BARIONI': [-23.5340, -47.1360],    # Rua Prof. Fernando de Lima, 70
        'CENTRAL DE REGULACAO': [-23.5320, -47.1335],      # Avenida John Kennedy, 509
        'CENTRO DE SAUDE II': [-23.5320, -47.1335],        # Avenida John Kennedy, 509
        'DEPARTAMENTO DE SAUDE': [-23.5505, -47.1260],     # Rua São Paulo, 966 (Taboão)
        'FARMACIA CENTRAL': [-23.5300, -47.1320],          # Rua Alfredo Salvetti, 91
        'GOIANA': [-23.5450, -47.1050],                    # Rua Martin Afonso de Sousa, Paisagem Colonial
        'GUACU': [-23.5180, -47.1250],                     # Avenida Bernardino de Lucca, Jd. Carambei
        'HOSPITAL SANTA CASA': [-23.5295, -47.1415],       # Rua Santa Isabel, 1586
        'MAYLASKY': [-23.5561, -47.0900],                  # Rua Antônio Sartori, Mailasque
        'MAYLASKY-ESPECIALIDADES': [-23.5570, -47.0905],   # Rua Benedicta dos Santos Caparelli, Mailasque
        'SABOO': [-23.4747, -47.1626],                     # Estrada do Saboó
        'SAO JOAO NOVO': [-23.5395, -47.2140],             # Rua José Benedito Rodrigues, São João Novo
        'SISO': [-23.5315, -47.1350],                      # Avenida Antonino Dias Bastos, 157
        'TABOAO': [-23.5500, -47.1250],                    # Avenida São Luis, 118
        'VILA NOVA': [-23.5240, -47.1430],                 # Rua Jaboticabal, 604
        'VILLAGGIO EMILIA': [-23.5450, -47.1500]           # Rua das Papoulas, Vila Santa Rosália
    }

    resultado_final = []
    for d in dados:
        nome_est = d['unidade'].strip().upper()
        
        # Procura a coordenada correspondente ou usa o centro como padrão se não encontrar
        coords = [-23.5325, -47.1353]
        for chave, latlng in coordenadas_fixas.items():
            if chave in nome_est:
                coords = latlng
                break

        resultado_final.append({
            'unidade': d['unidade'],
            'total': d['total'],
            'lat': coords[0],
            'lng': coords[1]
        })

    return jsonify({'sucesso': True, 'dados': resultado_final})

@app.route('/admin/configuracoes')
@login_required
@nivel_i_required
def admin_configuracoes():
  return render_template('admin_configuracoes.html')


@app.route('/admin/configuracoes/assiduidade', methods=['GET'])
@login_required
@nivel_i_required
def listar_assiduidade_config():
  conn = get_db_connection()
  cbos = [
      dict(row)
      for row in conn.execute(
          'SELECT id, ocupacao, meses_assiduidade FROM cbos ORDER BY ocupacao'
          ' ASC'
      ).fetchall()
  ]
  conn.close()
  return render_template('admin_assiduidade.html', cbos=cbos)


@app.route('/admin/configuracoes/assiduidade/salvar', methods=['POST'])
@login_required
@nivel_i_required
def salvar_assiduidade_config():
  cbo_id = request.form.get('cbo_id')
  meses = (
      int(request.form.get('meses_assiduidade'))
      if request.form.get('meses_assiduidade', '').isdigit()
      else 6
  )

  conn = get_db_connection()
  cursor = conn.cursor()
  try:
    cursor.execute(
        'UPDATE cbos SET meses_assiduidade = ? WHERE id = ?', (meses, cbo_id)
    )
    conn.commit()
    flash('Parâmetro de assiduidade atualizado com sucesso!', 'success')
  except Exception as e:
    conn.rollback()
    flash(f'Erro ao atualizar assiduidade: {str(e)}', 'danger')
  finally:
    conn.close()
  return redirect(url_for('listar_assiduidade_config'))


@app.route('/admin/configuracoes/cids', methods=['GET'])
@login_required
@nivel_i_required
def listar_cids():
  conn = get_db_connection()
  cids = [
      dict(row)
      for row in conn.execute(
          'SELECT * FROM cids ORDER BY versao DESC, codigo ASC'
      ).fetchall()
  ]
  conn.close()
  return render_template('admin_cids.html', cids=cids)


@app.route('/admin/configuracoes/cid/salvar', methods=['POST'])
@login_required
@nivel_i_required
def salvar_cid():
  cid_id = request.form.get('id')
  codigo = request.form.get('codigo', '').strip().upper()
  descricao = request.form.get('descricao', '').strip()
  versao = request.form.get('versao', 'CID-10').strip()

  conn = get_db_connection()
  cursor = conn.cursor()
  try:
    if cid_id:
      cursor.execute(
          'UPDATE cids SET codigo = ?, descricao = ?, versao = ? WHERE id = ?',
          (codigo, descricao, versao, cid_id),
      )
      flash('CID atualizado com sucesso!', 'success')
    else:
      duplicado = cursor.execute(
          'SELECT id FROM cids WHERE codigo = ? AND versao = ?',
          (codigo, versao),
      ).fetchone()
      if duplicado:
        flash(f'Erro: O código {codigo} ({versao}) já está cadastrado.', 'danger')
      else:
        cursor.execute(
            'INSERT INTO cids (codigo, descricao, versao) VALUES (?, ?, ?)',
            (codigo, descricao, versao),
        )
        flash('Novo CID cadastrado com sucesso!', 'success')
    conn.commit()
  except Exception as e:
    conn.rollback()
    flash(f'Erro ao salvar CID: {str(e)}', 'danger')
  finally:
    conn.close()
  return redirect(url_for('listar_cids'))


@app.route('/admin/configuracoes/cbos', methods=['GET'])
@login_required
@nivel_i_required
def listar_cbos():
  conn = get_db_connection()
  cbos = [
      dict(row)
      for row in conn.execute('SELECT * FROM cbos ORDER BY ocupacao ASC').fetchall()
  ]
  conn.close()
  return render_template('admin_cbos.html', cbos=cbos)


@app.route('/admin/configuracoes/cbo/salvar', methods=['POST'])
@login_required
@nivel_i_required
def salvar_cbo():
  cbo_id = request.form.get('id')
  codigo = request.form.get('codigo', '').strip()
  ocupacao = request.form.get('ocupacao', '').strip()
  idade_minima = (
      int(request.form.get('idade_minima'))
      if request.form.get('idade_minima', '').isdigit()
      else None
  )
  idade_maxima = (
      int(request.form.get('idade_maxima'))
      if request.form.get('idade_maxima', '').isdigit()
      else None
  )
  conselho = request.form.get('conselho', '').strip().upper()

  conn = get_db_connection()
  cursor = conn.cursor()
  try:
    if cbo_id:
      cursor.execute(
          """UPDATE cbos SET codigo = ?, ocupacao = ?, profissao = ?,
          idade_minima = ?, idade_maxima = ?, sigla_conselho = ? WHERE id = ?""",
          (codigo, ocupacao, ocupacao, idade_minima, idade_maxima, conselho, cbo_id),
      )
      flash('Especialidade atualizada!', 'success')
    else:
      cursor.execute(
          """INSERT INTO cbos (codigo, ocupacao, profissao, idade_minima,
          idade_maxima, sigla_conselho) VALUES (?, ?, ?, ?, ?, ?)""",
          (codigo, ocupacao, ocupacao, idade_minima, idade_maxima, conselho),
      )
      flash('Especialidade cadastrada!', 'success')
    conn.commit()
  finally:
    conn.close()
  return redirect(url_for('listar_cbos'))


@app.route('/admin/configuracoes/cbo/excluir/<int:cbo_id>', methods=['POST', 'GET'])
@login_required
@nivel_i_required
def excluir_cbo(cbo_id):
  conn = get_db_connection()
  cursor = conn.cursor()
  try:
    vinculados = cursor.execute(
        'SELECT COUNT(*) FROM profissionais WHERE cbo_id = ?', (cbo_id,)
    ).fetchone()[0]

    if vinculados > 0:
      flash(
          'Erro: Não é possível excluir esta Especialidade/CBO pois existem'
          ' profissionais vinculados a ela.',
          'danger',
      )
    else:
      cursor.execute('DELETE FROM cbos WHERE id = ?', (cbo_id,))
      conn.commit()
      flash('Especialidade/CBO excluída com sucesso!', 'success')
  except Exception as e:
    conn.rollback()
    flash(f'Erro ao excluir CBO: {str(e)}', 'danger')
  finally:
    conn.close()
  return redirect(url_for('listar_cbos'))


@app.route('/admin/configuracoes/campanhas', methods=['GET'])
@login_required
@nivel_i_required
def admin_campanhas():
  conn = get_db_connection()
  campanhas = [
      dict(row)
      for row in conn.execute(
          'SELECT * FROM campanhas_avisos ORDER BY data_inicio DESC'
      ).fetchall()
  ]
  conn.close()
  return render_template('admin_avisos_e_campanhas.html', campanhas=campanhas)


@app.route('/admin/configuracoes/campanhas/salvar', methods=['POST'])
@login_required
@nivel_i_required
def salvar_campanha():
  campanha_id = request.form.get('id')
  titulo = request.form.get('titulo', '').strip()
  data_inicio = request.form.get('data_inicio')
  data_fim = request.form.get('data_fim')
  descricao_texto = request.form.get('descricao_texto', '').strip()
  ativo = 1 if request.form.get('ativo', '1') == '1' else 0

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    arquivo_path_db = None
    if 'arquivo' in request.files:
      file = request.files['arquivo']
      if file and file.filename != '' and (
          allowed_file(file.filename, ALLOWED_EXTENSIONS_IMG)
          or allowed_file(file.filename, ALLOWED_EXTENSIONS_PDF)
      ):
        filename = secure_filename(file.filename)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        file.save(os.path.join(UPLOAD_FOLDER, filename))
        arquivo_path_db = f'uploads/{filename}'

    if campanha_id:
      if arquivo_path_db:
        cursor.execute(
            """
                    UPDATE campanhas_avisos 
                    SET titulo = ?, data_inicio = ?, data_fim = ?, arquivo_path = ?, descricao_texto = ?, ativo = ?
                    WHERE id = ?
                """,
            (
                titulo,
                data_inicio,
                data_fim,
                arquivo_path_db,
                descricao_texto or None,
                ativo,
                campanha_id,
            ),
        )
      else:
        cursor.execute(
            """
                    UPDATE campanhas_avisos 
                    SET titulo = ?, data_inicio = ?, data_fim = ?, descricao_texto = ?, ativo = ?
                    WHERE id = ?
                """,
            (
                titulo,
                data_inicio,
                data_fim,
                descricao_texto or None,
                ativo,
                campanha_id,
            ),
        )
      flash('Campanha / Aviso atualizado com sucesso!', 'success')
    else:
      cursor.execute(
          """
                INSERT INTO campanhas_avisos (titulo, data_inicio, data_fim, arquivo_path, descricao_texto, ativo)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
          (
              titulo,
              data_inicio,
              data_fim,
              arquivo_path_db,
              descricao_texto or None,
              ativo,
          ),
      )
      flash('Nova campanha / aviso cadastrado com sucesso!', 'success')
    conn.commit()
  except Exception as e:
    conn.rollback()
    flash(f'Erro ao salvar campanha: {str(e)}', 'danger')
  finally:
    conn.close()
  return redirect(url_for('admin_campanhas'))


@app.route('/admin/configuracoes/guias', methods=['GET'])
@login_required
@nivel_i_required
def admin_guias():
  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute('SELECT * FROM guias_fluxos WHERE ativo = 1 ORDER BY id DESC')
  guias_raw = cursor.fetchall()
  guias = []
  for g in guias_raw:
    guia_dict = dict(g)
    cursor.execute('SELECT * FROM guias_anexos WHERE guia_id = ?', (g['id'],))
    guia_dict['anexos'] = [dict(a) for a in cursor.fetchall()]
    guias.append(guia_dict)
  conn.close()
  return render_template('admin_guias.html', guias=guias)


@app.route('/admin/configuracoes/guias/salvar', methods=['POST'])
@login_required
@nivel_i_required
def salvar_guia():
  guia_id = request.form.get('id')
  titulo_interno = request.form.get('titulo_interno', '').strip()
  titulo = request.form.get('titulo', '').strip()
  categoria = request.form.get('categoria', '').strip()
  ativo = 1 if request.form.get('ativo', '1') == '1' else 0
  descricao_resumida = request.form.get('descricao_resumida', '').strip()
  conteudo_orientacao = request.form.get('conteudo_orientacao', '').strip()

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    logo_path_db = None
    if 'logo_file' in request.files:
      file_logo = request.files['logo_file']
      if (
          file_logo
          and file_logo.filename != ''
          and allowed_file(file_logo.filename, ALLOWED_EXTENSIONS_IMG)
      ):
        filename_logo = secure_filename(file_logo.filename)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        file_logo.save(os.path.join(UPLOAD_FOLDER, filename_logo))
        logo_path_db = f'uploads/{filename_logo}'

    if guia_id:
      if logo_path_db:
        cursor.execute(
            """
                    UPDATE guias_fluxos 
                    SET titulo_interno = ?, titulo = ?, categoria = ?, ativo = ?, 
                        descricao_resumida = ?, conteudo_orientacao = ?, logo_path = ? 
                    WHERE id = ?
                """,
            (
                titulo_interno,
                titulo,
                categoria,
                ativo,
                descricao_resumida,
                conteudo_orientacao,
                logo_path_db,
                guia_id,
            ),
        )
      else:
        cursor.execute(
            """
                    UPDATE guias_fluxos 
                    SET titulo_interno = ?, titulo = ?, categoria = ?, ativo = ?, 
                        descricao_resumida = ?, conteudo_orientacao = ? 
                    WHERE id = ?
                """,
            (
                titulo_interno,
                titulo,
                categoria,
                ativo,
                descricao_resumida,
                conteudo_orientacao,
                guia_id,
            ),
        )
      id_alvo = guia_id
      flash('Guia atualizado com sucesso!', 'success')
    else:
      cursor.execute(
          """
                INSERT INTO guias_fluxos (titulo_interno, titulo, categoria, ativo, descricao_resumida, conteudo_orientacao, logo_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
          (
              titulo_interno,
              titulo,
              categoria,
              ativo,
              descricao_resumida,
              conteudo_orientacao,
              logo_path_db,
          ),
      )
      id_alvo = cursor.execute('SELECT last_insert_rowid()').fetchone()[0]
      flash('Guia cadastrado com sucesso!', 'success')

    if 'pdf_files' in request.files:
      files_pdf = request.files.getlist('pdf_files')
      nomes_pdf = request.form.getlist('pdf_nomes[]')

      for index, file_pdf in enumerate(files_pdf):
        if (
            file_pdf
            and file_pdf.filename != ''
            and allowed_file(file_pdf.filename, ALLOWED_EXTENSIONS_PDF)
        ):
          filename_pdf = secure_filename(file_pdf.filename)
          os.makedirs(UPLOAD_FOLDER, exist_ok=True)
          file_pdf.save(os.path.join(UPLOAD_FOLDER, filename_pdf))
          pdf_path_db = f'uploads/{filename_pdf}'

          nome_anexo = (
              nomes_pdf[index]
              if index < len(nomes_pdf) and nomes_pdf[index].strip()
              else file_pdf.filename
          )
          cursor.execute(
              """
                        INSERT INTO guias_anexos (guia_id, nome_arquivo, pdf_path)
                        VALUES (?, ?, ?)
                    """,
              (id_alvo, nome_anexo, pdf_path_db),
          )

    conn.commit()
  except Exception as e:
    conn.rollback()
    flash(f'Erro ao salvar guia: {str(e)}', 'danger')
  finally:
    conn.close()

  return redirect(url_for('admin_guias'))

@app.route('/admin/configuracoes/guias/excluir/<int:guia_id>', methods=['POST', 'GET'])
@login_required
@nivel_i_required
def excluir_guia(guia_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM guias_anexos WHERE guia_id = ?', (guia_id,))
        cursor.execute('DELETE FROM guias_fluxos WHERE id = ?', (guia_id,))
        conn.commit()
        flash('Guia e seus anexos excluídos com sucesso!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Erro ao excluir guia: {str(e)}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('admin_guias'))


@app.route('/admin/configuracoes/guias/anexo/excluir/<int:anexo_id>', methods=['GET', 'POST'])
@login_required
@nivel_i_required
def excluir_anexo_pdf(anexo_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM guias_anexos WHERE id = ?', (anexo_id,))
        conn.commit()
        flash('Arquivo PDF excluído com sucesso!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Erro ao excluir anexo PDF: {str(e)}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('admin_guias'))


# --- ROTA DE LISTA DE ESPERA COM PAGINAÇÃO (50 REGISTROS) ---
@app.route('/lista-espera')
@login_required
def ver_lista_espera():
  conn = get_db_connection()
  cursor = conn.cursor()

  filtrado = request.args.get('filtrado') == '1'
  cpf_filtro = request.args.get('cpf', '').strip()
  modalidade_filtro = request.args.get('modalidade', '').strip()
  status_filtro = request.args.get('status_filtro', 'ativos').strip()

  page = int(request.args.get('page', 1))
  per_page = 50
  offset = (page - 1) * per_page

  atendimentos = []
  total_paginas = 1
  total_registros = 0

  if filtrado:
    query_base_where = ' WHERE 1=1'
    params = []

    if cpf_filtro:
      cpf_limpo = ''.join(filter(str.isdigit, cpf_filtro))
      query_base_where += ' AND u.cpf LIKE ?'
      params.append(f'%{cpf_limpo}%')

    if modalidade_filtro:
      query_base_where += ' AND le.modalidade_atendimento = ?'
      params.append(modalidade_filtro)

    if status_filtro == 'ativos':
      query_base_where += " AND le.status IN ('Aguardando', 'Em Atendimento')"
    elif status_filtro == 'todos':
      pass
    elif status_filtro in [
        'Aguardando',
        'Em Atendimento',
        'Atendido / Finalizado',
        'Cancelado / Desistência',
    ]:
      query_base_where += ' AND le.status = ?'
      params.append(status_filtro)

    query_count = (
        'SELECT COUNT(*) FROM lista_espera le JOIN usuarios u ON le.usuario_id ='
        ' u.id'
        + query_base_where
    )
    cursor.execute(query_count, params)
    total_registros = cursor.fetchone()[0]
    total_paginas = (
        (total_registros + per_page - 1) // per_page
        if total_registros > 0
        else 1
    )

    query_lista = (
        """
        SELECT 
            le.*,
            u.nome AS paciente_nome,
            u.cpf AS paciente_cpf,
            u.cartao_sus AS paciente_sus,
            u.numero_prontuario AS paciente_prontuario,
            e.nome AS unidade_solicitante_nome,
            c.codigo AS cid_codigo,
            c.descricao AS cid_descricao,
            c.versao AS cid_versao,
            p_triagem.nome AS profissional_triagem_nome,
            e_triagem.nome AS profissional_triagem_unidade,
            p_atendimento.nome AS profissional_atualizacao_nome,
            e_prof.nome AS profissional_atualizacao_unidade
        FROM lista_espera le
        JOIN usuarios u ON le.usuario_id = u.id
        JOIN estabelecimentos e ON le.unidade_solicitante_id = e.id
        LEFT JOIN cids c ON le.cid_id = c.id
        LEFT JOIN profissionais p_triagem ON le.profissional_triagem_id = p_triagem.id
        LEFT JOIN estabelecimentos e_triagem ON p_triagem.estabelecimento_id = e_triagem.id
        LEFT JOIN profissionais p_atendimento ON le.profissional_atendimento_id = p_atendimento.id
        LEFT JOIN estabelecimentos e_prof ON p_atendimento.estabelecimento_id = e_prof.id
    """
        + query_base_where
        + ' ORDER BY le.data_entrada ASC LIMIT ? OFFSET ?'
    )

    params_paginados = params + [per_page, offset]
    cursor.execute(query_lista, params_paginados)
    raw_atendimentos = cursor.fetchall()

    atendimentos = []
    for row in raw_atendimentos:
      item = dict(row)
      if item['status'] == 'Aguardando':
        cursor.execute(
            """
            SELECT COUNT(*) + 1 FROM lista_espera 
            WHERE modalidade_atendimento = ? 
              AND status = 'Aguardando'
              AND data_entrada < ?
        """,
            (item['modalidade_atendimento'], item['data_entrada']),
        )
        item['posicao_fila'] = cursor.fetchone()[0]
      else:
        item['posicao_fila'] = None
      atendimentos.append(item)

  modalidades = [
      row['modalidade_atendimento']
      for row in cursor.execute(
          'SELECT DISTINCT modalidade_atendimento FROM lista_espera ORDER BY'
          ' modalidade_atendimento ASC'
      ).fetchall()
  ]
  estabelecimentos = [
      dict(row)
      for row in cursor.execute(
          'SELECT id, nome, tipo FROM estabelecimentos WHERE ativo = 1 ORDER BY'
          ' nome ASC'
      ).fetchall()
  ]
  cids = [
      dict(row)
      for row in cursor.execute(
          'SELECT id, codigo, descricao, versao FROM cids ORDER BY codigo ASC'
      ).fetchall()
  ]
  conn.close()

  return render_template(
      'lista_espera.html',
      atendimentos=atendimentos,
      modalidades=modalidades,
      estabelecimentos=estabelecimentos,
      cids=cids,
      pagina_atual=page,
      total_paginas=total_paginas,
      total_registros=total_registros,
  )

if __name__ == '__main__':
  app.run(debug=True, host='0.0.0.0', port=5000)