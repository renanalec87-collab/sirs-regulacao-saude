import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

def importar_tabela_cids():
    if not os.path.exists(DB_PATH):
        print("Erro: Banco de dados não encontrado. Execute o init_db.py primeiro.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Exemplo de lista padrão inicial (CID-10 e CID-11) para teste ou base inicial.
    # No futuro, isso pode ler um arquivo CSV oficial da OMS/Ministério da Saúde.
    cids_iniciais = [
        ('F20.0', 'Esquizofrenia paranoide', 'CID-10'),
        ('F32.9', 'Episódio depressivo não especificado', 'CID-10'),
        ('F84.0', 'Autismo infantil', 'CID-10'),
        ('F90.0', 'Transtorno de Déficit de Atenção e Hiperatividade (TDAH)', 'CID-10'),
        ('6A02', 'Transtorno do espectro autista', 'CID-11'),
        ('6A70', 'Transtornos depressivos', 'CID-11')
    ]

    print("Iniciando importação de CIDs...")
    inseridos = 0
    
    for codigo, descricao, versao in cids_iniciais:
        try:
            # Insere nas duas tabelas para manter compatibilidade com o sistema
            cursor.execute("INSERT OR IGNORE INTO cids (codigo, descricao, versao) VALUES (?, ?, ?)", (codigo, descricao, versao))
            cursor.execute("INSERT OR IGNORE INTO cid (codigo, descricao, versao) VALUES (?, ?, ?)", (codigo, descricao, versao))
            inseridos += 1
        except Exception as e:
            print(f"Erro ao inserir o CID {codigo}: {e}")

    conn.commit()
    conn.close()
    print(f"Importação de CIDs concluída! {inseridos} registros processados.")

if __name__ == '__main__':
    importar_tabela_cids()