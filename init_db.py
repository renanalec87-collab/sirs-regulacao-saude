from datetime import datetime
import os
import random
import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')


def inicializar_banco():
  # Remove o banco antigo se existir para garantir a recriação limpa
  if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  # Habilita chaves estrangeiras
  cursor.execute('PRAGMA foreign_keys = ON;')

  # 1. Tabela de Estabelecimentos de Saúde
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS estabelecimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cnes TEXT UNIQUE,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            ativo INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

  # 2. Tabela de CBOs / Especialidades
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS cbos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            ocupacao TEXT NOT NULL,
            profissao TEXT,
            sigla_conselho TEXT,
            idade_minima INTEGER,
            idade_maxima INTEGER,
            meses_assiduidade INTEGER DEFAULT 6,
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

  # 4. Tabela de Profissionais
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS profissionais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cpf TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            perfil TEXT NOT NULL,
            cbo_id INTEGER,
            estabelecimento_id INTEGER,
            registro_profissional TEXT,
            permite_terceirizadas INTEGER DEFAULT 0,
            ativo INTEGER DEFAULT 1,
            token_recuperacao TEXT,
            token_expiracao TIMESTAMP,
            forcar_troca_senha INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cbo_id) REFERENCES cbos(id),
            FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos(id)
        );
    """)

  # 5. Tabela de Usuários / Pacientes
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

  # 6. Tabela de Lista de Espera / Encaminhamentos
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

  # 7. Tabela de Guias e Fluxos de Encaminhamento
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

  # 8. Tabela de Anexos em PDF das Guias
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

  # 9. Tabela de Campanhas e Avisos de Login
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

  # --- POPULANDO DADOS INICIAIS ---

  # 1. As 21 Unidades de Saúde
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

  # 2. Especialidades detalhadas com faixas etárias
  cbos_iniciais = [
      ('225133', 'PSICOLOGIA INFANTIL', 'Psicólogo Infantil', 'CRP', 0, 9, 6),
      (
          '225134',
          'PSICOLOGIA ADOLESCENTE',
          'Psicólogo Adolescente',
          'CRP',
          10,
          17,
          6,
      ),
      ('225135', 'PSICOLOGIA ADULTO', 'Psicólogo Adulto', 'CRP', 18, 120, 6),
      ('225136', 'PSIQUIATRIA INFANTIL', 'Médico Psiquiatra Infantil', 'CRM', 0, 17, 6),
      ('225137', 'PSIQUIATRIA ADULTO', 'Médico Psiquiatra Adulto', 'CRM', 18, 120, 6),
      ('223810', 'FONOAUDIOLOGIA INFANTIL', 'Fonoaudiólogo Infantil', 'CRF', 0, 17, 6),
      ('223811', 'FONOAUDIOLOGIA ADULTO', 'Fonoaudiólogo Adulto', 'CRF', 18, 120, 6),
      (
          '223905',
          'TERAPIA OCUPACIONAL ADULTO',
          'Terapeuta Ocupacional Adulto',
          'CREFITO',
          18,
          120,
          6,
      ),
      (
          '223906',
          'TERAPIA OCUPACIONAL INFANTIL',
          'Terapeuta Ocupacional Infantil',
          'CREFITO',
          0,
          17,
          6,
      ),
  ]
  cursor.executemany(
      """
        INSERT INTO cbos (codigo, ocupacao, profissao, sigla_conselho, idade_minima, idade_maxima, meses_assiduidade) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
      cbos_iniciais,
  )

  # 3. CIDs Iniciais
  cids_iniciais = [
      ('F32.2', 'Episódio depressivo grave sem sintomas psicóticos', 'CID-10'),
      ('F41.1', 'Transtorno de ansiedade generalizada', 'CID-10'),
      (
          'F10.2',
          'Transtornos mentais e comportamentais devidos ao uso de álcool',
          'CID-10',
      ),
      ('F20.0', 'Esquizofrenia paranoide', 'CID-10'),
      ('F84.0', 'Autismo infantil', 'CID-10'),
      ('6A70', 'Transtorno depressivo maior, episódio único, moderado', 'CID-11'),
      ('6B00', 'Transtorno de ansiedade generalizada', 'CID-11'),
      ('6C40', 'Transtornos devidos ao uso de álcool', 'CID-11'),
      ('6A20', 'Esquizofrenia', 'CID-11'),
      ('6A02', 'Transtorno do espectro autista', 'CID-11'),
      ('6B20', 'Transtorno de estresse pós-traumático', 'CID-11'),
      ('6A80', 'Transtorno bipolar', 'CID-11'),
  ]
  cursor.executemany(
      'INSERT INTO cids (codigo, descricao, versao) VALUES (?, ?, ?)',
      cids_iniciais,
  )

  # 4. Guias e Fluxos (APACE, APAE, Lucy Montoro, etc.)
  guias_iniciais = [
      (
          'APACE',
          'APACE',
          'SERVIÇOS CONVENIADOS',
          'Diretrizes e critérios de regulação para o acesso às instituições'
          ' parceiras e serviços conveniados de reabilitação e apoio especializado'
          ' na rede.',
          '<p><strong>Critérios de Encaminhamento -'
          ' APACE:</strong></p><ul><li>Apresentar relatório médico'
          ' detalhado.</li><li>Cartão SUS atualizado e comprovante de residência'
          ' em São Roque.</li></ul>',
      ),
      (
          'APAE-SR',
          'APAE-SR',
          'SERVIÇOS CONVENIADOS',
          'Diretrizes e critérios de regulação para o acesso às instituições'
          ' parceiras e serviços conveniados de reabilitação e apoio especializado'
          ' na rede.',
          '<p><strong>Critérios de Encaminhamento -'
          ' APAE:</strong></p><ul><li>Avaliação multiprofissional'
          ' prévia.</li><li>Atendimento voltado a deficiências intelectuais e'
          ' múltiplas.</li></ul>',
      ),
      (
          'Equoterapia',
          'Equoterapia',
          'SERVIÇOS CONVENIADOS',
          'Diretrizes e critérios de regulação para o acesso às instituições'
          ' parceiras e serviços conveniados de reabilitação e apoio especializado'
          ' na rede.',
          '<p><strong>Critérios para'
          ' Equoterapia:</strong></p><ul><li>Indicação médica ou terapêutica'
          ' obrigatória.</li><li>Termo de responsabilidade e avaliação de'
          ' contraindicações físicas.</li></ul>',
      ),
      (
          'Instituto Plenus',
          'Instituto Plenus',
          'SERVIÇOS CONVENIADOS',
          'Diretrizes e critérios de regulação para o acesso às instituições'
          ' parceiras e serviços conveniados de reabilitação e apoio especializado'
          ' na rede.',
          '<p><strong>Critérios - Instituto'
          ' Plenus:</strong></p><ul><li>Encaminhamento via rede pública'
          ' municipal.</li><li>Atendimento especializado conforme diretrizes do'
          ' convênio.</li></ul>',
      ),
      (
          'Rede Lucy Montoro',
          'Rede Lucy Montoro',
          'SERVIÇO ESPECIALIZADO',
          'Diretrizes e critérios de regulação para reabilitação de alta'
          ' complexidade.',
          '<p><strong>Critérios de Acesso - Rede Lucy'
          ' Montoro:</strong></p><ul><li>Pacientes com deficiências físicas e'
          ' motoras incapacitantes.</li><li>Laudo CACON/APAC e exames'
          ' complementares obrigatórios.</li></ul>',
      ),
      (
          'SPA - VIDA NATURAL',
          'SPA - VIDA NATURAL',
          'SERVIÇOS CONVENIADOS',
          'Diretrizes e critérios de regulação para o acesso às instituições'
          ' parceiras e serviços conveniados de reabilitação e apoio especializado'
          ' na rede.',
          '<p><strong>Diretrizes - SPA Vida'
          ' Natural:</strong></p><ul><li>Programas de promoção à saúde e'
          ' bem-estar integrados à rede de atenção.</li></ul>',
      ),
  ]
  cursor.executemany(
      """
        INSERT INTO guias_fluxos (titulo_interno, titulo, categoria, descricao_resumida, conteudo_orientacao, ativo)
        VALUES (?, ?, ?, ?, ?, 1)
    """,
      guias_iniciais,
  )

  # 5. Profissional Administrador Padrão (Nível I)
  senha_padrao = generate_password_hash('admin123')
  cursor.execute(
      """
        INSERT INTO profissionais (nome, cpf, email, senha_hash, perfil, cbo_id, estabelecimento_id, registro_profissional, ativo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
      (
          'Administrador Geral',
          '00000000000',
          'admin@saoroque.sp.gov.br',
          senha_padrao,
          'NIVEL_I',
          1,
          3,
          'ADMIN-01',
          1,
      ),
  )

  conn.commit()
  conn.close()
  print(
      'Banco de dados inicializado com sucesso com todas as unidades,'
      ' especialidades e guias!'
  )


if __name__ == '__main__':
  inicializar_banco()