# SIRS – Sistema Integrado de Regulação em Saúde 🏥

> Sistema web complementar desenvolvido para unificar fluxos de regulação, gerir filas de espera da Saúde Mental (CAPS II) e eliminar encaminhamentos duplicados na rede municipal de saúde.

---

## 💡 Sobre o Projeto & Proposta Operacional
O **SIRS** foi construído como um painel de inteligência operacional cirúrgico e independente. É importante ressaltar que **o sistema não substitui o PEC (Prontuário Eletrônico do Cidadão / e-SUS)**. 

O fluxo operacional foi desenhado para o uso em **abas paralelas no navegador**:
- **Aba 1 (PEC Oficial):** Utilizada pelo profissional de saúde para o registro clínico, anamnese e prontuário oficial.
- **Aba 2 (SIRS):** Utilizada simultaneamente para consulta rápida à fila de espera da Saúde Mental, verificação de status de regulação e validação anti-duplicidade de encaminhamentos.

### Principais Funcionalidades:
- **Acesso Unificado:** Autenticação segura por níveis de permissão (Gestão, Assistencial e Consulta) com criptografia robusta de senhas (`Werkzeug.security`).
- **Gestão da Fila de Espera:** Acompanhamento dinâmico do tempo de espera e status do paciente (Aguardando / Em Atendimento).
- **Trava Anti-Duplicidade:** Validação atômica que impede que o mesmo cidadão ocupe vagas duplicadas na mesma especialidade por solicitações de UBSs diferentes.
- **Auditoria e Conformidade (LGPD):** Registo automático de autoria e carimbo temporal em todas as movimentações e triagens.

---

## 🛠 Stack Tecnológica
- **Backend:** Python 3.10+ / Flask (Microsserviço leve e orientado a rotas RESTful)
- **Persistência de Dados (ORM):** Flask-SQLAlchemy (Abstração relacional compatível com SQLite e bancos corporativos como PostgreSQL)
- **Interface:** HTML5 semântico, CSS3 responsivo (Flexbox/Grid) e ícones via Font Awesome

---

## 🚀 Como Executar o Projeto Localmente

1. Clone o repositório:
   ```bash
   git clone [https://github.com/renanalec87-collab/senhores-regulacao-saude.git](https://github.com/renanalec87-collab/senhores-regulacao-saude.git)
   cd senhores-regulacao-saude
