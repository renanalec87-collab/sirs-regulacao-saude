from datetime import datetime
import os
import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')


def inicializar_banco():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('PRAGMA foreign_keys = ON;')

    # 1. Tabela de Estabelecimentos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estabelecimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cnes TEXT UNIQUE,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            ativo INTEGER DEFAULT 1,
            criado_por_profissional_id INTEGER,
            atualizado_por_profissional_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (criado_por_profissional_id) REFERENCES profissionais(id),
            FOREIGN KEY (atualizado_por_profissional_id) REFERENCES profissionais(id)
        );
    """)

    # 2. Tabela de CBOs / Especialidades da Fila (SEM CONSELHO OBRIGATÓRIO, FOCO EM REGRAS DE FILA)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cbos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            ocupacao TEXT NOT NULL,
            idade_minima INTEGER,
            idade_maxima INTEGER,
            meses_assiduidade INTEGER DEFAULT 6,
            ativa INTEGER DEFAULT 1,
            gera_lista_espera INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 3. Tabela de CIDs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            versao TEXT DEFAULT 'CID-10',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 4. Tabela de Profissionais (Guarda Cargo, Conselho e Registro Individual)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profissionais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cpf TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            perfil TEXT NOT NULL,
            profissao TEXT,
            sigla_conselho TEXT,
            registro_profissional TEXT,
            permite_terceirizadas INTEGER DEFAULT 0,
            ativo INTEGER DEFAULT 1,
            token_recuperacao TEXT,
            token_expiracao TIMESTAMP,
            forcar_troca_senha INTEGER DEFAULT 0,
            criado_por_profissional_id INTEGER,
            atualizado_por_profissional_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (criado_por_profissional_id) REFERENCES profissionais(id),
            FOREIGN KEY (atualizado_por_profissional_id) REFERENCES profissionais(id)
        );
    """)

    # 5. Vínculos de Unidades por Profissional (Múltiplas Unidades - N:N puro sem amarra com CBO)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profissional_unidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profissional_id INTEGER NOT NULL,
            estabelecimento_id INTEGER NOT NULL,
            ativo INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profissional_id) REFERENCES profissionais(id) ON DELETE CASCADE,
            FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id),
            UNIQUE(profissional_id, estabelecimento_id)
        );
    """)

    # 5.1 Restrição de Profissionais Autorizados por CBO (Caso queira restringir quem insere na fila de certa especialidade)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cbo_profissionais_autorizados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cbo_id INTEGER NOT NULL,
            profissional_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cbo_id) REFERENCES cbos(id) ON DELETE CASCADE,
            FOREIGN KEY (profissional_id) REFERENCES profissionais(id) ON DELETE CASCADE,
            UNIQUE(cbo_id, profissional_id)
        );
    """)

    # 6. Histórico de Acessos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_acessos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profissional_id INTEGER NOT NULL,
            estabelecimento_id INTEGER NOT NULL,
            ip_address TEXT,
            acao TEXT DEFAULT 'LOGIN',
            data_acesso TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profissional_id) REFERENCES profissionais(id) ON DELETE CASCADE,
            FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id)
        );
    """)

    # 7. Usuários / Pacientes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_prontuario TEXT UNIQUE,
            nome TEXT NOT NULL,
            cpf TEXT UNIQUE,
            cartao_sus TEXT UNIQUE,
            data_nascimento DATE NOT NULL,
            sexo TEXT NOT NULL,
            nome_mae TEXT,
            telefone_principal TEXT,
            telefone_recado TEXT,
            unidade_referencia_id INTEGER,
            criado_por_profissional_id INTEGER,
            atualizado_por_profissional_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (unidade_referencia_id) REFERENCES estabelecimentos(id),
            FOREIGN KEY (criado_por_profissional_id) REFERENCES profissionais(id),
            FOREIGN KEY (atualizado_por_profissional_id) REFERENCES profissionais(id)
        );
    """)

    # 8. Lista de Espera
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lista_espera (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            profissional_triagem_id INTEGER,
            profissional_atendimento_id INTEGER,
            modalidade_atendimento TEXT NOT NULL,
            nivel_servico TEXT DEFAULT 'CAPS',
            unidade_solicitante_id INTEGER NOT NULL,
            cid_id INTEGER,
            observacao_atendimento TEXT,
            desfecho_triagem TEXT,
            status TEXT DEFAULT 'Aguardando',
            data_entrada TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (profissional_triagem_id) REFERENCES profissionais(id),
            FOREIGN KEY (profissional_atendimento_id) REFERENCES profissionais(id),
            FOREIGN KEY (unidade_solicitante_id) REFERENCES estabelecimentos(id),
            FOREIGN KEY (cid_id) REFERENCES cids(id)
        );
    """)

    # 9. Guias e Fluxos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guias_fluxos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo_interno TEXT NOT NULL,
            titulo TEXT NOT NULL,
            categoria TEXT NOT NULL,
            logo_path TEXT,
            descricao_resumida TEXT,
            conteudo_orientacao TEXT,
            ativo INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 10. Anexos das Guias
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guias_anexos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guia_id INTEGER NOT NULL,
            nome_arquivo TEXT NOT NULL,
            pdf_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (guia_id) REFERENCES guias_fluxos(id) ON DELETE CASCADE
        );
    """)

    # 11. Campanhas e Avisos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campanhas_avisos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            data_inicio DATE NOT NULL,
            data_fim DATE NOT NULL,
            arquivo_path TEXT,
            descricao_texto TEXT,
            ativo INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Carga Inicial de Estabelecimentos
    estabelecimentos_iniciais = [
        ('4967070', '192 - RESGATE', 'OUTROS'),
        ('7161190', 'CENTRAL DE REGULACAO', 'OUTROS'),
        ('4930134', 'CAPS II-AD', 'CAPS'),
        ('4718321', 'MAYLASKY-ESPECIALIDADES', 'Centro de Especialidade'),
        ('2049635', 'CENTRO DE SAUDE II', 'OUTROS'),
        ('6348548', 'DEPARTAMENTO DE SAUDE', 'OUTROS'),
        ('4752163', 'FARMACIA CENTRAL', 'OUTROS'),
        ('2075660', 'VILA NOVA', 'UBS'),
        ('2075679', 'CANGUERA', 'UBS'),
        ('2752522', 'MAYLASKY', 'UBS'),
        ('2752514', 'SAO JOAO NOVO', 'UBS'),
        ('2752506', 'GOIANA', 'UBS'),
        ('4676173', 'HOSPITAL SANTA CASA', 'HOSPITAL/PRONTO SOCORRO'),
        ('2066912', 'SISO', 'Centro de Especialidade'),
        ('7440529', 'CENTRAL - ESPECIALIDADES', 'Centro de Especialidade'),
        ('2793385', 'CENTRAL - IRIS BARIONI', 'UBS'),
        ('2793377', 'CARMO', 'USF'),
        ('2075652', 'SABOO', 'FUSF'),
        ('2879077', 'GUACU', 'USF'),
        ('2879085', 'TABOAO', 'USF'),
        ('7462662', 'VILLAGGIO EMILIA', 'USF'),
    ]
    cursor.executemany(
        'INSERT INTO estabelecimentos (cnes, nome, tipo) VALUES (?, ?, ?)',
        estabelecimentos_iniciais,
    )

    # CBOs / Especialidades (Sem conselho obrigatório, focadas nas faixas etárias e regras de fila)
    cbos_iniciais = [
        ('225133', 'Psicologia Infantil', 0, 9, 6, 1, 1),
        ('225134', 'Psicologia Adolescente', 10, 17, 6, 1, 1),
        ('225135', 'Psicologia Adulto', 18, 120, 6, 1, 1),
        ('225136', 'Psiquiatria Infantil', 0, 17, 6, 1, 1),
        ('225137', 'Psiquiatria Adulto', 18, 120, 6, 1, 1),
        ('223810', 'Fonoaudiologia Infantil', 0, 17, 6, 1, 1),
        ('223811', 'Fonoaudiologia Adulto', 18, 120, 6, 1, 1),
        ('223905', 'Terapia Ocupacional', 0, 120, 6, 1, 1),
    ]
    cursor.executemany(
        """
        INSERT INTO cbos (codigo, ocupacao, idade_minima, idade_maxima, meses_assiduidade, ativa, gera_lista_espera) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        cbos_iniciais,
    )

    # Administrador Padrão
    senha_padrao = generate_password_hash('admin123')
    cursor.execute(
        """
        INSERT INTO profissionais (nome, cpf, email, senha_hash, perfil, profissao, sigla_conselho, registro_profissional, ativo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            'Administrador Geral',
            '00000000000',
            'admin@saoroque.sp.gov.br',
            senha_padrao,
            'NIVEL_I',
            'Administrador',
            'MTE',
            'ADMIN-01',
            1,
        ),
    )
    profissional_id = cursor.lastrowid

    # Vincula o Admin ao CAPS II-AD (id 3) livremente
    cursor.execute(
        """
        INSERT INTO profissional_unidades (profissional_id, estabelecimento_id, ativo)
        VALUES (?, ?, 1)
    """,
        (profissional_id, 3),
    )

    conn.commit()
    conn.close()
    print('Banco de dados inicializado com sucesso (versão desacoplada e multissetorial)!')


if __name__ == '__main__':
    inicializar_banco()