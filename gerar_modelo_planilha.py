import pandas as pd

# Definindo os dados modelo com as colunas completas, incluindo telefones e unidade de referência
dados_modelo = {
    'prontuario': ['12345', '12346'],
    'nome': ['MARIA DA SILVA', 'JOAO CARLOS SOUZA'],
    'cpf': ['12345678901', '98765432100'],
    'cartao_sus': ['123456789012345', '987654321098765'],
    'data_nasc': ['1985-05-12', '1992-11-20'],
    'sexo': ['Feminino', 'Masculino'],
    'nome_mae': ['Ana da Silva', 'Maria dos Santos'],
    'telefone_principal': ['11988887777', '11977776666'],
    'telefone_recado': ['1133334444', ''],
    'unidade_referencia': ['UBS Mailasque', 'UBS Centro']
}

# Criando o DataFrame com o Pandas
df = pd.DataFrame(dados_modelo)

# Salvando como arquivo Excel (.xlsx)
nome_arquivo = 'modelo_pacientes.xlsx'
df.to_excel(nome_arquivo, index=False)

print(f"Planilha modelo atualizada e criada com sucesso: {nome_arquivo}")