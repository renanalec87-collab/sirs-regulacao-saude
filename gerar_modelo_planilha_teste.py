import pandas as pd
import random

primeiros_nomes = ['Ana', 'Carlos', 'Mariana', 'José', 'Fernanda', 'Lucas', 'Beatriz', 'Marcos', 'Juliana', 'Rafael', 'Camila', 'Bruno', 'Larissa', 'Gabriel', 'Patrícia', 'Rodrigo']
sobrenomes = ['Silva', 'Santos', 'Oliveira', 'Souza', 'Rodrigues', 'Ferreira', 'Alves', 'Pereira', 'Lima', 'Gomes', 'Costa', 'Ribeiro']

unidades_sao_roque = [
    'CAPS II - Centro de Atenção Psicossocial',
    'CSII - Centro de Saúde II',
    'Santa Casa de Misericórdia',
    'UBS Central',
    'USF Cambará',
    'USF Maylasky',
    'USF São João Novo',
    'USF Vila Aguiar'
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
    return "".join(map(str, n))

def gerar_sus():
    return "".join([str(random.randint(0, 9)) for _ in range(15)])

def gerar_telefone():
    return f"119{random.randint(40000000, 99999999)}"

# Vamos gerar 50 registros para teste inicial robusto (você pode alterar para 1000 quando quiser)
quantidade = 50
dados = []

for i in range(1, quantidade + 1):
    nome = f"{random.choice(primeiros_nomes)} {random.choice(sobrenomes)} {random.choice(sobrenomes)}"
    prontuario = f"T{1000 + i}"
    cpf = gerar_cpf()
    cartao_sus = gerar_sus()
    
    # Data no formato YYYY-MM-DD ideal para o banco de dados
    ano = random.randint(1970, 2015)
    mes = str(random.randint(1, 12)).zfill(2)
    dia = str(random.randint(1, 28)).zfill(2)
    data_nasc = f"{ano}-{mes}-{dia}"
    
    dados.append({
        'prontuario': prontuario,
        'nome': nome,
        'cpf': cpf,
        'cartao_sus': cartao_sus,
        'data_nasc': data_nasc,
        'sexo': random.choice(sexos),
        'nome_mae': f"{random.choice(primeiros_nomes)} {random.choice(sobrenomes)}",
        'telefone_principal': gerar_telefone(),
        'telefone_recado': gerar_telefone(),
        'unidade_referencia': random.choice(unidades_sao_roque)
    })

df = pd.DataFrame(dados)
arquivo = 'modelo_pacientes_teste.xlsx'
df.to_excel(arquivo, index=False)

print(f"Planilha de teste gerada com sucesso: {arquivo}")