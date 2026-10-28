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
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn


# --- FUNÇÃO AUXILIAR DE CÁLCULO DE IDADE ---
def calcular_idade(data_nascimento_str):
    if not data_nascimento_str:
        return 0
    try:
        hoje = datetime.now().date()
        nasc = datetime.strptime(
            data_nascimento_str.split('T')[0], '%Y-%m-%d'
        ).date()
        return (
            hoje.year
            - nasc.year
            - ((hoje.month, hoje.day) < (nasc.month, nasc.day))
        )
    except Exception:
        return 0


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


# --- CONFIGURAR SESSÃO DO PROFISSIONAL ---
def iniciar_sessao_profissional(profissional_id, vinculo_id, acao_tipo='LOGIN'):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM profissionais WHERE id = ?', (profissional_id,))
    prof = cursor.fetchone()

    # Consulta de vínculo atualizada (sem cbo_id)
    cursor.execute("""
        SELECT pu.id AS vinculo_id, e.id AS estabelecimento_id, e.nome AS estabelecimento_nome, 
               e.tipo AS estabelecimento_tipo
        FROM profissional_unidades pu
        JOIN estabelecimentos e ON pu.estabelecimento_id = e.id
        WHERE pu.id = ? AND pu.profissional_id = ?
    """, (vinculo_id, profissional_id))
    vinculo = cursor.fetchone()

    if not vinculo:
        conn.close()
        return False

    total_unidades = cursor.execute("""
        SELECT COUNT(*) FROM profissional_unidades 
        WHERE profissional_id = ? AND ativo = 1
    """, (profissional_id,)).fetchone()[0]

    ultimo_acg = cursor.execute("""
        SELECT data_acesso FROM historico_acessos 
        WHERE profissional_id = ? 
        ORDER BY data_acesso DESC LIMIT 1
    """, (profissional_id,)).fetchone()
    
    ultimo_acesso_str = 'Primeiro acesso'
    if ultimo_acg and ultimo_acg['data_acesso']:
        try:
            dt_parse = datetime.strptime(str(ultimo_acg['data_acesso']).split('.')[0], '%Y-%m-%d %H:%M:%S')
            ultimo_acesso_str = dt_parse.strftime('%d/%m/%Y %H:%M:%S')
        except:
            ultimo_acesso_str = str(ultimo_acg['data_acesso'])

    ip_cliente = request.remote_addr
    # Histórico de acessos sem cbo_id
    cursor.execute("""
        INSERT INTO historico_acessos (profissional_id, estabelecimento_id, ip_address, acao)
        VALUES (?, ?, ?, ?)
    """, (profissional_id, vinculo['estabelecimento_id'], ip_cliente, acao_tipo))
    conn.commit()
    conn.close()

    session['usuario_id'] = prof['id']
    session['nome'] = prof['nome']
    session['perfil'] = prof['perfil']
    session['profissao'] = prof['profissao'] or 'Profissional'
    session['sigla_conselho'] = prof['sigla_conselho'] or ''
    session['registro_profissional'] = prof['registro_profissional'] or ''
    
    session['vinculo_id'] = vinculo['vinculo_id']
    session['estabelecimento'] = vinculo['estabelecimento_nome']
    session['estabelecimento_id'] = vinculo['estabelecimento_id']
    session['estabelecimento_tipo'] = vinculo['estabelecimento_tipo']
    session['total_unidades'] = total_unidades
    session['ultimo_acesso'] = ultimo_acesso_str

    return True


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
            SELECT * FROM profissionais 
            WHERE (cpf = ? OR cpf = ? OR email = ?) AND ativo = 1
        """
        cursor.execute(query, (login_input, login_limpo, login_input))
        profissional = cursor.fetchone()

        if profissional and check_password_hash(profissional['senha_hash'], senha):
            profissional_id = profissional['id']
            
            # Busca de vínculos sem cbo_id
            cursor.execute("""
                SELECT pu.id AS vinculo_id, e.nome AS estabelecimento_nome
                FROM profissional_unidades pu
                JOIN estabelecimentos e ON pu.estabelecimento_id = e.id
                WHERE pu.profissional_id = ? AND pu.ativo = 1
            """, (profissional_id,))
            vinculos = cursor.fetchall()
            conn.close()

            if not vinculos:
                flash('Profissional sem unidades vinculadas no sistema.', 'danger')
                return render_template('login.html', campanhas=campanhas)

            if len(vinculos) == 1:
                iniciar_sessao_profissional(profissional_id, vinculos[0]['vinculo_id'], 'LOGIN')
                flash('Login efetuado com sucesso!', 'success')
                return redirect(url_for('dashboard'))
            else:
                session['pre_auth_profissional_id'] = profissional_id
                return redirect(url_for('selecionar_unidade'))
        else:
            conn.close()
            flash('CPF/E-mail ou senha incorretos.', 'danger')

    return render_template('login.html', campanhas=campanhas)

@app.route('/selecionar-unidade', methods=['GET', 'POST'])
def selecionar_unidade():
    profissional_id = session.get('pre_auth_profissional_id')
    if not profissional_id:
        flash('Por favor, faça o login primeiro.', 'warning')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        vinculo_id = request.form.get('vinculo_id')
        if iniciar_sessao_profissional(profissional_id, vinculo_id, 'TROCA DE UNIDADE'):
            session.pop('pre_auth_profissional_id', None)
            conn.close()
            flash('Acesso e unidade selecionados com sucesso!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Vínculo inválido ou não autorizado.', 'danger')

    # Busca o nome e garante que não venha vazio
    cursor.execute('SELECT nome FROM profissionais WHERE id = ?', (profissional_id,))
    prof = cursor.fetchone()
    nome_profissional = prof['nome'] if prof and prof['nome'] else 'Usuário'

    cursor.execute("""
        SELECT pu.id AS vinculo_id, e.nome AS estabelecimento_nome
        FROM profissional_unidades pu
        JOIN estabelecimentos e ON pu.estabelecimento_id = e.id
        WHERE pu.profissional_id = ? AND pu.ativo = 1
    """, (profissional_id,))
    vinculos = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return render_template('selecionar_unidade.html', nome_profissional=nome_profissional, vinculos=vinculos)

@app.route('/trocar-unidade', methods=['GET'])
@login_required
def trocar_unidade():
    session['pre_auth_profissional_id'] = session.get('usuario_id')
    return redirect(url_for('selecionar_unidade'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Sessão encerrada com sucesso.', 'info')
    return redirect(url_for('login'))

# --- API DE HISTÓRICO DE ACESSOS (ÚLTIMOS 30 DIAS) ---
@app.route('/api/historico-acessos', methods=['GET'])
@login_required
def api_historico_acessos():
    profissional_id = session.get('usuario_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        historico = cursor.execute("""
            SELECT ha.data_acesso, ha.acao, ha.ip_address, e.nome AS estabelecimento_nome
            FROM historico_acessos ha
            LEFT JOIN estabelecimentos e ON ha.estabelecimento_id = e.id
            WHERE ha.profissional_id = ?
            ORDER BY ha.data_acesso DESC
            LIMIT 50
        """, (profissional_id,)).fetchall()
        
        dados = []
        for h in historico:
            dados.append({
                'data_acesso': str(h['data_acesso']).split('.')[0],
                'acao': h['acao'] or 'LOGIN',
                'ip_address': h['ip_address'] or '127.0.0.1',
                'estabelecimento_nome': h['estabelecimento_nome'] or 'Unidade não informada'
            })
    except Exception as e:
        print(f"Erro ao buscar histórico de acessos: {e}")
        dados = []
    finally:
        conn.close()
        
    return jsonify(dados)

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    estabelecimentos = [
        dict(row)
        for row in cursor.execute(
            'SELECT id, nome, tipo FROM estabelecimentos WHERE ativo = 1 ORDER BY nome ASC'
        ).fetchall()
    ]
    
    cids = [] 
    
    cbos = [
        dict(row)
        for row in cursor.execute(
            'SELECT id, ocupacao, idade_minima, idade_maxima FROM cbos WHERE ativa = 1 AND gera_lista_espera = 1 ORDER BY ocupacao ASC'
        ).fetchall()
    ]
    
    conn.close()
    return render_template(
        'dashboard.html',
        estabelecimentos=estabelecimentos,
        cids=cids,
        cbos=cbos,
    )


@app.route('/api/cids/buscar', methods=['GET'])
@login_required
def api_buscar_cids():
    termo = request.args.get('q', '').strip()
    if len(termo) < 2:
        return jsonify({'sucesso': True, 'dados': []})
    
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT id, codigo, descricao, versao 
        FROM cids 
        WHERE codigo LIKE ? OR descricao LIKE ?
        ORDER BY versao DESC, codigo ASC
        LIMIT 30
    """
    termo_like = f'%{termo}%'
    cursor.execute(query, (termo_like, termo_like))
    resultados = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'sucesso': True, 'dados': resultados})


@app.route('/api/paciente/buscar', methods=['GET'])
@login_required
def buscar_paciente():
    termo_doc = request.args.get('doc', '').strip()
    termo_nome = request.args.get('nome', '').strip()
    termo_nasc = request.args.get('nasc', '').strip()
    
    if not termo_doc and not termo_nome and not termo_nasc:
        return jsonify({
            'sucesso': False,
            'encontrado': False,
            'mensagem': 'Por favor, informe ao menos um critério de busca.'
        }), 400

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
            filtro_sql += ' AND (u.cpf LIKE ? OR u.numero_prontuario LIKE ?)'
            params.extend([f'%{doc_limpo}%', f'%{doc_limpo}%'])
    
    elif termo_nome or termo_nasc:
        if termo_nome:
            cns_limpo = ''.join(filter(str.isdigit, termo_nome))
            if cns_limpo and len(cns_limpo) >= 3:
                filtro_sql += ' AND (u.nome LIKE ? OR u.nome_mae LIKE ? OR u.cartao_sus LIKE ?)'
                params.extend([f'%{termo_nome}%', f'%{termo_nome}%', f'%{cns_limpo}%'])
            else:
                palavras = termo_nome.split()
                for palavra in palavras:
                    filtro_sql += ' AND (u.nome LIKE ? OR u.nome_mae LIKE ?)'
                    params.extend([f'%{palavra}%', f'%{palavra}%'])
        
        if termo_nasc:
            filtro_sql += ' AND u.data_nascimento = ?'
            params.append(termo_nasc)

    cursor.execute(query_count + filtro_sql, params)
    total_registros = cursor.fetchone()[0]
    total_paginas = (
        (total_registros + per_page - 1) // per_page
        if total_registros > 0
        else 1
    )

    query = """
        SELECT DISTINCT u.id, u.numero_prontuario, u.nome, u.cpf, u.cartao_sus, 
               u.data_nascimento, u.sexo, u.nome_mae, u.telefone_principal, 
               u.telefone_recado, u.unidade_referencia_id, u.created_at, u.updated_at, 
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
        telefone_principal = request.form.get('telefone_principal', '').strip()
        telefone_recado = request.form.get('telefone_recado', '').strip()

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
            'Erro: Já existe um paciente cadastrado com este CPF, Cartão SUS ou Nº de Prontuário.',
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

        status_fila = r['status'] or 'Aguardando'
        
        if status_fila in ['Atendido / Finalizado']:
            status_exibicao = 'Concluída'
        elif status_fila in ['Cancelado / Desistência']:
            status_exibicao = 'Cancelada'
        elif status_fila in ['Em Atendimento']:
            status_exibicao = 'Em Atendimento'
        else:
            status_exibicao = 'Aguardando'

        if status_exibicao in ['Aguardando', 'Em Atendimento'] and r['data_atualizacao']:
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
    
    unidade_solicitante_id = session.get('estabelecimento_id') or request.form.get('unidade_solicitante_id')
    
    if not unidade_solicitante_id:
        conn_temp = get_db_connection()
        fallback_est = conn_temp.execute("SELECT id FROM estabelecimentos WHERE ativo = 1 LIMIT 1").fetchone()
        conn_temp.close()
        if fallback_est:
            unidade_solicitante_id = fallback_est['id']
        else:
            flash('Erro: Unidade solicitante não identificada. Faça login em uma unidade.', 'danger')
            return redirect(url_for('dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cbo_info = cursor.execute('SELECT id, ocupacao FROM cbos WHERE ocupacao = ?', (modalidade,)).fetchone()
        
        if cbo_info:
            cbo_id = cbo_info['id']
            autorizados = cursor.execute("""
                SELECT p.nome, p.email, e.nome AS unidade_nome
                FROM cbo_profissionais_autorizados cpa
                JOIN profissionais p ON cpa.profissional_id = p.id
                LEFT JOIN profissional_unidades pu ON pu.profissional_id = p.id AND pu.ativo = 1
                LEFT JOIN estabelecimentos e ON pu.estabelecimento_id = e.id
                WHERE cpa.cbo_id = ?
            """, (cbo_id,)).fetchall()
            
            if autorizados:
                cursor.execute('SELECT profissional_id FROM cbo_profissionais_autorizados WHERE cbo_id = ?', (cbo_id,))
                ids_permitidos = [row[0] for row in cursor.fetchall()]
                usuario_logado_id = session.get('usuario_id')
                
                if usuario_logado_id not in ids_permitidos:
                    detalhes = "".join([f"<li class='mb-1'><strong>{a['nome']}</strong> <span style='color: #4b5563;'>(Unidade: {a['unidade_nome'] or 'Não informada'} | E-mail: {a['email']})</span></li>" for a in autorizados])
                    
                    mensagem_alerta = (
                        f"<div class='d-flex align-start gap-3'>"
                        f"  <div style='font-size: 28px; line-height: 1; color: #d97706;'>⚠️</div>"
                        f"  <div style='flex: 1;'>"
                        f"     <div style='font-size: 15px; font-weight: 700; color: #92400e; margin-bottom: 4px;'>Acesso Restrito: Fluxo Regulado para a Especialidade {modalidade}</div>"
                        f"     <div style='color: #4b5563; font-size: 13px; margin-bottom: 8px;'>Somente o(s) seguinte(s) profissional(is) autorizado(s) pode(m) realizar inserções:</div>"
                        f"     <ul class='mb-2 ps-3' style='font-size: 13px; color: #1f2937;'>{detalhes}</ul>"
                        f"     <hr style='border: none; border-top: 1px solid #fde68a; margin: 8px 0;'>"
                        f"     <small style='color: #78350f;'>Consulte o guia de fluxo desta especialidade na aba superior ou entre em contato com o responsável.</small>"
                        f"  </div>"
                        f"</div>"
                    )
                    conn.close()
                    flash(mensagem_alerta, 'warning')
                    return redirect(url_for('dashboard'))

        cursor.execute("""
            SELECT id, data_entrada FROM lista_espera 
            WHERE usuario_id = ? AND modalidade_atendimento = ? AND status IN ('Aguardando', 'Em Atendimento')
        """, (usuario_id, modalidade))
        if cursor.fetchone():
            flash('Bloqueio: Paciente já possui uma solicitação ativa para esta modalidade.', 'warning')
            return redirect(url_for('dashboard'))

        nivel_servico = 'CAPS'
        est_info = cursor.execute('SELECT tipo FROM estabelecimentos WHERE id = ?', (unidade_solicitante_id,)).fetchone()
        if est_info and est_info['tipo'] not in ['CAPS', 'Centro de Atenção Psicossocial']:
            nivel_servico = 'AMBULATORIAL'

        cid_id = request.form.get('cid_id')
        observacao = request.form.get('observacao_atendimento', '').strip()

        cursor.execute("""
            INSERT INTO lista_espera (usuario_id, profissional_triagem_id, modalidade_atendimento, nivel_servico, unidade_solicitante_id, cid_id, observacao_atendimento, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Aguardando')
        """, (usuario_id, session['usuario_id'], modalidade, nivel_servico, unidade_solicitante_id, cid_id or None, observacao))
        
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
    
    row_atual = cursor.execute("""
        SELECT le.status, le.nivel_servico, le.unidade_solicitante_id, e.nome AS unidade_nome
        FROM lista_espera le
        LEFT JOIN estabelecimentos e ON le.unidade_solicitante_id = e.id
        WHERE le.id = ?
    """, (lista_id,)).fetchone()

    if not row_atual:
        conn.close()
        flash('Erro: Registro não encontrado.', 'danger')
        return redirect(url_for('ver_lista_espera'))

    if row_atual['status'] in ['Atendido / Finalizado', 'Cancelado / Desistência']:
        conn.close()
        flash('Erro: Esta solicitação já foi encerrada.', 'danger')
        return redirect(url_for('ver_lista_espera'))

    unidade_atual_sessao = session.get('estabelecimento_id')
    perfil_usuario = session.get('perfil')

    if row_atual['status'] == 'Em Atendimento' and novo_status != 'Em Atendimento':
        if str(row_atual['unidade_solicitante_id']) != str(unidade_atual_sessao) and perfil_usuario != 'NIVEL_I':
            unidade_responsavel = row_atual['unidade_nome'] or 'outra unidade'
            conn.close()
            
            mensagem_bloqueio = (
                f"<div class='d-flex align-start gap-3'>"
                f"  <div style='font-size: 28px; line-height: 1; color: #dc2626;'>🔒</div>"
                f"  <div style='flex: 1;'>"
                f"     <div style='font-size: 15px; font-weight: 700; color: #991b1b; margin-bottom: 4px;'>Ação Bloqueada: Paciente em Atendimento Simultâneo</div>"
                f"     <div style='color: #4b5563; font-size: 13px; margin-bottom: 6px;'>"
                f"         Este paciente encontra-se atualmente com o status <strong>'Em Atendimento'</strong> vinculado à unidade <strong>{unidade_responsavel}</strong>."
                f"     </div>"
                f"     <div style='color: #1f2937; font-size: 13px;'>"
                f"         Por questões de segurança e integridade da regulação, apenas os profissionais lotados na unidade executora ou um gestor (Nível I) podem finalizar ou alterar o fluxo deste caso."
                f"     </div>"
                f"  </div>"
                f"</div>"
            )
            flash(mensagem_bloqueio, 'danger')
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

    page = int(request.args.get('page', 1))
    per_page = 15
    offset = (page - 1) * per_page

    cursor.execute('SELECT COUNT(*) FROM profissionais')
    total_registros = cursor.fetchone()[0]
    total_paginas = (
        (total_registros + per_page - 1) // per_page
        if total_registros > 0
        else 1
    )

    profissionais_raw = cursor.execute("""
        SELECT p.*, 
               p_criou.nome AS criado_por_nome,
               p_at.nome AS atualizado_por_nome
        FROM profissionais p 
        LEFT JOIN profissionais p_criou ON p.criado_por_profissional_id = p_criou.id
        LEFT JOIN profissionais p_at ON p.atualizado_por_profissional_id = p_at.id
        ORDER BY p.nome ASC
        LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()

    profissionais = []
    for p in profissionais_raw:
        prof_dict = dict(p)
        
        # Consulta de múltiplos vínculos sem amarra de cbo_id
        vinculos_raw = cursor.execute("""
            SELECT pu.id AS vinculo_id, pu.estabelecimento_id,
                   e.nome AS estabelecimento_nome
            FROM profissional_unidades pu
            JOIN estabelecimentos e ON pu.estabelecimento_id = e.id
            WHERE pu.profissional_id = ? AND pu.ativo = 1
        """, (prof_dict['id'],)).fetchall()
        
        prof_dict['vinculos'] = [dict(v) for v in vinculos_raw]
        
        if prof_dict['vinculos']:
            prof_dict['estabelecimento_nome'] = ", ".join([v['estabelecimento_nome'] for v in prof_dict['vinculos']])
        else:
            prof_dict['estabelecimento_nome'] = "Não informada"
            
        profissionais.append(prof_dict)

    estabelecimentos = [
        dict(row)
        for row in cursor.execute('SELECT id, nome FROM estabelecimentos WHERE ativo = 1 ORDER BY nome ASC').fetchall()
    ]
    conn.close()
    
    return render_template(
        'admin_profissionais.html',
        profissionais=profissionais,
        estabelecimentos=estabelecimentos,
        pagina_atual=page,
        total_paginas=total_paginas,
        total_registros=total_registros,
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
                'Erro: A senha deve ter exatamente 8 caracteres e conter pelo menos 3 letras.',
                'danger',
            )
            return redirect(url_for('listar_profissionais'))

    perfil = request.form.get('perfil', 'NIVEL_II')
    profissao = request.form.get('profissao', '').strip()
    sigla_conselho = request.form.get('sigla_conselho', '').strip().upper()
    registro_profissional = request.form.get('registro_profissional', '').strip()
    permite_terceirizadas = (
        1 if request.form.get('permite_terceirizadas') == 'on' else 0
    )
    ativo = 1 if request.form.get('ativo', '1') == '1' else 0
    usuario_logado_id = session.get('usuario_id')

    estabelecimento_ids = request.form.getlist('estabelecimento_ids[]')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if profissional_id:
            # === VERIFICAÇÃO DE DUPLICIDADE SEGURA NA EDIÇÃO ===
            duplicado = cursor.execute("""
                SELECT id FROM profissionais 
                WHERE (cpf = ? OR email = ?) AND id != ?
            """, (cpf, email, profissional_id)).fetchone()
            
            if duplicado:
                conn.close()
                flash('Erro: Já existe outro profissional cadastrado com este CPF ou E-mail.', 'danger')
                return redirect(url_for('listar_profissionais'))

            if senha:
                senha_hash = generate_password_hash(senha)
                cursor.execute(
                    """
                        UPDATE profissionais 
                        SET nome = ?, cpf = ?, email = ?, senha_hash = ?, perfil = ?, 
                            profissao = ?, sigla_conselho = ?, registro_profissional = ?, 
                            permite_terceirizadas = ?, ativo = ?, atualizado_por_profissional_id = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """,
                    (
                        nome,
                        cpf,
                        email,
                        senha_hash,
                        perfil,
                        profissao or None,
                        sigla_conselho or None,
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
                        SET nome = ?, cpf = ?, email = ?, perfil = ?, 
                            profissao = ?, sigla_conselho = ?, registro_profissional = ?, 
                            permite_terceirizadas = ?, ativo = ?, atualizado_por_profissional_id = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """,
                    (
                        nome,
                        cpf,
                        email,
                        perfil,
                        profissao or None,
                        sigla_conselho or None,
                        registro_profissional or None,
                        permite_terceirizadas,
                        ativo,
                        usuario_logado_id,
                        profissional_id,
                    ),
                )
                                                  
            for est_id in estabelecimento_ids:
                if est_id:
                    vinculo_existente = cursor.execute("""
                        SELECT id FROM profissional_unidades 
                        WHERE profissional_id = ? AND estabelecimento_id = ?
                    """, (profissional_id, est_id)).fetchone()
                    
                    if vinculo_existente:
                        # Se já existe (mesmo inativo), reativa/mantém ativo
                        cursor.execute('UPDATE profissional_unidades SET ativo = 1 WHERE id = ?', (vinculo_existente['id'],))
                    else:
                        # Se não existe, insere o novo vínculo
                        cursor.execute("""
                            INSERT INTO profissional_unidades (profissional_id, estabelecimento_id, ativo)
                            VALUES (?, ?, 1)
                        """, (profissional_id, est_id))

            flash('Profissional atualizado com sucesso!', 'success')
        else:
            if not senha:
                flash('Erro: A senha é obrigatória.', 'danger')
                return redirect(url_for('listar_profissionais'))
            
            senha_hash = generate_password_hash(senha)
            cursor.execute(
                """
                INSERT INTO profissionais (
                    nome, cpf, email, senha_hash, perfil, profissao, sigla_conselho, 
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
                    profissao or None,
                    sigla_conselho or None,
                    registro_profissional or None,
                    permite_terceirizadas,
                    ativo,
                    usuario_logado_id,
                    usuario_logado_id,
                ),
            )
            
            profissional_id = cursor.lastrowid

            for est_id in estabelecimento_ids:
                if est_id:
                    cursor.execute("""
                        INSERT INTO profissional_unidades (profissional_id, estabelecimento_id, ativo)
                        VALUES (?, ?, 1)
                    """, (profissional_id, est_id))

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
                   p1.nome AS criado_por_nome, 
                   p2.nome AS atualizado_por_nome
            FROM estabelecimentos e
            LEFT JOIN profissionais p1 ON e.criado_por_profissional_id = p1.id
            LEFT JOIN profissionais p2 ON e.atualizado_por_profissional_id = p2.id
            ORDER BY e.nome ASC
        """).fetchall()
    ]
    
    conn.close()
    return render_template('admin_estabelecimentos.html', estabelecimentos=estabelecimentos)


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
    
    if unidade_filtro:
        query_unidade = """
            SELECT 
                p.nome AS profissional_nome,
                c.ocupacao AS profissional_cbo,
                SUM(CASE WHEN le.status = 'Aguardando' THEN 1 ELSE 0 END) AS aguardando,
                SUM(CASE WHEN le.status = 'Em Atendimento' THEN 1 ELSE 0 END) AS em_atendimento,
                SUM(CASE WHEN le.status = 'Atendido / Finalizado' THEN 1 ELSE 0 END) AS atendido,
                SUM(CASE WHEN le.status = 'Cancelado / Desistência' THEN 1 ELSE 0 END) AS cancelado,
                COUNT(le.id) AS total
            FROM lista_espera le
            LEFT JOIN profissionais p ON le.profissional_triagem_id = p.id
            LEFT JOIN profissional_unidades pu ON pu.profissional_id = p.id AND pu.estabelecimento_id = le.unidade_solicitante_id
            LEFT JOIN cbos c ON pu.cbo_id = c.id
            WHERE le.unidade_solicitante_id = ?
        """
    else:
        query_unidade = """
            SELECT 
                e.nome AS unidade,
                SUM(CASE WHEN le.status = 'Aguardando' THEN 1 ELSE 0 END) AS aguardando,
                SUM(CASE WHEN le.status = 'Em Atendimento' THEN 1 ELSE 0 END) AS em_atendimento,
                SUM(CASE WHEN le.status = 'Atendido / Finalizado' THEN 1 ELSE 0 END) AS atendido,
                SUM(CASE WHEN le.status = 'Cancelado / Desistência' THEN 1 ELSE 0 END) AS cancelado,
                SUM(CASE WHEN le.status = 'Ajuste de Faixa Etária' THEN 1 ELSE 0 END) AS ajuste_faixa,
                COUNT(le.id) AS total
            FROM estabelecimentos e
            LEFT JOIN lista_espera le ON le.unidade_solicitante_id = e.id
        """

    query_modalidade = """
        SELECT 
            modalidade_atendimento,
            SUM(CASE WHEN strftime('%Y', data_entrada) = '2023' THEN 1 ELSE 0 END) AS ano_2023,
            SUM(CASE WHEN strftime('%Y', data_entrada) = '2024' THEN 1 ELSE 0 END) AS ano_2024,
            SUM(CASE WHEN strftime('%Y', data_entrada) = '2025' THEN 1 ELSE 0 END) AS ano_2025,
            SUM(CASE WHEN strftime('%Y', data_entrada) = '2026' THEN 1 ELSE 0 END) AS ano_2026,
            COUNT(*) AS quantidade 
        FROM lista_espera 
        WHERE 1=1
    """

    params = []
    params_unidade = []

    if data_inicio and data_fim:
        query_status += ' AND data_entrada BETWEEN ? AND ?'
        query_modalidade += ' AND data_entrada BETWEEN ? AND ?'
        if unidade_filtro:
            query_unidade += ' AND le.data_entrada BETWEEN ? AND ?'
        else:
            query_unidade += (
                ' AND (le.data_entrada BETWEEN ? AND ? OR le.data_entrada IS NULL)'
            )
        params.extend([data_inicio, data_fim + ' 23:59:59'])
        params_unidade.extend([data_inicio, data_fim + ' 23:59:59'])

    if unidade_filtro:
        query_status += ' AND unidade_solicitante_id = ?'
        query_modalidade += ' AND unidade_solicitante_id = ?'
        params.append(unidade_filtro)
        params_unidade.insert(0, unidade_filtro)
    else:
        query_unidade += ' WHERE e.ativo = 1'

    if modalidade_filtro:
        query_status += ' AND modalidade_atendimento = ?'
        query_modalidade += ' AND modalidade_atendimento = ?'
        query_unidade += ' AND le.modalidade_atendimento = ?'
        params.append(modalidade_filtro)
        params_unidade.append(modalidade_filtro)

    query_status += ' GROUP BY status'
    
    if unidade_filtro:
        query_unidade += ' GROUP BY p.id, p.nome, c.ocupacao ORDER BY total DESC'
    else:
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
            'SELECT id, nome FROM estabelecimentos WHERE ativo = 1 ORDER BY'
            ' nome ASC'
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

    coordenadas_fixas = {
        '192 - RESGATE': [-23.519083, -47.141246],
        'CENTRAL DE REGULACAO': [-23.5320, -47.1335],
        'CANGUERA': [-23.605284, -47.164590],
        'CAPS II': [-23.5300, -47.1320],
        'CAPS II-AD': [-23.536013, -47.137850],
        'CARMO': [-23.627480, -47.094070],
        'CENTRAL - ESPECIALIDADES': [-23.538167, -47.139515],
        'CENTRAL - IRIS BARIONI': [-23.532277, -47.137233],
        'CENTRO DE SAUDE II': [-23.529892, -47.132510],
        'DEPARTAMENTO DE SAUDE': [-23.541973, -47.129337],
        'FARMACIA CENTRAL': [-23.529892, -47.132510],
        'GOIANA': [-23.554126, -47.147340],     
        'GUACU': [-23.519083, -47.141246],
        'HOSPITAL SANTA CASA': [-23.537575, -47.138604],
        'MAYLASKY': [-23.557459, -47.090049],
        'MAYLASKY-ESPECIALIDADES': [-23.558604, -47.093887],
        'SABOO': [-23.465941, -47.155775],
        'SAO JOAO NOVO': [-23.540390, -47.036600],     
        'SISO': [-23.532137, -47.137198],
        'TABOAO': [-23.545165, -47.123766],
        'VILA NOVA': [-23.523544, -47.154396],
        'VILLAGGIO EMILIA': [-23.548436, -47.131466],
    }

    resultado_final = []
    for d in dados:
        nome_est = d['unidade'].strip().upper()
        coords = [-23.5325, -47.1353]
        for chave, latlng in coordenadas_fixas.items():
            if chave in nome_est:
                coords = latlng
                break

        resultado_final.append({
            'unidade': d['unidade'],
            'total': d['total'],
            'lat': coords[0],
            'lng': coords[1],
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
            'SELECT * FROM cids ORDER BY versao DESC, codigo ASC LIMIT 100'
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
    cursor = conn.cursor()
    
    cbos_raw = cursor.execute('SELECT * FROM cbos ORDER BY ocupacao ASC').fetchall()
    cbos = []
    
    for row in cbos_raw:
        cbo_dict = dict(row)
        
        autorizados = cursor.execute("""
            SELECT p.id, p.nome, p.cpf
            FROM cbo_profissionais_autorizados cpa
            JOIN profissionais p ON cpa.profissional_id = p.id
            WHERE cpa.cbo_id = ?
        """, (cbo_dict['id'],)).fetchall()
        
        cbo_dict['profissionais_detalhes'] = [dict(a) for a in autorizados]
        cbo_dict['tem_restricao'] = len(cbo_dict['profissionais_detalhes']) > 0
        cbos.append(cbo_dict)
        
    conn.close()
    return render_template('admin_cbos.html', cbos=cbos)


@app.route('/admin/configuracoes/cbo/salvar', methods=['POST'])
@login_required
@nivel_i_required
def salvar_cbo():
    cbo_id = request.form.get('id')
    codigo = request.form.get('codigo', '').strip()
    ocupacao = padronizar_nome_proprio(request.form.get('ocupacao', ''))
    
    idade_minima = request.form.get('idade_minima')
    idade_minima = int(idade_minima) if idade_minima != '' and idade_minima is not None else None

    idade_maxima = request.form.get('idade_maxima')
    idade_maxima = int(idade_maxima) if idade_maxima != '' and idade_maxima is not None else None

    conselho = request.form.get('conselho', '').strip().upper()
    ativa = 1 if request.form.get('ativa') == '1' else 0
    gera_lista_espera = 1 if request.form.get('gera_lista_espera') == '1' else 0
    
    profissionais_autorizados = request.form.getlist('profissionais_autorizados')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if cbo_id:
            cursor.execute("""
                UPDATE cbos 
                SET codigo = ?, ocupacao = ?, idade_minima = ?, idade_maxima = ?, sigla_conselho = ?, ativa = ?, gera_lista_espera = ?
                WHERE id = ?
            """, (codigo, ocupacao, idade_minima, idade_maxima, conselho or None, ativa, gera_lista_espera, cbo_id))
            flash('Especialidade/CBO atualizada com sucesso!', 'success')
        else:
            cursor.execute("""
                INSERT INTO cbos (codigo, ocupacao, idade_minima, idade_maxima, sigla_conselho, ativa, gera_lista_espera, meses_assiduidade)
                VALUES (?, ?, ?, ?, ?, ?, ?, 6)
            """, (codigo, ocupacao, idade_minima, idade_maxima, conselho or None, ativa, gera_lista_espera))
            cbo_id = cursor.lastrowid
            flash('Nova Especialidade/CBO cadastrada com sucesso!', 'success')

        cursor.execute("DELETE FROM cbo_profissionais_autorizados WHERE cbo_id = ?", (cbo_id,))
        
        for prof_id in profissionais_autorizados:
            if prof_id:
                cursor.execute("""
                    INSERT INTO cbo_profissionais_autorizados (cbo_id, profissional_id)
                    VALUES (?, ?)
                """, (cbo_id, prof_id))

        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f'Erro ao salvar Especialidade/CBO: {str(e)}', 'danger')
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
            'SELECT COUNT(*) FROM profissional_unidades WHERE cbo_id = ?', (cbo_id,)
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
            id_alvo = cursor.lastrowid
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


@app.route(
    '/admin/configuracoes/guias/excluir/<int:guia_id>', methods=['POST', 'GET']
)
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


@app.route(
    '/admin/configuracoes/guias/anexo/excluir/<int:anexo_id>',
    methods=['GET', 'POST'],
)
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


@app.route('/api/buscar-profissionais', methods=['GET'])
@login_required
@nivel_i_required
def api_buscar_profissionais():
    termo = request.args.get('q', '').strip()
    if len(termo) < 3:
        return jsonify([])
    
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    termo_like = f'%{termo}%'
    cursor.execute("""
        SELECT id, nome, cpf FROM profissionais 
        WHERE ativo = 1 AND (nome LIKE ? OR cpf LIKE ?)
        LIMIT 10
    """, (termo_like, termo_like))
    
    profissionais = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(profissionais)


@app.route('/lista-espera')
@login_required
def ver_lista_espera():
    conn = get_db_connection()
    cursor = conn.cursor()

    filtrado = request.args.get('filtrado') == '1'
    cpf_filtro = request.args.get('cpf', '').strip()
    modalidade_filtro = request.args.get('modalidade', '').strip()
    status_filtro = request.args.get('status_filtro', 'ativos').strip()
    data_inicio = request.args.get('data_inicio', '').strip()
    data_fim = request.args.get('data_fim', '').strip()

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

        if data_inicio:
            query_base_where += ' AND le.data_entrada >= ?'
            params.append(data_inicio + ' 00:00:00')

        if data_fim:
            query_base_where += ' AND le.data_entrada <= ?'
            params.append(data_fim + ' 23:59:59')

        if status_filtro == 'ativos':
            query_base_where += (
                " AND le.status IN ('Aguardando', 'Em Atendimento')"
            )
        elif status_filtro == 'todos':
            pass
        elif status_filtro == 'Ajuste de Faixa Etária':
            query_base_where += " AND le.status IN ('Aguardando', 'Em Atendimento')"
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

        query_lista = (
            """
        SELECT 
            le.*,
            u.nome AS paciente_nome,
            u.cpf AS paciente_cpf,
            u.cartao_sus AS paciente_sus,
            u.numero_prontuario AS paciente_prontuario,
            u.data_nascimento AS paciente_data_nascimento,
            e.nome AS unidade_solicitante_nome,
            c.codigo AS cid_codigo,
            c.descricao AS cid_descricao,
            c.versao AS cid_versao,
            p_triagem.nome AS profissional_triagem_nome,
            p_atendimento.nome AS profissional_atualizacao_nome,
            (
                SELECT est.nome 
                FROM profissional_unidades pu 
                JOIN estabelecimentos est ON pu.estabelecimento_id = est.id 
                WHERE pu.profissional_id = le.profissional_atendimento_id AND pu.ativo = 1 
                LIMIT 1
            ) AS profissional_atualizacao_unidade    
        FROM lista_espera le
        JOIN usuarios u ON le.usuario_id = u.id
        JOIN estabelecimentos e ON le.unidade_solicitante_id = e.id
        LEFT JOIN cids c ON le.cid_id = c.id
        LEFT JOIN profissionais p_triagem ON le.profissional_triagem_id = p_triagem.id
        LEFT JOIN profissionais p_atendimento ON le.profissional_atendimento_id = p_atendimento.id
        """
            + query_base_where
            + ' ORDER BY le.data_entrada ASC'
        )

        cursor.execute(query_lista, params)
        raw_atendimentos = cursor.fetchall()

        atendimentos_processados = []
        for row in raw_atendimentos:
            item = dict(row)

            idade = calcular_idade(item.get('paciente_data_nascimento'))
            item['idade_atual'] = idade

            modalidade = item['modalidade_atendimento']
            status_atual = item['status']
            alerta_faixa = False
            sugestao_modalidade = None

            if status_atual in ['Aguardando', 'Em Atendimento']:
                if 'infantil' in modalidade.lower() and idade >= 10:
                    alerta_faixa = True
                    sugestao_modalidade = 'Psicologia Adolescente'
                elif 'adolescente' in modalidade.lower() and (idade < 10 or idade >= 18):
                    alerta_faixa = True
                    sugestao_modalidade = (
                        'Psicologia Infantil' if idade < 10 else 'Psicologia Adulto'
                    )
                elif 'adulto' in modalidade.lower() and idade < 18:
                    alerta_faixa = True
                    sugestao_modalidade = 'Psicologia Adolescente'

            item['alerta_faixa_etaria'] = alerta_faixa
            item['sugestao_modalidade'] = sugestao_modalidade

            if alerta_faixa:
                item['status_exibicao'] = 'Ajuste de Faixa Etária'
            else:
                item['status_exibicao'] = status_atual

            if status_filtro == 'Ajuste de Faixa Etária' and not alerta_faixa:
                continue

            if status_atual == 'Aguardando' and not alerta_faixa:
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

            atendimentos_processados.append(item)

        total_registros = len(atendimentos_processados)
        total_paginas = (
            (total_registros + per_page - 1) // per_page
            if total_registros > 0
            else 1
        )
        atendimentos = atendimentos_processados[offset : offset + per_page]

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
    cids = [] 
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