from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3, os, json
from functools import wraps
from datetime import datetime, timedelta, date

app = Flask(__name__)
app.secret_key = 'wearlub_secret_2026'

DB = os.path.join(os.path.dirname(__file__), 'wearlub_database.db')

# ─── DB ───────────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL, login TEXT NOT NULL UNIQUE,
        senha TEXT NOT NULL, perfil TEXT DEFAULT 'usuario')""")
    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO usuarios (nome,login,senha,perfil) VALUES (?,?,?,?)",
                  ('Clodoaldo','CLODOALDO','123456','admin'))
    c.execute("""CREATE TABLE IF NOT EXISTS configuracoes_fiscais (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        regime_tributario TEXT, aliquota_simples REAL DEFAULT 0,
        pis REAL DEFAULT 0.65, cofins REAL DEFAULT 3.0,
        iss REAL DEFAULT 5.0, irpj REAL DEFAULT 1.2,
        csll REAL DEFAULT 1.08, comissao_padrao REAL DEFAULT 5.0,
        saldo_inicial_normal REAL DEFAULT 0,
        saldo_inicial_saude  REAL DEFAULT 0)""")
    c.execute("SELECT COUNT(*) FROM configuracoes_fiscais")
    if c.fetchone()[0] == 0:
        c.execute("""INSERT INTO configuracoes_fiscais
            (regime_tributario,aliquota_simples,pis,cofins,iss,irpj,csll,comissao_padrao)
            VALUES ('Lucro Presumido',0,0.65,3.0,5.0,1.2,1.08,5.0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL, cnpj TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS funcionarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL, cargo TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS fluxo_caixa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT, categoria TEXT, cliente_id INTEGER, funcionario_id INTEGER,
        descricao TEXT, valor_bruto REAL, deducoes_impostos REAL DEFAULT 0,
        comissao REAL DEFAULT 0, valor_liquido REAL,
        nf_numero TEXT, data_vencimento TEXT, data_pagamento TEXT,
        status TEXT, destino_saude REAL DEFAULT 0,
        origem_conta TEXT DEFAULT 'Conta Normal',
        credor_emprestimo TEXT, juros_emprestimo REAL DEFAULT 0,
        data_quitacao_acordada TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS categorias_receita (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE,
        tipo TEXT DEFAULT 'Serviço')""")
    c.execute("SELECT COUNT(*) FROM categorias_receita")
    if c.fetchone()[0] == 0:
        cats = ['Serviço - Filtragem Industrial','Serviço - Análise de Vibração',
            'Serviço - Termografia','Serviço - Análise de Óleo',
            'Serviço - Balanceamento','Serviço - Consultoria',
            'Serviço - Lubrificação Industrial',
            'Venda - Maquinários de Filtragem',
            'Venda - Filtros e Elementos','Venda - Lubrificantes e Óleos',
            'Empréstimo / Aporte']
        for cat in cats:
            if cat.startswith('Venda'):
                tipo = 'Venda'
            elif cat.startswith('Empréstimo'):
                tipo = 'Outros'
            else:
                tipo = 'Serviço'
            c.execute("INSERT INTO categorias_receita (nome,tipo) VALUES (?,?)", (cat, tipo))
    for col, tp in [('credor_emprestimo','TEXT'),
                    ('juros_emprestimo','REAL DEFAULT 0'),
                    ('data_quitacao_acordada','TEXT')]:
        try: c.execute(f"ALTER TABLE fluxo_caixa ADD COLUMN {col} {tp}")
        except: pass
    # Garante que Empréstimo / Aporte existe nas categorias
    try:
        c.execute("INSERT OR IGNORE INTO categorias_receita (nome,tipo) VALUES ('Empréstimo / Aporte','Outros')")
    except: pass
    # ─── PROSPECÇÃO ───────────────────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS prospeccao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa TEXT NOT NULL,
        num_proposta TEXT,
        contato TEXT NOT NULL,
        telefone TEXT,
        email TEXT,
        status TEXT DEFAULT 'Enviada',
        responsavel TEXT NOT NULL,
        data_envio TEXT,
        servicos TEXT,
        valor_total REAL DEFAULT 0,
        observacoes TEXT,
        criado_em TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit(); conn.close()

init_db()

# ─── AUTH ─────────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def deco(*a, **kw):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        return f(*a, **kw)
    return deco

# ─── HELPERS ──────────────────────────────────────────────────────────────────
CATEGORIAS_RECEITA = [
    'Serviço - Filtragem Industrial','Serviço - Análise de Vibração',
    'Serviço - Termografia','Serviço - Análise de Óleo',
    'Serviço - Balanceamento','Serviço - Consultoria',
    'Serviço - Lubrificação Industrial',
    'Venda - Maquinários de Filtragem',
    'Venda - Filtros e Elementos','Venda - Lubrificantes e Óleos',
]
CATEGORIAS_DESPESA = [
    'Custo Fixo - Aluguel / Escritório',
    'Custo Fixo - Salários da Equipe',
    'Custo Fixo - Pró-labore',
    'Custo Variável - Combustível',
    'Custo Variável - Transporte / Viagem de Campo',
    'Custo Variável - Insumos (Filtros, Óleos, Graxas)',
    'Imprevisto - Manutenção de Frota / Veículos',
    'Imprevisto - Gastos Extras de Campo',
    'Impostos e Taxas Federais / Estaduais',
    'Amortização / Pagamento de Empréstimo',
]
CARGOS = [
    'Técnico de Lubrificação','Engenheiro de Lubrificação',
    'Técnico de Filtragem','Técnico de Análise de Óleo',
    'Técnico de Vibração e Termografia','Coordenador Técnico',
    'Comercial / Vendas','Administrativo','Outro',
]


def to_float(v):
    """Converte '5.000,00' ou '5000.00' ou '5000' para float."""
    v = str(v or '0').strip()
    # formato BR: tem ponto de milhar e vírgula decimal
    if ',' in v:
        v = v.replace('.', '').replace(',', '.')
    return float(v or 0)

def get_cfg():
    conn = get_db()
    cfg = conn.execute("SELECT * FROM configuracoes_fiscais ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return cfg

def calcular_saldos():
    cfg  = get_cfg()
    conn = get_db()
    rows = conn.execute("SELECT * FROM fluxo_caixa").fetchall()
    conn.close()
    sn = float(cfg['saldo_inicial_normal'] or 0)
    ss = float(cfg['saldo_inicial_saude']  or 0)
    rp = pp = 0.0
    for r in rows:
        if r['tipo'] == 'Entrada' and r['status'] == 'Pago/Recebido':
            if r['categoria'] == 'Aporte / Empréstimo Recebido':
                sn += r['valor_bruto']
            else:
                ss += (r['destino_saude'] or 0)
                sn += r['valor_bruto'] - (r['destino_saude'] or 0)
        elif r['tipo'] == 'Saída' and r['status'] == 'Pago/Recebido':
            if r['origem_conta'] == 'Saúde da Empresa': ss -= r['valor_bruto']
            else: sn -= r['valor_bruto']
        elif r['tipo'] == 'Transferência':
            ss -= r['valor_bruto']; sn += r['valor_bruto']
        elif r['tipo'] == 'Entrada' and r['status'] == 'Pendente':
            rp += r['valor_bruto']
        elif r['tipo'] == 'Saída' and r['status'] == 'Pendente':
            pp += r['valor_bruto']
    return sn, ss, rp, pp

def get_alertas():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM fluxo_caixa WHERE status='Pendente' ORDER BY data_vencimento"
    ).fetchall()
    conn.close()
    alertas = []
    hoje = date.today()
    for r in rows:
        try:
            dt = datetime.strptime(r['data_vencimento'], '%Y-%m-%d').date()
            dias = (dt - hoje).days
            if dias < 0:
                alertas.append({'classe':'alert-danger','icone':'fa-circle-xmark',
                    'texto': f"ATRASADO {-dias}d: {r['descricao']} | {r['origem_conta']} | {dt.strftime('%d/%m/%Y')} | R$ {r['valor_bruto']:,.2f}"})
            elif dias <= 3:
                alertas.append({'classe':'alert-warning','icone':'fa-triangle-exclamation',
                    'texto': f"VENCE EM {dias}d: {r['descricao']} | {r['origem_conta']} | {dt.strftime('%d/%m/%Y')} | R$ {r['valor_bruto']:,.2f}"})
        except: pass
    return alertas

# ─── LOGIN / LOGOUT ───────────────────────────────────────────────────────────
@app.route('/', methods=['GET','POST'])
@app.route('/login', methods=['GET','POST'])
def login():
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))
    erro = None
    if request.method == 'POST':
        u = request.form.get('usuario','').strip()
        s = request.form.get('senha','').strip()
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM usuarios WHERE login=? AND senha=?", (u,s)
        ).fetchone()
        conn.close()
        if user:
            session['usuario_id']     = user['id']
            session['usuario_nome']   = user['nome']
            session['usuario_perfil'] = user['perfil']
            return redirect(url_for('dashboard'))
        erro = 'Usuário ou senha inválidos.'
    return render_template('login.html', erro=erro, ano=date.today().year)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─── DASHBOARD ────────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    sn, ss, rp, pp = calcular_saldos()
    conn = get_db()
    ultimos = conn.execute(
        "SELECT * FROM fluxo_caixa ORDER BY id DESC LIMIT 15"
    ).fetchall()
    emprestimos = conn.execute(
        "SELECT * FROM fluxo_caixa WHERE categoria='Aporte / Empréstimo Recebido' AND status='Pago/Recebido'"
    ).fetchall()
    conn.close()
    return render_template('dashboard.html',
        saldo_normal=sn, saldo_saude=ss,
        a_receber=rp, a_pagar=pp,
        alertas=get_alertas(),
        ultimos=ultimos,
        emprestimos=emprestimos)

# ─── FLUXO DE CAIXA ───────────────────────────────────────────────────────────
@app.route('/financeiro/fluxo')
@login_required
def fluxo_caixa():
    conn = get_db()
    rows = conn.execute("SELECT * FROM fluxo_caixa ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('fluxo_caixa.html', lancamentos=rows)

# ─── RECEITA ──────────────────────────────────────────────────────────────────
@app.route('/financeiro/receita', methods=['GET','POST'])
@login_required
def receita():
    cfg = get_cfg()
    if request.method == 'POST':
        tipo_ent = request.form.get('tipo_entrada','servico')
        conn = get_db(); c = conn.cursor()

        if tipo_ent == 'servico':
            cat     = request.form.get('categoria','')
            nf      = request.form.get('nf_numero','')
            v_bruto = to_float(request.form.get('valor_bruto', '0'))
            dt_ven  = request.form.get('data_vencimento','')
            blind   = to_float(request.form.get('blindagem', '0'))
            status  = request.form.get('status','Pendente')
            desc    = request.form.get('descricao','')

            imp_pct = cfg['pis']+cfg['cofins']+cfg['iss']+cfg['irpj']+cfg['csll']
            imp = v_bruto * (imp_pct/100)
            com = v_bruto * (cfg['comissao_padrao']/100)
            liq = v_bruto - imp - com
            v_saude = liq * (blind/100)
            dt_pag  = date.today().isoformat() if status == 'Pago/Recebido' else None

            c.execute("""INSERT INTO fluxo_caixa
                (tipo,categoria,descricao,valor_bruto,deducoes_impostos,comissao,
                 valor_liquido,nf_numero,data_vencimento,data_pagamento,
                 status,destino_saude,origem_conta)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'Conta Normal')""",
                ('Entrada',cat,desc or f"{cat} - NF {nf}",
                 v_bruto,imp,com,liq,nf,dt_ven,dt_pag,status,v_saude))
        else:
            credor  = request.form.get('credor','')
            v_bruto = to_float(request.form.get('valor_bruto', '0'))
            juros   = float(request.form.get('juros',0) or 0)
            dt_quit = request.form.get('data_quitacao','')
            status  = request.form.get('status','Pago/Recebido')
            desc    = request.form.get('descricao','')
            dt_pag  = date.today().isoformat() if status == 'Pago/Recebido' else None

            c.execute("""INSERT INTO fluxo_caixa
                (tipo,categoria,descricao,valor_bruto,deducoes_impostos,comissao,
                 valor_liquido,nf_numero,data_vencimento,data_pagamento,
                 status,destino_saude,origem_conta,
                 credor_emprestimo,juros_emprestimo,data_quitacao_acordada)
                VALUES (?,?,?,?,0,0,?,?,?,?,?,0,'Conta Normal',?,?,?)""",
                ('Entrada','Aporte / Empréstimo Recebido',
                 f"Empréstimo de {credor}",v_bruto,v_bruto,
                 'SEM NF',date.today().isoformat(),dt_pag,
                 status,credor,juros,dt_quit))
        conn.commit(); conn.close()
        flash('Lançamento registrado com sucesso!','success')
        return redirect(url_for('dashboard'))

    conn2 = get_db()
    cats_db = [r['nome'] for r in conn2.execute("SELECT nome FROM categorias_receita ORDER BY tipo,nome").fetchall()]
    conn2.close()
    hoje_30 = (date.today() + timedelta(days=30)).isoformat()
    hoje_90 = (date.today() + timedelta(days=90)).isoformat()
    return render_template('receita.html',
        cfg=cfg,
        categorias_receita=cats_db,
        hoje_30=hoje_30, hoje_90=hoje_90)

# ─── DESPESA ──────────────────────────────────────────────────────────────────
@app.route('/financeiro/despesa', methods=['GET','POST'])
@login_required
def despesa():
    if request.method == 'POST':
        origem  = request.form.get('origem_conta','Conta Normal')
        cat     = request.form.get('categoria','')
        desc    = request.form.get('descricao','')
        v       = to_float(request.form.get('valor_bruto', '0'))
        dt_ven  = request.form.get('data_vencimento','')
        status  = request.form.get('status','Pago/Recebido')
        dt_pag  = date.today().isoformat() if status == 'Pago/Recebido' else None

        conn = get_db()
        conn.execute("""INSERT INTO fluxo_caixa
            (tipo,categoria,descricao,valor_bruto,deducoes_impostos,comissao,
             valor_liquido,nf_numero,data_vencimento,data_pagamento,
             status,destino_saude,origem_conta)
            VALUES (?,?,?,?,0,0,?,?,?,?,?,0,?)""",
            ('Saída',cat,desc,v,v,'',dt_ven,dt_pag,status,origem))
        conn.commit(); conn.close()
        flash('Despesa lançada com sucesso!','success')
        return redirect(url_for('dashboard'))

    return render_template('despesa.html',
        categorias_despesa=CATEGORIAS_DESPESA,
        hoje=date.today().isoformat())

# ─── SAÚDE ────────────────────────────────────────────────────────────────────
@app.route('/financeiro/saude', methods=['GET','POST'])
@login_required
def saude():
    sn, ss, _, _ = calcular_saldos()
    if request.method == 'POST':
        v      = float(request.form.get('valor',0) or 0)
        motivo = request.form.get('motivo','')
        if v > 0 and v <= ss:
            conn = get_db()
            conn.execute("""INSERT INTO fluxo_caixa
                (tipo,categoria,descricao,valor_bruto,deducoes_impostos,comissao,
                 valor_liquido,nf_numero,data_vencimento,data_pagamento,
                 status,destino_saude,origem_conta)
                VALUES ('Transferência','Resgate Emergencial',?,?,0,0,?,'',?,?,'Pago/Recebido',0,'Saúde da Empresa')""",
                (f"Resgate Saúde → Normal: {motivo}", v, v,
                 date.today().isoformat(), date.today().isoformat()))
            conn.commit(); conn.close()
            flash('Resgate efetuado com sucesso!','success')
            return redirect(url_for('saude'))
        else:
            flash('Valor inválido ou maior que o saldo disponível.','danger')
    return render_template('saude.html', saldo_saude=ss, saldo_normal=sn)

# ─── CONFIGURAÇÕES ────────────────────────────────────────────────────────────
@app.route('/configuracoes', methods=['GET','POST'])
@login_required
def configuracoes():
    if request.method == 'POST':
        conn = get_db()
        conn.execute("""UPDATE configuracoes_fiscais SET
            regime_tributario=?,aliquota_simples=?,pis=?,cofins=?,
            iss=?,irpj=?,csll=?,comissao_padrao=?,
            saldo_inicial_normal=?,saldo_inicial_saude=?
            WHERE id=1""",
            (request.form.get('regime'),
             to_float(request.form.get('simples', '0')),
             to_float(request.form.get('pis', '0')),
             to_float(request.form.get('cofins', '0')),
             to_float(request.form.get('iss', '0')),
             to_float(request.form.get('irpj', '0')),
             to_float(request.form.get('csll', '0')),
             to_float(request.form.get('comissao', '0')),
             to_float(request.form.get('saldo_normal', '0')),
             to_float(request.form.get('saldo_saude', '0'))))
        conn.commit(); conn.close()
        flash('Configurações salvas!','success')
        return redirect(url_for('configuracoes'))
    return render_template('configuracoes.html', cfg=get_cfg())

# ─── CLIENTES ─────────────────────────────────────────────────────────────────
@app.route('/cadastros/clientes')
@login_required
def clientes():
    conn = get_db()
    rows = conn.execute("SELECT * FROM clientes ORDER BY nome").fetchall()
    conn.close()
    return render_template('clientes.html', clientes=rows)

@app.route('/cadastros/clientes/novo', methods=['GET','POST'])
@login_required
def cliente_novo():
    if request.method == 'POST':
        nome = request.form.get('nome','').strip()
        cnpj = request.form.get('cnpj','').strip()
        if nome:
            conn = get_db()
            conn.execute("INSERT INTO clientes (nome,cnpj) VALUES (?,?)", (nome,cnpj))
            conn.commit(); conn.close()
            flash(f'Cliente {nome} cadastrado!','success')
        return redirect(url_for('clientes'))
    return render_template('cliente_form.html', c=None)

@app.route('/cadastros/clientes/editar/<int:id>', methods=['GET','POST'])
@login_required
def cliente_editar(id):
    conn = get_db()
    if request.method == 'POST':
        conn.execute("UPDATE clientes SET nome=?,cnpj=? WHERE id=?",
                     (request.form.get('nome'),request.form.get('cnpj'),id))
        conn.commit(); conn.close()
        flash('Cliente atualizado!','success')
        return redirect(url_for('clientes'))
    c = conn.execute("SELECT * FROM clientes WHERE id=?", (id,)).fetchone()
    conn.close()
    return render_template('cliente_form.html', c=c)

@app.route('/cadastros/clientes/excluir/<int:id>', methods=['POST'])
@login_required
def cliente_excluir(id):
    conn = get_db()
    conn.execute("DELETE FROM clientes WHERE id=?", (id,))
    conn.commit(); conn.close()
    flash('Cliente excluído.','warning')
    return redirect(url_for('clientes'))

# ─── FUNCIONÁRIOS ─────────────────────────────────────────────────────────────
@app.route('/cadastros/funcionarios')
@login_required
def funcionarios():
    conn = get_db()
    rows = conn.execute("SELECT * FROM funcionarios ORDER BY nome").fetchall()
    conn.close()
    return render_template('funcionarios.html', funcionarios=rows)

@app.route('/cadastros/funcionarios/novo', methods=['GET','POST'])
@login_required
def funcionario_novo():
    if request.method == 'POST':
        nome  = request.form.get('nome','').strip()
        cargo = request.form.get('cargo','')
        if nome:
            conn = get_db()
            conn.execute("INSERT INTO funcionarios (nome,cargo) VALUES (?,?)", (nome,cargo))
            conn.commit(); conn.close()
            flash(f'{nome} cadastrado!','success')
        return redirect(url_for('funcionarios'))
    return render_template('funcionario_form.html', f=None, cargos=CARGOS)

@app.route('/cadastros/funcionarios/editar/<int:id>', methods=['GET','POST'])
@login_required
def funcionario_editar(id):
    conn = get_db()
    if request.method == 'POST':
        conn.execute("UPDATE funcionarios SET nome=?,cargo=? WHERE id=?",
                     (request.form.get('nome'),request.form.get('cargo'),id))
        conn.commit(); conn.close()
        flash('Atualizado!','success')
        return redirect(url_for('funcionarios'))
    f = conn.execute("SELECT * FROM funcionarios WHERE id=?", (id,)).fetchone()
    conn.close()
    return render_template('funcionario_form.html', f=f, cargos=CARGOS)

@app.route('/cadastros/funcionarios/excluir/<int:id>', methods=['POST'])
@login_required
def funcionario_excluir(id):
    conn = get_db()
    conn.execute("DELETE FROM funcionarios WHERE id=?", (id,))
    conn.commit(); conn.close()
    flash('Excluído.','warning')
    return redirect(url_for('funcionarios'))

# ─── USUÁRIOS ─────────────────────────────────────────────────────────────────
@app.route('/cadastros/usuarios')
@login_required
def usuarios():
    conn = get_db()
    rows = conn.execute("SELECT id,nome,login,perfil FROM usuarios ORDER BY nome").fetchall()
    conn.close()
    return render_template('usuarios.html', usuarios=rows)

@app.route('/cadastros/usuarios/novo', methods=['GET','POST'])
@login_required
def usuario_novo():
    if request.method == 'POST':
        nome   = request.form.get('nome','').strip()
        login_ = request.form.get('login','').strip()
        senha  = request.form.get('senha','').strip()
        perfil = request.form.get('perfil','usuario')
        try:
            conn = get_db()
            conn.execute("INSERT INTO usuarios (nome,login,senha,perfil) VALUES (?,?,?,?)",
                         (nome,login_,senha,perfil))
            conn.commit(); conn.close()
            flash(f'Usuário {nome} cadastrado!','success')
        except Exception as e:
            flash(f'Erro: {e}','danger')
        return redirect(url_for('usuarios'))
    return render_template('usuario_form.html', u=None)

@app.route('/cadastros/usuarios/editar/<int:id>', methods=['GET','POST'])
@login_required
def usuario_editar(id):
    conn = get_db()
    if request.method == 'POST':
        nome   = request.form.get('nome','').strip()
        login_ = request.form.get('login','').strip()
        senha  = request.form.get('senha','').strip()
        perfil = request.form.get('perfil','usuario')
        if senha:
            conn.execute("UPDATE usuarios SET nome=?,login=?,senha=?,perfil=? WHERE id=?",
                         (nome,login_,senha,perfil,id))
        else:
            conn.execute("UPDATE usuarios SET nome=?,login=?,perfil=? WHERE id=?",
                         (nome,login_,perfil,id))
        conn.commit(); conn.close()
        flash('Atualizado!','success')
        return redirect(url_for('usuarios'))
    u = conn.execute("SELECT * FROM usuarios WHERE id=?", (id,)).fetchone()
    conn.close()
    return render_template('usuario_form.html', u=u)

@app.route('/cadastros/usuarios/excluir/<int:id>', methods=['POST'])
@login_required
def usuario_excluir(id):
    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE id=?", (id,))
    conn.commit(); conn.close()
    flash('Excluído.','warning')
    return redirect(url_for('usuarios'))

# ─── DADOS PARA GRÁFICOS ──────────────────────────────────────────────────────
@app.route('/api/graficos')
@login_required
def api_graficos():
    import json
    from datetime import datetime
    conn = get_db()
    rows = conn.execute("SELECT * FROM fluxo_caixa WHERE status='Pago/Recebido'").fetchall()
    conn.close()

    # Receitas x Despesas por mês (últimos 6 meses)
    meses = {}
    for r in rows:
        try:
            dt = datetime.strptime(r['data_vencimento'], '%Y-%m-%d')
            chave = dt.strftime('%m/%Y')
            if chave not in meses:
                meses[chave] = {'receita': 0, 'despesa': 0}
            if r['tipo'] == 'Entrada':
                meses[chave]['receita'] += r['valor_bruto']
            elif r['tipo'] == 'Saída':
                meses[chave]['despesa'] += r['valor_bruto']
        except: pass

    meses_sorted = sorted(meses.items())[-6:]
    labels_bar   = [m[0] for m in meses_sorted]
    receitas_bar = [round(m[1]['receita'],2) for m in meses_sorted]
    despesas_bar = [round(m[1]['despesa'],2) for m in meses_sorted]

    # Pizza - categorias de despesa
    cats = {}
    for r in rows:
        if r['tipo'] == 'Saída':
            cat = r['categoria'] or 'Outros'
            cats[cat] = cats.get(cat, 0) + r['valor_bruto']
    cats_sorted = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:6]
    labels_pizza = [c[0].split(' - ')[-1] for c in cats_sorted]
    values_pizza = [round(c[1],2) for c in cats_sorted]

    # Saldos atual
    sn, ss, _, _ = calcular_saldos()

    return json.dumps({
        'labels_bar':   labels_bar,
        'receitas_bar': receitas_bar,
        'despesas_bar': despesas_bar,
        'labels_pizza': labels_pizza,
        'values_pizza': values_pizza,
        'saldo_normal': round(sn, 2),
        'saldo_saude':  round(ss, 2),
    })

# ─── EDITAR / EXCLUIR LANÇAMENTO ──────────────────────────────────────────────
@app.route('/financeiro/lancamento/editar/<int:id>', methods=['GET','POST'])
@login_required
def lancamento_editar(id):
    conn = get_db()
    if request.method == 'POST':
        cat     = request.form.get('categoria','')
        desc    = request.form.get('descricao','')
        # aceita vírgula como decimal: "5.000,00" -> 5000.00
        v_str   = request.form.get('valor_bruto','0').replace('.','').replace(',','.')
        v       = float(v_str or 0)
        dt_ven  = request.form.get('data_vencimento','')
        status  = request.form.get('status','Pendente')
        origem  = request.form.get('origem_conta','Conta Normal')
        dt_pag  = date.today().isoformat() if status == 'Pago/Recebido' else None
        conn.execute("""UPDATE fluxo_caixa SET
            categoria=?, descricao=?, valor_bruto=?, valor_liquido=?,
            data_vencimento=?, status=?, origem_conta=?, data_pagamento=?
            WHERE id=?""",
            (cat, desc, v, v, dt_ven, status, origem, dt_pag, id))
        conn.commit(); conn.close()
        flash('Lançamento atualizado com sucesso!', 'success')
        return redirect(url_for('fluxo_caixa'))
    l = conn.execute("SELECT * FROM fluxo_caixa WHERE id=?", (id,)).fetchone()
    conn.close()
    cats = CATEGORIAS_RECEITA if (l and l['tipo'] == 'Entrada') else CATEGORIAS_DESPESA
    return render_template('lancamento_editar.html', l=l, categorias=cats)

@app.route('/financeiro/lancamento/excluir/<int:id>', methods=['POST'])
@login_required
def lancamento_excluir(id):
    conn = get_db()
    conn.execute("DELETE FROM fluxo_caixa WHERE id=?", (id,))
    conn.commit(); conn.close()
    flash('Lançamento excluído.', 'warning')
    return redirect(url_for('fluxo_caixa'))


# ─── CATEGORIAS DE RECEITA ────────────────────────────────────────────────────
@app.route('/cadastros/categorias')
@login_required
def categorias():
    conn = get_db()
    cats = conn.execute("SELECT * FROM categorias_receita ORDER BY tipo,nome").fetchall()
    conn.close()
    return render_template('categorias.html', categorias=cats)

@app.route('/cadastros/categorias/nova', methods=['POST'])
@login_required
def categoria_nova():
    nome = request.form.get('nome','').strip()
    tipo = request.form.get('tipo','Serviço')
    if nome:
        try:
            conn = get_db()
            conn.execute("INSERT INTO categorias_receita (nome,tipo) VALUES (?,?)", (nome,tipo))
            conn.commit(); conn.close()
            flash(f'Categoria "{nome}" adicionada!','success')
        except:
            flash('Categoria já existe.','danger')
    return redirect(url_for('categorias'))

@app.route('/cadastros/categorias/excluir/<int:id>', methods=['POST'])
@login_required
def categoria_excluir(id):
    conn = get_db()
    conn.execute("DELETE FROM categorias_receita WHERE id=?", (id,))
    conn.commit(); conn.close()
    flash('Categoria removida.','warning')
    return redirect(url_for('categorias'))


# ─── PROSPECÇÃO ───────────────────────────────────────────────────────────────
STATUS_PROSP = ['Enviada','Em negociação','Aprovada','Reprovada','Aguardando retorno']

@app.route('/prospeccao')
@login_required
def prospeccao():
    conn = get_db()
    filtro_status = request.args.get('status','')
    filtro_resp   = request.args.get('resp','')
    filtro_busca  = request.args.get('busca','')
    filtro_de     = request.args.get('data_de','')
    filtro_ate    = request.args.get('data_ate','')
    q = "SELECT * FROM prospeccao WHERE 1=1"
    params = []
    if filtro_status:
        q += " AND status=?"; params.append(filtro_status)
    if filtro_resp:
        q += " AND responsavel=?"; params.append(filtro_resp)
    if filtro_busca:
        q += " AND (empresa LIKE ? OR contato LIKE ?)"; params += [f'%{filtro_busca}%']*2
    if filtro_de:
        q += " AND data_envio >= ?"; params.append(filtro_de)
    if filtro_ate:
        q += " AND data_envio <= ?"; params.append(filtro_ate)
    q += " ORDER BY id DESC"
    rows = conn.execute(q, params).fetchall()
    responsaveis = [r['responsavel'] for r in conn.execute(
        "SELECT DISTINCT responsavel FROM prospeccao ORDER BY responsavel").fetchall()]
    totais = conn.execute(
        "SELECT COUNT(*) as total, SUM(valor_total) as soma FROM prospeccao").fetchone()
    por_status = {s: conn.execute(
        "SELECT COUNT(*) FROM prospeccao WHERE status=?", (s,)).fetchone()[0]
        for s in STATUS_PROSP}
    conn.close()
    # Converte servicos JSON para lista em cada proposta
    propostas_list = []
    for row in rows:
        p = dict(row)
        try:
            svcs = json.loads(p['servicos'] or '[]')
            p['svcs_lista'] = svcs
            p['svcs_nomes'] = ', '.join(s['nome'] for s in svcs if s.get('nome'))
        except:
            p['svcs_lista'] = []
            p['svcs_nomes'] = ''
        propostas_list.append(p)
    return render_template('prospeccao.html',
        propostas=propostas_list, status_list=STATUS_PROSP,
        responsaveis=responsaveis,
        filtro_status=filtro_status, filtro_resp=filtro_resp, filtro_busca=filtro_busca,
        filtro_de=filtro_de, filtro_ate=filtro_ate,
        totais=totais, por_status=por_status)

@app.route('/prospeccao/nova', methods=['GET','POST'])
@login_required
def prospeccao_nova():
    if request.method == 'POST':
        import json
        svcs_nomes  = request.form.getlist('svc_nome')
        svcs_vals   = request.form.getlist('svc_valor')
        svcs = [{'nome': n, 'valor': float(v or 0)}
                for n, v in zip(svcs_nomes, svcs_vals) if n.strip()]
        valor_total = sum(s['valor'] for s in svcs)
        conn = get_db()
        conn.execute("""INSERT INTO prospeccao
            (empresa,num_proposta,contato,telefone,email,status,responsavel,
             data_envio,servicos,valor_total,observacoes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (request.form.get('empresa','').strip(),
             request.form.get('num_proposta','').strip(),
             request.form.get('contato','').strip(),
             request.form.get('telefone','').strip(),
             request.form.get('email','').strip(),
             request.form.get('status','Enviada'),
             request.form.get('responsavel','').strip(),
             request.form.get('data_envio',''),
             json.dumps(svcs, ensure_ascii=False),
             valor_total,
             request.form.get('observacoes','').strip()))
        conn.commit(); conn.close()
        flash('Proposta cadastrada com sucesso!','success')
        return redirect(url_for('prospeccao'))
    return render_template('prospeccao_form.html', p=None, status_list=STATUS_PROSP)

@app.route('/prospeccao/editar/<int:id>', methods=['GET','POST'])
@login_required
def prospeccao_editar(id):
    import json
    conn = get_db()
    if request.method == 'POST':
        svcs_nomes = request.form.getlist('svc_nome')
        svcs_vals  = request.form.getlist('svc_valor')
        svcs = [{'nome': n, 'valor': float(v or 0)}
                for n, v in zip(svcs_nomes, svcs_vals) if n.strip()]
        valor_total = sum(s['valor'] for s in svcs)
        conn.execute("""UPDATE prospeccao SET
            empresa=?,num_proposta=?,contato=?,telefone=?,email=?,status=?,
            responsavel=?,data_envio=?,servicos=?,valor_total=?,observacoes=?
            WHERE id=?""",
            (request.form.get('empresa','').strip(),
             request.form.get('num_proposta','').strip(),
             request.form.get('contato','').strip(),
             request.form.get('telefone','').strip(),
             request.form.get('email','').strip(),
             request.form.get('status','Enviada'),
             request.form.get('responsavel','').strip(),
             request.form.get('data_envio',''),
             json.dumps(svcs, ensure_ascii=False),
             valor_total,
             request.form.get('observacoes','').strip(),
             id))
        conn.commit(); conn.close()
        flash('Proposta atualizada!','success')
        return redirect(url_for('prospeccao'))
    row = conn.execute("SELECT * FROM prospeccao WHERE id=?", (id,)).fetchone()
    conn.close()
    p = dict(row) if row else None
    if p:
        try:
            p['svcs_lista'] = json.loads(p['servicos'] or '[]')
        except:
            p['svcs_lista'] = []
    return render_template('prospeccao_form.html', p=p, status_list=STATUS_PROSP)

@app.route('/prospeccao/excluir/<int:id>', methods=['POST'])
@login_required
def prospeccao_excluir(id):
    conn = get_db()
    conn.execute("DELETE FROM prospeccao WHERE id=?", (id,))
    conn.commit(); conn.close()
    flash('Proposta excluída.','warning')
    return redirect(url_for('prospeccao'))

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
