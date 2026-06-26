import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# -------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# -------------------------------------------------------------------------
st.set_page_config(
    page_title="Wearlub - Controle Administrativo",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização (Amarelo Ouro #F2B705 e fundo clean)
st.markdown("""
<style>
    .main { background-color: #fafafa; }
    div[data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e0e0e0; }
    .stButton>button { 
        width: 100%; 
        border-radius: 6px; 
        background-color: #F2B705; 
        color: black; 
        font-weight: bold;
        border: none;
    }
    .stButton>button:hover { background-color: #d9a304; color: black; }
    .card {
        background-color: white;
        padding: 20px;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        margin-bottom: 20px;
        border-top: 4px solid #F2B705;
    }
    .metric-title { font-size: 13px; color: #757575; font-weight: bold; text-transform: uppercase; }
    .metric-value { font-size: 26px; font-weight: bold; color: #212121; margin-top: 5px; }
</style>
""", unsafe_allow_html=True)

# Topo Customizado
st.markdown("""
<div style="background-color: #F2B705; padding: 15px; border-radius: 6px; margin-bottom: 25px; text-align: center;">
    <h2 style="color: white; margin: 0; font-family: sans-serif; letter-spacing: 1px;">WEARLUB</h2>
    <p style="color: white; margin: 5px 0 0 0; opacity: 0.9; font-size: 14px;">Gestão de Controle Administrativo & Engenharia de Lubrificação</p>
</div>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------------
# INICIALIZAÇÃO DO BANCO DE DADOS
# -------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('wearlub_database.db')
    cursor = conn.cursor()
    
    # Configurações Fiscais e Saldos Iniciais
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracoes_fiscais (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        regime_tributario TEXT,
        aliquota_simples REAL,
        pis REAL,
        cofins REAL,
        iss REAL,
        irpj REAL,
        csll REAL,
        comissao_padrao REAL,
        saldo_inicial_normal REAL,
        saldo_inicial_saude REAL
    )
    """)
    
    cursor.execute("SELECT COUNT(*) FROM configuracoes_fiscais")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO configuracoes_fiscais 
        (regime_tributario, aliquota_simples, pis, cofins, iss, irpj, csll, comissao_padrao, saldo_inicial_normal, saldo_inicial_saude)
        VALUES ('Lucro Presumido', 0.0, 0.65, 3.0, 5.0, 1.2, 1.08, 5.0, 0.0, 0.0)
        """)
        
    # Clientes
    cursor.execute("CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, cnpj TEXT)")
    
    # Funcionários
    cursor.execute("CREATE TABLE IF NOT EXISTS funcionarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, cargo TEXT)")

    # Fluxo de Caixa Atualizado com suporte a detalhes de empréstimo externo
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fluxo_caixa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT, -- 'Entrada', 'Saída' ou 'Transferência'
        categoria TEXT,
        cliente_id INTEGER,
        funcionario_id INTEGER,
        descricao TEXT,
        valor_bruto REAL,
        deducoes_impostos REAL,
        comissao REAL,
        valor_liquido REAL,
        nf_numero TEXT,
        data_vencimento TEXT,
        data_pagamento TEXT,
        status TEXT,
        destino_saude REAL,
        origem_conta TEXT, -- 'Conta Normal' ou 'Saúde da Empresa'
        credor_emprestimo TEXT, -- Detalhes de quem emprestou
        juros_emprestimo REAL, -- Juros combinados
        data_quitacao_acordada TEXT -- Prazo para pagar o empréstimo
    )
    """)
    
    # Adicionar colunas novas se a tabela já existir de versões anteriores
    cursor.execute("PRAGMA table_info(fluxo_caixa)")
    colunas = [c[1] for c in cursor.fetchall()]
    if 'credor_emprestimo' not in colunas:
        cursor.execute("ALTER TABLE fluxo_caixa ADD COLUMN credor_emprestimo TEXT")
    if 'juros_emprestimo' not in colunas:
        cursor.execute("ALTER TABLE fluxo_caixa ADD COLUMN juros_emprestimo REAL DEFAULT 0.0")
    if 'data_quitacao_acordada' not in colunas:
        cursor.execute("ALTER TABLE fluxo_caixa ADD COLUMN data_quitacao_acordada TEXT")
        
    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------------------
# FUNÇÕES DE SUPORTE
# -------------------------------------------------------------------------
def get_config_fiscal():
    conn = sqlite3.connect('wearlub_database.db')
    df = pd.read_sql_query("SELECT * FROM configuracoes_fiscais ORDER BY id DESC LIMIT 1", conn)
    conn.close()
    return df.iloc[0] if not df.empty else None

def atualizar_saldos_e_config(regime, simples, pis, cofins, iss, irpj, csll, comissao, s_normal, s_saude):
    conn = sqlite3.connect('wearlub_database.db')
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE configuracoes_fiscais SET 
    regime_tributario=?, aliquota_simples=?, pis=?, cofins=?, iss=?, irpj=?, csll=?, comissao_padrao=?,
    saldo_inicial_normal=?, saldo_inicial_saude=?
    WHERE id = 1
    """, (regime, simples, pis, cofins, iss, irpj, csll, comissao, s_normal, s_saude))
    conn.commit()
    conn.close()

def inserir_movimentacao(tipo, categoria, cliente_id, func_id, desc, v_bruto, v_imp, v_com, v_liq, nf, dt_ven, dt_pag, status, d_saude, origem='Conta Normal', credor=None, juros=0.0, dt_quit=None):
    conn = sqlite3.connect('wearlub_database.db')
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO fluxo_caixa 
    (tipo, categoria, cliente_id, funcionario_id, descricao, valor_bruto, deducoes_impostos, comissao, valor_liquido, nf_numero, data_vencimento, data_pagamento, status, destino_saude, origem_conta, credor_emprestimo, juros_emprestimo, data_quitacao_acordada)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (tipo, categoria, cliente_id, func_id, desc, v_bruto, v_imp, v_com, v_liq, nf, dt_ven, dt_pag, status, d_saude, origem, credor, juros, dt_quit))
    conn.commit()
    conn.close()

def get_dados_fluxo():
    conn = sqlite3.connect('wearlub_database.db')
    df = pd.read_sql_query("""
        SELECT f.*, c.nome as nome_cliente, func.nome as nome_funcionario 
        FROM fluxo_caixa f
        LEFT JOIN clientes c ON f.cliente_id = c.id
        LEFT JOIN funcionarios func ON f.funcionario_id = func.id
        ORDER BY f.data_vencimento ASC
    """, conn)
    conn.close()
    return df

# Menu Lateral
menu = st.sidebar.radio(
    "Navegação Wearlub",
    ["📊 Painel Financeiro", "🟢 Lançar Receita ou Empréstimo", "🔴 Lançar Despesa (Custos)", "🏥 Saúde da Empresa", "⚙️ Configurações & Saldos"]
)

cfg = get_config_fiscal()
df_fluxo = get_dados_fluxo()

# -------------------------------------------------------------------------
# MOTOR DE CÁLCULO DE SALDOS EM TEMPO REAL
# -------------------------------------------------------------------------
saldo_normal = cfg['saldo_inicial_normal']
saldo_saude = cfg['saldo_inicial_saude']

if not df_fluxo.empty:
    # Entradas pagas/recebidas (Serviços e Empréstimos de terceiros)
    entradas_pagas = df_fluxo[(df_fluxo['tipo'] == 'Entrada') & (df_fluxo['status'] == 'Pago/Recebido')]
    for _, row in entradas_pagas.iterrows():
        if row['categoria'] == 'Aporte / Empréstimo Recebido':
            # Empréstimos vão 100% inteiros para a conta normal da empresa (sem imposto)
            saldo_normal += row['valor_bruto']
        else:
            # Serviços comuns aplicam a regra da retenção da saúde da empresa
            v_saude_alocado = row['destino_saude']
            v_normal_alocado = row['valor_bruto'] - v_saude_alocado
            saldo_saude += v_saude_alocado
            saldo_normal += v_normal_alocado

    # Saídas (Custos / Despesas / Amortizações) pagas
    saidas_pagas = df_fluxo[(df_fluxo['tipo'] == 'Saída') & (df_fluxo['status'] == 'Pago/Recebido')]
    for _, row in saidas_pagas.iterrows():
        if row['origem_conta'] == 'Saúde da Empresa':
            saldo_saude -= row['valor_bruto']
        else:
            saldo_normal -= row['valor_bruto']

    # Transferências / Resgates da Saúde
    transferencias = df_fluxo[df_fluxo['tipo'] == 'Transferência']
    for _, row in transferencias.iterrows():
        saldo_saude -= row['valor_bruto']
        saldo_normal += row['valor_bruto']

    # Previsões futuras
    rec_p = df_fluxo[(df_fluxo['tipo'] == 'Entrada') & (df_fluxo['status'] == 'Pendente')]['valor_bruto'].sum()
    pag_p = df_fluxo[(df_fluxo['tipo'] == 'Saída') & (df_fluxo['status'] == 'Pendente')]['valor_bruto'].sum()
else:
    rec_p = pag_p = 0.0

# -------------------------------------------------------------------------
# ABA 5: CONFIGURAÇÕES E SALDOS INICIAIS
# -------------------------------------------------------------------------
if menu == "⚙️ Configurações & Saldos":
    st.subheader("⚙️ Configurações, Parâmetros Fiscais e Abertura de Caixa")
    with st.form("form_fiscal"):
        st.markdown("### 🏁 1. Saldos Iniciais (Abertura de Caixa)")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            s_init_normal = st.number_input("Saldo Atual na CONTA NORMAL / OPERACIONAL (R$)", min_value=0.0, value=float(cfg['saldo_inicial_normal']))
        with col_s2:
            s_init_saude = st.number_input("Saldo Atual na CONTA SAÚDE DA EMPRESA (R$)", min_value=0.0, value=float(cfg['saldo_inicial_saude']))
            
        st.markdown("### 📊 2. Impostos e Comissões de Serviços")
        regime = st.selectbox("Regime Tributário", ["Simples Nacional", "Lucro Presumido"], index=0 if cfg['regime_tributario'] == "Simples Nacional" else 1)
        col1, col2 = st.columns(2)
        with col1:
            simples = st.number_input("Simples Nacional (%)", min_value=0.0, value=float(cfg['aliquota_simples']))
            pis = st.number_input("PIS (%)", min_value=0.0, value=float(cfg['pis']))
            cofins = st.number_input("COFINS (%)", min_value=0.0, value=float(cfg['cofins']))
        with col2:
            iss = st.number_input("ISS (%)", min_value=0.0, value=float(cfg['iss']))
            irpj = st.number_input("IRPJ (%)", min_value=0.0, value=float(cfg['irpj']))
            csll = st.number_input("CSLL (%)", min_value=0.0, value=float(cfg['csll']))
        comissao = st.number_input("Comissão Padrão de Técnicos (%)", min_value=0.0, value=float(cfg['comissao_padrao']))
        
        if st.form_submit_button("Salvar Tudo"):
            atualizar_saldos_e_config(regime, simples, pis, cofins, iss, irpj, csll, comissao, s_init_normal, s_init_saude)
            st.success("Configurações atualizadas no servidor local Wearlub!")
            st.rerun()

# -------------------------------------------------------------------------
# ABA 1: PAINEL FINANCEIRO
# -------------------------------------------------------------------------
elif menu == "📊 Painel Financeiro":
    st.subheader("📊 Painel Geral de Controle Administrativo")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f'<div class="card"><div class="metric-title">💰 Saldo Conta Normal</div><div class="metric-value">R$ {saldo_normal:,.2f}</div></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="card"><div class="metric-title">🏥 Saúde da Empresa</div><div class="metric-value" style="color:#d9a304;">R$ {saldo_saude:,.2f}</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="card"><div class="metric-title">⏳ A Receber / Entrar</div><div class="metric-value">R$ {rec_p:,.2f}</div></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="card"><div class="metric-title">📉 Contas a Pagar Futuras</div><div class="metric-value">R$ {pag_p:,.2f}</div></div>', unsafe_allow_html=True)
    
    # Exibir quadro exclusivo se houver empréstimos ativos pendentes
    if not df_fluxo.empty:
        emp_ativos = df_fluxo[(df_fluxo['categoria'] == 'Aporte / Empréstimo Recebido') & (df_fluxo['status'] == 'Pago/Recebido')]
        if not emp_ativos.empty:
            st.markdown("### 🤝 Controle de Empréstimos e Injeções de Capital Externo")
            exib_emp = emp_ativos[['credor_emprestimo', 'valor_bruto', 'juros_emprestimo', 'data_quitacao_acordada', 'descricao']]
            exib_emp.columns = ['Origem / Quem Emprestou', 'Valor Recebido (R$)', 'Taxa de Juros (%)', 'Prazo de Quitação', 'Histórico/Obs']
            st.dataframe(exib_emp, use_container_width=True)

    # Vencimentos Críticos
    st.markdown("### ⚠️ Vencimentos Críticos (Próximos 3 dias ou Atrasados)")
    if not df_fluxo.empty:
        alerta = False
        hoje = datetime.now().date()
        for idx, row in df_fluxo[df_fluxo['status'] == 'Pendente'].iterrows():
            v_dt = datetime.strptime(row['data_vencimento'], '%Y-%m-%d').date()
            dias = (v_dt - hoje).days
            if dias < 0:
                st.error(f"🔴 ATRASADO HÁ {-dias} DIAS: {row['descricao']} | Conta: {row['origem_conta']} | Vencimento: {v_dt.strftime('%d/%m/%Y')} | Valor: R$ {row['valor_bruto']:,.2f}")
                alerta = True
            elif 0 <= dias <= 3:
                st.warning(f"🟡 VENCE EM {dias} DIAS: {row['descricao']} | Conta: {row['origem_conta']} | Vencimento: {v_dt.strftime('%d/%m/%Y')} | Valor: R$ {row['valor_bruto']:,.2f}")
                alerta = True
        if not alerta:
            st.success("🟢 Nenhum alerta técnico ou financeiro ativo.")
            
    if not df_fluxo.empty:
        st.markdown("---")
        st.markdown("### 📋 Histórico do Caixa da Empresa")
        exib_df = df_fluxo[['tipo', 'categoria', 'descricao', 'origem_conta', 'valor_bruto', 'data_vencimento', 'status']].copy()
        exib_df.columns = ['Tipo', 'Classificação', 'Descrição', 'Conta Destino/Origem', 'Valor (R$)', 'Vencimento', 'Status']
        st.dataframe(exib_df, use_container_width=True)

# -------------------------------------------------------------------------
# ABA 2: LANÇAR RECEITA OU EMPRÉSTIMO EXTERNO
# -------------------------------------------------------------------------
elif menu == "🟢 Lançar Receita ou Empréstimo":
    st.subheader("🟢 Entrada de Capital (Faturamento de Serviços ou Empréstimos Pessoais)")
    
    tipo_entrada = st.radio("Selecione o Tipo de Entrada de Dinheiro:", ["Faturamento de Serviço da Wearlub", "Empréstimo Pessoal / Aporte de Outra Empresa (Sem Nota Fiscal)"])
    
    if tipo_entrada == "Faturamento de Serviço da Wearlub":
        # Tela clássica de serviços com cálculo de impostos
        conn = sqlite3.connect('wearlub_database.db')
        cli_df = pd.read_sql_query("SELECT * FROM clientes", conn)
        func_df = pd.read_sql_query("SELECT * FROM funcionarios", conn)
        conn.close()
        
        cats = ["Serviço - Filtragem", "Serviço - Análise de Vibração", "Serviço - Termografia", "Serviço - Análise de Óleo", "Serviço - Balanceamento", "Serviço - Consultoria", "Serviço - Lubrificação Industrial", "Venda - Maquinários de Filtragem", "Venda - Filtros", "Venda - Lubrificantes"]
        
        with st.form("form_servico"):
            col1, col2 = st.columns(2)
            with col1:
                cli = st.selectbox("Cliente Atendido", cli_df['nome'].tolist() if not cli_df.empty else ["Nenhum Cliente Cadastrado"])
                cat = st.selectbox("Tipo de Serviço Técnico", cats)
                nf = st.text_input("Número da Nota Fiscal (NF-e)")
                v_bruto = st.number_input("Valor Bruto Fechado (R$)", min_value=0.0, value=10000.0)
            with col2:
                tec = st.selectbox("Responsável Técnico", func_df['nome'].tolist() if not func_df.empty else ["Nenhum Funcionário Cadastrado"])
                dt_v = st.date_input("Vencimento do Boleto", datetime.now() + timedelta(days=30))
                opcao_s = st.radio("Blindagem para Saúde da Empresa:", ["0% (Fica tudo no Caixa Livre)", "5% Retenção", "10% Retenção", "100% (Reter Lucro Líquido Integral)"])
                status = st.selectbox("Status Atual", ["Pendente", "Pago/Recebido"])
                
            if st.form_submit_button("Confirmar Cadastro do Serviço"):
                # Cálculo automático cascata
                imp = v_bruto * (cfg['aliquota_simples']/100.0) if cfg['regime_tributario'] == "Simples Nacional" else v_bruto * ((cfg['pis']+cfg['cofins']+cfg['iss']+cfg['irpj']+cfg['csll'])/100.0)
                com = v_bruto * (cfg['comissao_padrao']/100.0)
                liq = v_bruto - imp - com
                p = 0.0 if "0%" in opcao_s else (0.05 if "5%" in opcao_s else (0.10 if "10%" in opcao_s else 1.0))
                v_saude = liq * p
                
                dt_p = datetime.now().strftime('%Y-%m-%d') if status == "Pago/Recebido" else None
                inserir_movimentacao('Entrada', cat, None, None, f"Faturamento {cat} - NF {nf}", v_bruto, imp, com, liq, nf, dt_v.strftime('%Y-%m-%d'), dt_p, status, v_saude, origem='Conta Normal')
                st.success("Faturamento de engenharia registrado e provisionado!")
                
    else:
        # NOVA FUNCIONALIDADE: EMPRÉSTIMO EXTERNO
        with st.form("form_emprestimo_pessoal"):
            st.markdown("⚠️ **Dinheiro de Empréstimo:** Este valor entra direto e 100% integral na sua **Conta Normal** para fluxo operacional. Não sofre deduções de impostos corporativos ou comissões.")
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                credor = st.text_input("De quem foi o empréstimo? (Nome do amigo, empresário ou empresa)", placeholder="Ex: Clodoaldo (Conta Pessoal), Amigo Empresário X, Banco Y")
                v_emp = st.number_input("Qual o valor total recebido? (R$)", min_value=0.0, value=5000.0)
                status_e = st.selectbox("O dinheiro já caiu na conta da empresa?", ["Pago/Recebido", "Pendente"])
            with col_e2:
                juros = st.number_input("Taxa de Juros Combinada (% total ou mensal)", min_value=0.0, value=0.0, help="Deixe 0 se foi empréstimo amigo sem juros.")
                dt_q = st.date_input("Data combinada para pagamento/quitação", datetime.now() + timedelta(days=90))
                desc_e = st.text_input("Observações / Detalhes adicionais", placeholder="Ex: Empréstimo para cobrir quebra de veículo até receber medição")
                
            if st.form_submit_button("Confirmar Entrada de Empréstimo"):
                if credor:
                    dt_p = datetime.now().strftime('%Y-%m-%d') if status_e == "Pago/Recebido" else None
                    inserir_movimentacao(
                        tipo='Entrada',
                        categoria='Aporte / Empréstimo Recebido',
                        cliente_id=None,
                        funcionario_id=None,
                        descricao=f"Empréstimo recebido de {credor}",
                        v_bruto=v_emp,
                        deducoes_impostos=0.0,
                        comissao=0.0,
                        v_liquido=v_emp,
                        nf_numero="SEM NF (EMPRÉSTIMO)",
                        dt_ven=datetime.now().strftime('%Y-%m-%d'),
                        dt_pag=dt_p,
                        status=status_e,
                        d_saude=0.0,
                        origem='Conta Normal',
                        credor=credor,
                        juros=juros,
                        dt_quit=dt_q.strftime('%Y-%m-%d')
                    )
                    st.success(f"Empréstimo de {credor} registrado! O capital foi injetado na Conta Normal.")
                else:
                    st.error("Por favor, preencha o nome de quem emprestou o dinheiro.")

# -------------------------------------------------------------------------
# ABA 3: RETIRADAS / DESPESAS / CLASSIFICAÇÃO DE CUSTOS
# -------------------------------------------------------------------------
elif menu == "🔴 Lançar Despesa (Custos)":
    st.subheader("🔴 Nova Retirada, Custo ou Pagamento")
    
    # Classificação detalhada solicitada pelo cliente
    cats_saida = [
        "Custo Fixo - Aluguel / Escritório", 
        "Custo Fixo - Salários da Equipe",
        "Custo Fixo - Pró-labore",
        "Custo Variável - Combustível", 
        "Custo Variável - Transporte / Viagem de Campo", 
        "Custo Variável - Insumos (Filtros, Óleos, Graxas)", 
        "Imprevisto - Quebra de Carros / Manutenção Frota",
        "Imprevisto - Gastos Extras de Campo",
        "Impostos e Taxas Federais/Estaduais", 
        "Amortização / Pagamento de Empréstimo Pessoal"
    ]
    
    with st.form("form_saida"):
        col1, col2 = st.columns(2)
        with col1:
            origem_escolhida = st.selectbox("💳 DE QUAL CONTA SERÁ RETIRADO?", ["Conta Normal", "Saúde da Empresa"])
            cat = st.selectbox("Classificação Detalhada do Gasto", cats_saida)
            desc = st.text_input("Descrição do Motivo", placeholder="Ex: Conserto do parachoque da Van de campo após quebra")
        with col2:
            v_gasto = st.number_input("Valor Pago (R$)", min_value=0.0)
            dt_v = st.date_input("Data do Vencimento / Pagamento", datetime.now())
            status = st.selectbox("Status do Pagamento", ["Pago/Recebido", "Pendente"])
            
        if st.form_submit_button("Confirmar Lançamento de Despesa"):
            dt_p = datetime.now().strftime('%Y-%m-%d') if status == "Pago/Recebido" else None
            inserir_movimentacao('Saída', cat, None, None, desc, v_gasto, 0.0, 0.0, v_gasto, "", dt_v.strftime('%Y-%m-%d'), dt_p, status, 0.0, origem=origem_escolhida)
            st.success(f"Despesa/Custo lançado com sucesso com retirada da {origem_escolhida}!")

# -------------------------------------------------------------------------
# ABA 4: SAÚDE DA EMPRESA & RESGATE
# -------------------------------------------------------------------------
elif menu == "🏥 Saúde da Empresa":
    st.subheader("🏥 Fundo de Emergência Blindado & Resgates")
    
    st.markdown(f"""
    <div style="background-color: white; padding: 20px; border-radius:8px; border-left:6px solid #F2B705; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
        <span style="color:gray; font-size:13px; font-weight:bold;">🏥 RECURSOS TOTAIS DISPONÍVEIS NA SAÚDE DA EMPRESA</span>
        <h2 style="color: #212121; margin:5px 0;">R$ {saldo_saude:,.2f}</h2>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 🔄 Resgatar / Transferir Cachê para a Conta Normal")
    
    with st.form("form_transferencia"):
        v_transf = st.number_input("Valor do Resgate (R$)", min_value=0.0, max_value=max(0.0, saldo_saude))
        motivo_transf = st.text_input("Motivo do Resgate / Destinação", placeholder="Ex: Transferência de cachê livre para fluxo operacional")
        
        if st.form_submit_button("Executar Resgate para Conta Normal"):
            if v_transf > 0:
                inserir_movimentacao(
                    tipo='Transferência', categoria='Resgate Emergencial', cliente_id=None, funcionario_id=None,
                    descricao=f"Resgate Saúde -> Conta Normal: {motivo_transf}", v_bruto=v_transf, deducoes_impostos=0.0, comissao=0.0, valor_liquido=v_transf,
                    nf_numero="", dt_ven=datetime.now().strftime('%Y-%m-%d'), dt_pag=datetime.now().strftime('%Y-%m-%d'), status='Pago/Recebido', d_saude=0.0, origem='Saúde da Empresa'
                )
                st.success("Resgate efetuado! O valor saiu da Saúde e foi injetado na Conta Normal.")
                st.rerun()
