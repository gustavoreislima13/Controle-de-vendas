import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import sqlite3
import io
from datetime import datetime, date
from openai import OpenAI

# ==========================================
# 1. CONFIGURAÇÃO INICIAL
# ==========================================
st.set_page_config(page_title="CMG System Pro", layout="wide", page_icon="💎")

# ==========================================
# 2. SISTEMA DE TEMAS & CSS
# ==========================================
if "theme" not in st.session_state:
    st.session_state.theme = "Escuro"

# --- CSS BASE ---
CSS_BASE = """
<style>
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    div[data-testid="stTextInput"] input { font-size: 16px; padding: 10px; }
</style>
"""

# --- CSS CLARO ---
CSS_LIGHT = CSS_BASE + """
<style>
    .stApp { background-color: #F3F4F6; color: #111827; }
    section[data-testid="stSidebar"] { background-color: #FFFFFF; border-right: 1px solid #E5E7EB; }
    h1, h2, h3, h4, h5, h6, p, span, label { color: #111827 !important; }
    div[data-baseweb="input"], input { background-color: #FFFFFF !important; border-color: #9CA3AF !important; color: #000000 !important; }
    div[data-testid="stMetric"] { background-color: #FFFFFF; padding: 20px; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #E5E7EB; }
    div[data-testid="stMetricLabel"] label { color: #6B7280 !important; }
    div[data-testid="stMetricValue"] { color: #111827 !important; }
    div[data-testid="stDataFrame"] { background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; color: #000000 !important; }
    .stRadio label { color: #374151 !important; font-weight: 600; }
</style>
"""

# --- CSS ESCURO ---
CSS_DARK = CSS_BASE + """
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    section[data-testid="stSidebar"] { background-color: #171923; border-right: 1px solid #2D3748; }
    h1, h2, h3, h4, h5, h6, p, span, label { color: #FAFAFA !important; }
    div[data-baseweb="input"], input { background-color: #2D3748 !important; border-color: #4A5568 !important; color: #FFFFFF !important; }
    div[data-testid="stMetric"] { background-color: #262730; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border: 1px solid #4A5568; }
    div[data-testid="stMetricLabel"] label { color: #A0AEC0 !important; }
    div[data-testid="stMetricValue"] { color: #F7FAFC !important; }
    div[data-testid="stDataFrame"] { background-color: #1A202C; border: 1px solid #2D3748; border-radius: 12px; }
    .stRadio label { color: #E2E8F0 !important; font-weight: 600; }
</style>
"""

# ==========================================
# 3. BANCO DE DADOS
# ==========================================
DB_NAME = 'cmg_system.db'
BASE_DIR_ARQUIVOS = 'documentos_clientes'

if not os.path.exists(BASE_DIR_ARQUIVOS): os.makedirs(BASE_DIR_ARQUIVOS)

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, Nome TEXT, CPF TEXT, Email TEXT, Telefone TEXT, Data_Cadastro TEXT, Obs TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS consultores (id INTEGER PRIMARY KEY AUTOINCREMENT, Nome TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS bancos (id INTEGER PRIMARY KEY AUTOINCREMENT, Banco TEXT, Agencia TEXT, Conta TEXT)')
        
        # --- NOVA TABELA DE SERVIÇOS ---
        c.execute('CREATE TABLE IF NOT EXISTS servicos (id INTEGER PRIMARY KEY AUTOINCREMENT, Nome TEXT)')
        
        # Preenche serviços padrão se estiver vazia (primeira vez)
        c.execute("SELECT count(*) FROM servicos")
        if c.fetchone()[0] == 0:
            padroes = [("Limpeza Nome",), ("Score",), ("Consultoria",), ("Jurídico",)]
            c.executemany("INSERT INTO servicos (Nome) VALUES (?)", padroes)
        
        c.execute('CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)')
        
        c.execute('''CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, Data TEXT, Consultor TEXT, Cliente TEXT, CPF TEXT, 
            Servico TEXT, Valor REAL, Status_Pagamento TEXT, Conta_Recebimento TEXT, Obs TEXT, Docs TEXT, Email TEXT, Telefone TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, Data TEXT, Categoria TEXT, Descricao TEXT, Conta_Origem TEXT, Valor REAL
        )''')
        
        # Migrações e Metas Padrão
        for col in ["Email", "Telefone", "Obs", "Conta_Recebimento"]:
            try: c.execute(f"ALTER TABLE vendas ADD COLUMN {col} TEXT"); 
            except: pass
        try: c.execute("ALTER TABLE despesas ADD COLUMN Conta_Origem TEXT"); 
        except: pass
        try: c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('meta_mensal', '50000')")
        except: pass
        try: c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('meta_anual', '600000')")
        except: pass
        
        conn.commit()

init_db()

def run_query(query, params=()):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
    st.cache_data.clear()

@st.cache_data(ttl=3600, show_spinner=False)
def load_data(table_name):
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
    return df

def get_config(chave):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT valor FROM config WHERE chave=?", (chave,))
        res = c.fetchone()
        return float(res[0]) if res else 0.0

def set_config(chave, valor):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", (chave, str(valor)))
        conn.commit()
    st.cache_data.clear()

def update_full_table(df, table_name):
    with sqlite3.connect(DB_NAME) as conn:
        df.to_sql(table_name, conn, if_exists='replace', index=False)
    st.cache_data.clear()

def salvar_arquivos(arquivos, nome_cliente):
    if not arquivos: return 0
    safe_folder = "".join([c for c in nome_cliente if c.isalnum() or c in (' ', '_')]).strip().replace(" ", "_")
    path = os.path.join(BASE_DIR_ARQUIVOS, safe_folder)
    if not os.path.exists(path): os.makedirs(path)
    for arq in arquivos:
        with open(os.path.join(path, arq.name), "wb") as f:
            f.write(arq.getbuffer())
    return len(arquivos)

def converter_para_excel(dfs_dict):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for name, df in dfs_dict.items():
            df.to_excel(writer, index=False, sheet_name=name)
    return output.getvalue()

def chat_ia(df_v, df_d, user_msg, key):
    if not key: return "⚠️ Configure sua API Key."
    try:
        client = OpenAI(api_key=key)
        contexto = f"Vendas: {df_v.tail(5).to_string()}\nDespesas: {df_d.tail(5).to_string()}"
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": f"Analista financeiro. Contexto: {contexto}"}, {"role": "user", "content": user_msg}]
        )
        return resp.choices[0].message.content
    except Exception as e: return f"Erro IA: {e}"

# ==========================================
# 4. BARRA LATERAL
# ==========================================
with st.sidebar:
    st.title("💎 CMG Pro")
    st.markdown("Manager v20.0")
    
    st.markdown("### Menu")
    menu_options = [
        "📊 DASHBOARD", "🧮 PRECIFICAÇÃO", "📇 CRM", 
        "👥 VENDAS", "💰 FINANCEIRO", "⚙️ CONFIG", 
        "📂 ARQUIVOS", "🤖 I.A."
    ]
    escolha_menu = st.radio("Ir para:", menu_options, label_visibility="collapsed")
    st.divider()

    st.markdown("### 📅 Filtros")
    tipo_filtro = st.radio("Período:", ["Mês Atual", "Personalizado", "Todo Histórico"], label_visibility="collapsed")
    data_inicio, data_fim = None, None
    
    if tipo_filtro == "Mês Atual":
        hj = datetime.now()
        import calendar
        ultimo_dia = calendar.monthrange(hj.year, hj.month)[1]
        data_inicio, data_fim = date(hj.year, hj.month, 1), date(hj.year, hj.month, ultimo_dia)
        st.caption(f"🗓️ {data_inicio.strftime('%d/%m')} - {data_fim.strftime('%d/%m')}")
    elif tipo_filtro == "Personalizado":
        c1, c2 = st.columns(2)
        data_inicio = c1.date_input("De", value=date(datetime.now().year, datetime.now().month, 1))
        data_fim = c2.date_input("Até", value=datetime.now().date())

    st.divider()
    openai_key = ""
    try:
        if "OPENAI_API_KEY" in st.secrets: openai_key = st.secrets["OPENAI_API_KEY"]
    except: pass
    if not openai_key: openai_key = st.text_input("🔑 API Key", type="password")

# ==========================================
# 5. LÓGICA DE DADOS
# ==========================================
df_vendas_raw = load_data("vendas")
df_despesas_raw = load_data("despesas")
df_clientes_raw = load_data("clientes")
df_consultores = load_data("consultores")
df_bancos = load_data("bancos")
df_servicos = load_data("servicos") # CARREGA SERVIÇOS DO BANCO

meta_mensal = get_config('meta_mensal')
meta_anual = get_config('meta_anual')

df_vendas_raw['Data'] = pd.to_datetime(df_vendas_raw['Data'], errors='coerce').dt.date
df_despesas_raw['Data'] = pd.to_datetime(df_despesas_raw['Data'], errors='coerce').dt.date

if tipo_filtro != "Todo Histórico" and data_inicio and data_fim:
    df_vendas = df_vendas_raw[(df_vendas_raw['Data'] >= data_inicio) & (df_vendas_raw['Data'] <= data_fim)].copy()
    df_despesas = df_despesas_raw[(df_despesas_raw['Data'] >= data_inicio) & (df_despesas_raw['Data'] <= data_fim)].copy()
else:
    df_vendas = df_vendas_raw.copy()
    df_despesas = df_despesas_raw.copy()

# Listas Dinâmicas
lista_consultores = df_consultores["Nome"].tolist() if not df_consultores.empty else ["Geral"]
lista_bancos = df_bancos["Banco"].tolist() if not df_bancos.empty else ["Caixa Principal"]
lista_servicos = df_servicos["Nome"].tolist() if not df_servicos.empty else ["Geral"]

# TEMA CSS
if st.session_state.theme == "Claro":
    st.markdown(CSS_LIGHT, unsafe_allow_html=True)
    cor_grafico = ["#6366F1", "#3B82F6", "#10B981", "#F59E0B"]
    plotly_template = "plotly_white"
    txt_chart = "#111827"
else:
    st.markdown(CSS_DARK, unsafe_allow_html=True)
    cor_grafico = ["#E53E3E", "#F6E05E", "#4FD1C5", "#9F7AEA"]
    plotly_template = "plotly_dark"
    txt_chart = "white"

# ==========================================
# 6. ROTEAMENTO
# ==========================================

# --- DASHBOARD ---
if escolha_menu == "📊 DASHBOARD":
    st.markdown("## 📊 Visão Geral")
    termo_busca = st.text_input("🔍 Buscar rápido...", placeholder="Digite para filtrar os dados abaixo...")
    
    df_v = df_vendas.copy()
    if termo_busca:
        mask = df_v.astype(str).apply(lambda x: x.str.lower().str.contains(termo_busca.lower())).any(axis=1)
        df_v = df_v[mask]

    fat = df_v["Valor"].sum() if not df_v.empty else 0
    desp = df_despesas["Valor"].sum() if not df_despesas.empty else 0
    lucro = fat - desp
    ticket = fat / len(df_v) if len(df_v) > 0 else 0
    
    st.caption(f"Período: {tipo_filtro}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faturamento", f"R$ {fat:,.2f}")
    c2.metric("Lucro Líquido", f"R$ {lucro:,.2f}", delta=f"{(lucro/fat)*100:.1f}%" if fat>0 else "0%")
    c3.metric("Despesas", f"R$ {desp:,.2f}", delta="Saídas", delta_color="inverse")
    c4.metric("Ticket Médio", f"R$ {ticket:,.2f}")

    st.markdown("<br>", unsafe_allow_html=True)

    g1, g2 = st.columns([1, 2])
    with g1:
        st.markdown("**Mix de Serviços**")
        if not df_v.empty:
            fig_pie = px.pie(df_v, names="Servico", values="Valor", hole=0.7, color_discrete_sequence=cor_grafico, template=plotly_template)
            fig_pie.update_layout(showlegend=False, margin=dict(t=20, b=20, l=20, r=20), height=280, paper_bgcolor="rgba(0,0,0,0)")
            fig_pie.add_annotation(text=f"R${fat:,.0f}", showarrow=False, font_size=14, font_color=txt_chart)
            st.plotly_chart(fig_pie, use_container_width=True)
        else: st.info("Sem dados")
    with g2:
        st.markdown("**Evolução Financeira**")
        if not df_v.empty:
            daily = df_v.groupby("Data")["Valor"].sum().reset_index()
            fig_area = px.area(daily, x="Data", y="Valor", color_discrete_sequence=[cor_grafico[1]], template=plotly_template)
            fig_area.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=10, b=10, l=10, r=10), height=280)
            st.plotly_chart(fig_area, use_container_width=True)
        else: st.info("Sem dados")
    
    st.markdown("<br>", unsafe_allow_html=True)
    g3, g4 = st.columns([2, 1])
    with g3:
        st.markdown("**Fluxo de Caixa**")
        resumo = pd.DataFrame({"Tipo": ["Entradas", "Saídas"], "Valor": [fat, desp]})
        fig_bar = px.bar(resumo, x="Tipo", y="Valor", color="Tipo", color_discrete_map={"Entradas": cor_grafico[0], "Saídas": cor_grafico[3]}, template=plotly_template, text_auto='.2s')
        fig_bar.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=250, showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)
    with g4:
        st.markdown("**Meta Mensal**")
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number", value = fat, domain = {'x': [0, 1], 'y': [0, 1]},
            gauge = {'axis': {'range': [None, meta_mensal]}, 'bar': {'color': cor_grafico[2]}, 'bgcolor': "#2D3748" if st.session_state.theme == "Escuro" else "#E5E7EB"}
        ))
        fig_gauge.update_layout(height=250, margin=dict(t=30, b=10), paper_bgcolor="rgba(0,0,0,0)", font={'color': txt_chart})
        st.plotly_chart(fig_gauge, use_container_width=True)

# --- PRECIFICAÇÃO ---
elif escolha_menu == "🧮 PRECIFICAÇÃO":
    st.markdown("## 🧮 Calculadora")
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            custo = st.number_input("Custo (R$)", value=100.0)
            imposto = st.slider("Impostos (%)", 0, 30, 6)
            comissao = st.slider("Comissão (%)", 0, 30, 10)
            margem = st.slider("Margem (%)", 0, 100, 30)
    with c2:
        with st.container(border=True):
            soma = imposto + comissao + margem
            if soma >= 100: st.error("Margens > 100%")
            else:
                fator = (100 - soma) / 100
                preco_venda = custo / fator
                lucro_liq = preco_venda * (margem/100)
                st.metric("Sugerido", f"R$ {preco_venda:,.2f}")
                st.write(f"Lucro Líquido: R$ {lucro_liq:,.2f}")

# --- CRM ---
elif escolha_menu == "📇 CRM":
    st.markdown("## 📇 Clientes")
    busca_crm = st.text_input("🔍 Buscar Cliente...", placeholder="Nome ou CPF")
    
    df_c = df_clientes_raw.copy()
    if busca_crm:
        mask = df_c.astype(str).apply(lambda x: x.str.lower().str.contains(busca_crm.lower())).any(axis=1)
        df_c = df_c[mask]

    c1, c2 = st.columns([1, 2])
    with c1:
        with st.container(border=True):
            st.markdown("#### Cadastrar")
            with st.form("crm"):
                n = st.text_input("Nome*")
                cpf = st.text_input("CPF")
                email = st.text_input("Email")
                tel = st.text_input("Telefone")
                obs = st.text_area("Obs")
                if st.form_submit_button("Salvar"):
                    if n:
                        run_query("INSERT INTO clientes (Nome, CPF, Email, Telefone, Data_Cadastro, Obs) VALUES (?,?,?,?,?,?)", (n, cpf, email, tel, str(date.today()), obs))
                        st.success("Salvo!"); st.rerun()
                    else: st.error("Erro")
    with c2:
        st.markdown(f"#### Base ({len(df_c)})")
        if "Excluir" not in df_c.columns: df_c.insert(0, "Excluir", False)
        ed = st.data_editor(df_c, hide_index=True, use_container_width=True, column_config={"id": st.column_config.NumberColumn(disabled=True)})
        if st.button("💾 Atualizar CRM"):
            df_final = ed[ed["Excluir"]==False].drop(columns=["Excluir"])
            update_full_table(df_final, "clientes"); st.rerun()

# --- VENDAS ---
elif escolha_menu == "👥 VENDAS":
    st.markdown("## 👥 Vendas")
    busca_vendas = st.text_input("🔍 Filtrar Vendas...", placeholder="Cliente, Consultor...")
    
    df_v = df_vendas.copy()
    if busca_vendas:
        mask = df_v.astype(str).apply(lambda x: x.str.lower().str.contains(busca_vendas.lower())).any(axis=1)
        df_v = df_v[mask]
        
    c1, c2 = st.columns([1, 2])
    with c1:
        with st.container(border=True):
            st.markdown("#### Lançar")
            with st.form("venda"):
                cons = st.selectbox("Consultor", lista_consultores)
                
                # Campos do Cliente
                c_cli, c_cpf = st.columns(2)
                cli = c_cli.text_input("Cliente*")
                cpf = c_cpf.text_input("CPF")
                
                # NOVOS CAMPOS: EMAIL E TELEFONE
                c_email, c_tel = st.columns(2)
                email = c_email.text_input("Email")
                tel = c_tel.text_input("Telefone")
                
                # Serviço agora puxa da lista dinâmica
                serv = st.selectbox("Serviço", lista_servicos)
                
                val = st.number_input("Valor", min_value=0.0)
                
                c_stts, c_conta = st.columns(2)
                stt = c_stts.selectbox("Status", ["Pago Total", "Parcial", "Pendente"])
                cnt = c_conta.selectbox("Recebido em", lista_bancos)
                
                obs = st.text_area("Obs")
                docs = st.file_uploader("Docs", accept_multiple_files=True)
                
                if st.form_submit_button("Salvar"):
                    if cli:
                        qtd = salvar_arquivos(docs, cli)
                        run_query("INSERT INTO vendas (Data, Consultor, Cliente, CPF, Email, Telefone, Servico, Valor, Status_Pagamento, Conta_Recebimento, Obs, Docs) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", 
                                  (str(date.today()), cons, cli, cpf, email, tel, serv, val, stt, cnt, obs, f"{qtd} arqs"))
                        exists = False
                        if not df_clientes_raw.empty:
                            if cli in df_clientes_raw['Nome'].values: exists = True
                        if not exists:
                             run_query("INSERT INTO clientes (Nome, CPF, Email, Telefone, Data_Cadastro, Obs) VALUES (?,?,?,?,?,?,?)", (cli, cpf, email, tel, str(date.today()), "Auto Venda"))
                        st.toast("Salvo!"); st.rerun()
    with c2:
        st.markdown("#### Histórico")
        if "Excluir" not in df_v.columns: df_v.insert(0, "Excluir", False)
        ed_v = st.data_editor(df_v, hide_index=True, use_container_width=True, column_config={"id": st.column_config.NumberColumn(disabled=True)})
        if st.button("💾 Atualizar Vendas"):
            df_f = ed_v[ed_v["Excluir"]==False].drop(columns=["Excluir"])
            df_f['Data'] = df_f['Data'].astype(str)
            update_full_table(df_f, "vendas"); st.rerun()

# --- FINANCEIRO ---
elif escolha_menu == "💰 FINANCEIRO":
    st.markdown("## 💰 Financeiro")
    c1, c2 = st.columns([1, 2])
    with c1:
        with st.container(border=True):
            st.markdown("#### Lançar Saída")
            desc = st.text_input("Descrição")
            cat = st.selectbox("Categoria", ["Fixo", "Comissões", "Marketing", "Impostos"])
            con = st.selectbox("Saiu de", lista_bancos)
            val = st.number_input("Valor", min_value=0.0)
            if st.button("Salvar"):
                run_query("INSERT INTO despesas (Data, Categoria, Descricao, Conta_Origem, Valor) VALUES (?,?,?,?,?)",
                          (str(date.today()), cat, desc, con, val))
                st.toast("Salvo!"); st.rerun()
    with c2:
        st.markdown("#### Despesas")
        if "Excluir" not in df_despesas.columns: df_despesas.insert(0, "Excluir", False)
        ed_d = st.data_editor(df_despesas, hide_index=True, use_container_width=True)
        if st.button("💾 Atualizar Finanças"):
             df_f = ed_d[ed_d["Excluir"]==False].drop(columns=["Excluir"])
             df_f['Data'] = df_f['Data'].astype(str)
             update_full_table(df_f, "despesas"); st.rerun()

# --- CONFIG (METAS, CADASTROS, BACKUP) ---
elif escolha_menu == "⚙️ CONFIG":
    st.markdown("## ⚙️ Configurações")
    
    tab_geral, tab_backup = st.tabs(["Cadastros & Aparência", "Backup & Relatórios"])
    
    with tab_geral:
        col_cadastros, col_sistema = st.columns(2)
        
        with col_cadastros:
            st.markdown("#### 📋 Cadastros Auxiliares")
            
            # Serviços
            with st.expander("Serviços (Venda)", expanded=True):
                with st.form("add_s"):
                    ns = st.text_input("Novo Serviço")
                    if st.form_submit_button("Add") and ns: 
                        run_query("INSERT INTO servicos (Nome) VALUES (?)", (ns,)); st.rerun()
                if not df_servicos.empty: 
                    if "Excluir" not in df_servicos.columns: df_servicos.insert(0, "Excluir", False)
                    ed_s = st.data_editor(df_servicos, hide_index=True, key="editor_servicos")
                    if st.button("Salvar Serviços"):
                        update_full_table(ed_s[ed_s["Excluir"]==False].drop(columns=["Excluir"]), "servicos"); st.rerun()

            # Consultores
            with st.expander("Consultores"):
                with st.form("add_c"):
                    nm = st.text_input("Novo Consultor")
                    if st.form_submit_button("Add") and nm: 
                        run_query("INSERT INTO consultores (Nome) VALUES (?)", (nm,)); st.rerun()
                if not df_consultores.empty: st.dataframe(df_consultores, hide_index=True)
            
            # Bancos
            with st.expander("Contas Bancárias"):
                with st.form("add_b"):
                    nb = st.text_input("Novo Banco")
                    if st.form_submit_button("Add") and nb: 
                        run_query("INSERT INTO bancos (Banco) VALUES (?)", (nb,)); st.rerun()
                if not df_bancos.empty: st.dataframe(df_bancos, hide_index=True)

        with col_sistema:
            st.markdown("#### 🖥️ Sistema")
            novo_tema = st.radio("Tema Visual", ["Claro", "Escuro"], index=0 if st.session_state.theme == "Claro" else 1)
            if novo_tema != st.session_state.theme:
                st.session_state.theme = novo_tema
                st.rerun()
            
            st.divider()
            st.markdown("#### 🎯 Metas")
            with st.form("form_metas"):
                m_mensal = st.number_input("Meta Mensal (R$)", value=meta_mensal)
                m_anual = st.number_input("Meta Anual (R$)", value=meta_anual)
                if st.form_submit_button("Salvar Metas"):
                    set_config('meta_mensal', m_mensal)
                    set_config('meta_anual', m_anual)
                    st.success("Salvo!"); st.rerun()

    with tab_backup:
        st.markdown("#### 📥 Exportar")
        excel_data = converter_para_excel({
            "Vendas": df_vendas_raw, "Despesas": df_despesas_raw,
            "Clientes": df_clientes_raw, "Servicos": df_servicos
        })
        st.download_button("📊 Baixar Excel Completo", excel_data, f"Backup_{date.today()}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.divider()
        with open(DB_NAME, "rb") as fp:
            st.download_button("🗄️ Baixar Banco (.db)", fp, f"backup_{DB_NAME}", "application/x-sqlite3")

# --- ARQUIVOS ---
elif escolha_menu == "📂 ARQUIVOS":
    st.markdown("## 📂 Arquivos")
    col_busca, col_sel = st.columns([1, 2])
    with col_busca: busca = st.text_input("Filtro Pasta")
    pastas = [f for f in os.listdir(BASE_DIR_ARQUIVOS) if os.path.isdir(os.path.join(BASE_DIR_ARQUIVOS, f))]
    if busca: pastas = [p for p in pastas if busca.lower() in p.lower()]
    with col_sel: sel = st.selectbox("Selecione", ["--"] + pastas)
    if sel != "--":
        path = os.path.join(BASE_DIR_ARQUIVOS, sel)
        for arq in os.listdir(path):
            with open(os.path.join(path, arq), "rb") as f:
                st.download_button(f"📥 {arq}", f, file_name=arq)

# --- IA ---
elif escolha_menu == "🤖 I.A.":
    st.markdown("## 🤖 I.A.")
    if "msgs" not in st.session_state: st.session_state.msgs = []
    for m in st.session_state.msgs: st.chat_message(m["role"]).write(m["content"])
    if prompt := st.chat_input("Pergunte..."):
        st.session_state.msgs.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)
        res = chat_ia(df_vendas, df_despesas, prompt, openai_key)
        st.session_state.msgs.append({"role": "assistant", "content": res})
        st.chat_message("assistant").write(res)