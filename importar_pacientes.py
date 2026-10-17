import sqlite3
import os
import unicodedata
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')
EXCEL_PATH = os.path.join(os.path.dirname(__file__), 'modelo_pacientes_teste.xlsx')

def padronizar_nome_proprio(texto):
    if not texto:
        return ""
    texto_normalizado = unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('utf-8')
    palavras = texto_normalizado.strip().title().split()
    preposicoes = {'De', 'Da', 'Do', 'Das', 'Dos', 'E'}
    resultado = []
    for index, palavra in enumerate(palavras):
        if index > 0 and palavra in preposicoes:
            resultado.append(palavra.lower())
        else:
            resultado.append(palavra)
    return " ".join(resultado)

def importar_base_pacientes():
    if not os.path.exists(DB_PATH):
        print("Erro: Banco de dados não encontrado. Execute o init_db.py primeiro.")
        return

    if not os.path.exists(EXCEL_PATH):
        print(f"Erro: Arquivo {EXCEL_PATH} não encontrado. Execute o script gerador da planilha primeiro.")
        return

    print("Lendo a planilha Excel...")
    df = pd.read_excel(EXCEL_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("Iniciando importação de pacientes para o banco de dados...")
    sucessos = 0
    erros = 0

    for index, row in df.iterrows():
        try:
            # Captura e limpeza dos dados da linha do Excel
            prontuario = str(row.get('prontuario', '')).strip()
            nome = padronizar_nome_proprio(row.get('nome', ''))
            cpf_limpo = "".join(filter(str.isdigit, str(row.get('cpf', ''))))
            sus_limpo = "".join(filter(str.isdigit, str(row.get('cartao_sus', ''))))
            data_nasc = str(row.get('data_nasc', '')).strip()
            sexo = str(row.get('sexo', '')).strip()
            nome_mae = padronizar_nome_proprio(row.get('nome_mae', ''))
            tel_principal = "".join(filter(str.isdigit, str(row.get('telefone_principal', ''))))
            tel_recado = "".join(filter(str.isdigit, str(row.get('telefone_recado', ''))))
            nome_unidade = str(row.get('unidade_referencia', '')).strip()

            # Busca o ID da unidade de referência na tabela estabelecimentos pelo nome
            unidade_id = None
            if nome_unidade:
                cursor.execute("SELECT id FROM estabelecimentos WHERE nome LIKE ?", (f"%{nome_unidade}%",))
                est_row = cursor.fetchone()
                if est_row:
                    unidade_id = est_row['id']

            cursor.execute("""
                INSERT INTO usuarios (
                    numero_prontuario, nome, cpf, cartao_sus, data_nascimento, sexo, 
                    nome_mae, telefone_principal, telefone_recado, unidade_referencia_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                prontuario or None,
                nome,
                cpf_limpo or None,
                sus_limpo or None,
                data_nasc or None,
                sexo or None,
                nome_mae or None,
                tel_principal or None,
                tel_recado or None,
                unidade_id
            ))
            sucessos += 1
        except sqlite3.IntegrityError:
            erros += 1
            print(f"Aviso: Paciente {row.get('nome')} já existe (duplicidade de CPF/SUS/Prontuário).")
        except Exception as e:
            erros += 1
            print(f"Erro ao importar paciente {row.get('nome')}: {e}")

    conn.commit()
    conn.close()
    print(f"\nImportação concluída! Sucessos: {sucessos} | Duplicidades/Erros ignorados: {erros}")

if __name__ == '__main__':
    importar_base_pacientes()