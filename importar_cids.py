import sqlite3
import os
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')
# Nome correto do arquivo que está na sua pasta lateral: cid.csv
CSV_PATH = os.path.join(os.path.dirname(__file__), 'cid.csv')

def importar_tabela_cids():
    if not os.path.exists(DB_PATH):
        print("Erro: Banco de dados não encontrado. Execute o init_db.py primeiro.")
        return

    if not os.path.exists(CSV_PATH):
        print(f"Erro: Arquivo '{CSV_PATH}' não encontrado na pasta do projeto.")
        return

    print("A ler o arquivo CSV de CIDs...")
    try:
        df = pd.read_csv(CSV_PATH, encoding='latin1', sep=';')
    except Exception as e:
        print(f"Erro ao ler o CSV: {e}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Iniciando importação em massa para o banco de dados...")
    
    dados = []
    for _, linha in df.iterrows():
        codigo = str(linha.get('codigo', '')).strip()
        descricao = str(linha.get('descricao', '')).strip()
        versao = str(linha.get('versao', 'CID-10')).strip()
        if codigo and descricao:
            dados.append((codigo, descricao, versao))

    # Insere todos os registos de uma só vez (muito rápido)
    cursor.executemany(
        "INSERT OR IGNORE INTO cids (codigo, descricao, versao) VALUES (?, ?, ?)",
        dados
    )

    conn.commit()
    conn.close()
    print(f"Importação concluída com sucesso! {len(dados)} registros processados.")

if __name__ == '__main__':
    importar_tabela_cids()