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
# 2. SISTEMA DE TEMAS & CSS (CORRIGIDO)
# ==========================================
if "theme" not in st.session_state:
    st.session_state.theme = "Escuro" # Padrão Escuro (igual tua imagem)

# --- CSS COMUM ---
CSS_BASE = """
<style>
    /* Remover padding excessivo do topo para a busca ficar lá em cima */
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
    
    /* Estilo da Barra de Busca Centralizada */
    div[data-testid="stTextInput"] {
        margin-bottom: 10px;
    }
    
    /* Centralizar o texto dentro dos inputs */
    input { padding-left: 10px !important; }
</style>
"""

# --- CSS MODO CLARO (FIX: TEXTO ESCURO EM FUNDO CLARO) ---
CSS_LIGHT = CSS_BASE + """
<style>
    /* Fundo Geral */
    .stApp { background-color: #F3F4F6; color: #111827; }
    
    /* Sidebar */
    section[data-testid="stSidebar"] { background-color: #FFFFFF; border-right: 1px solid #E5E7EB; }
    
    /* Textos Gerais (Forçar Preto) */
    h1, h2, h3, h4, h5, h6, p, span, label { color: #111827 !important; }
    
    /* INPUTS (AQUI ESTAVA O PROBLEMA) */
    /* Garante que o fundo do input seja branco e o TEXTO SEJA PRETO */
    div[data-baseweb="input"] {
        background-color: #FFFFFF !important;
        border: 1px solid #9CA3AF !important; /* Borda mais visível */
        border-radius: 8px !important;
    }
    input[type="text"], input[type="number"], input[type="password"] {
        color: #000000 !important; /* Texto Preto Absoluto */
        background-color: transparent !important;
    }
    
    /* Cartões de Métricas */
    div[data-testid="stMetric"] { 
        background-color: #FFFFFF; 
        padding: 20px; 
        border-radius: 12px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.05); 
        border: 1px solid #E5E7EB; 
    }
    div[data-testid="stMetricLabel"] label { color: #6B7280 !important; }
    div[data-testid="stMetricValue"] { color: #111827 !important; }
    
    /* Tabelas */
    div[data-testid="stDataFrame"] { 
        background-color: #FFFFFF; 
        border: 1px solid #E5E7EB; 
        border-radius: 12px;
        color: #000000 !important;
    }
    
    /* Botões do Menu Lateral (Radio) */
    .stRadio label { color: #374151 !important; font-weight: 600; }
</style>
"""

# --- CSS MODO ESCURO (IGUAL TUA IMAGEM) ---
CSS_DARK = CSS_BASE + """
<style>
    /* Fundo Geral */
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    
    /* Sidebar */
    section[data-testid="stSidebar"] { background-color: #171923; border-right: 1px solid #2D3748; }
    
    /* Textos Gerais */
    h1, h2, h3, h4, h5, h6, p, span, label { color: #FAFAFA !important; }
    
    /* INPUTS (Busca Visível) */
    div[data-baseweb="input"] {
        background-color: #2D3748 !important;
        border: 1px solid #4A5568 !important;
        border-radius: 8px !important;
    }
    input[type="text"], input[type="number"], input[type="password"] {
        color: #FFFFFF !important; /* Texto Branco */
        background-color: transparent !important;
    }
    
    /* Cartões */
    div[data-testid="stMetric"] { 
        background-color: #262730; 
        padding: 20px; 
        border-radius: 12px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.3); 
        border: 1px solid #4A5568; 
    }
    div[data-testid="stMetricLabel"] label { color: #A0AEC0 !important; }
    div[data-testid="stMetricValue"] { color: #F7FAFC !important; }
    
    /* Tabelas */
    div[data-testid="stDataFrame"] { 
        background-color: #1A202C; 
        border: 1px solid #2D3748; 
        border-radius: 12px;
    }
    
    /* Botões Menu */
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
        c.execute('''CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, Data TEXT, Consultor TEXT, Cliente TEXT, CPF TEXT, 
            Servico TEXT, Valor REAL, Status_Pagamento TEXT, Conta_Recebimento TEXT, Obs TEXT, Docs TEXT, Email TEXT, Telefone TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, Data TEXT, Categoria TEXT, Descricao TEXT, Conta_Origem TEXT, Valor REAL
        )''')
        for col in ["Email", "Telefone", "Obs", "Conta_Recebimento"]:
            try: c.execute(f"ALTER TABLE vendas ADD COLUMN {col} TEXT"); 
            except: pass
        try: c.execute("ALTER TABLE despesas ADD COLUMN Conta_Origem TEXT"); 
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

def converter_para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados')
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
# 4. BARRA LATERAL (MENU E TEMA)
# ==========================================
with st.sidebar:
    st.title("💎 CMG Pro")
    st.markdown("Manager v18.0")
    
    # 1. Menu
    st.markdown("### Menu")
    menu_options = [
        "📊 DASHBOARD", "🧮 PRECIFICAÇÃO", "📇 CRM", 
        "👥 VENDAS", "💰 FINANCEIRO", "⚙️ CONFIG", 
        "📂 ARQUIVOS", "🤖 I.A."
    ]
    escolha_menu = st.radio("Ir para:", menu_options, label_visibility="collapsed")
    
    st.divider()

    # 2. Tema
    st.markdown("### 🌗 Tema Visual")
    tema_selecionado = st.radio("Tema:", ["Claro", "Escuro"], index=0 if st.session_state.theme == "Claro" else 1, label_visibility="collapsed")
    
    if tema_selecionado != st.session_state.theme:
        st.session_state.theme = tema_selecionado
        st.rerun()

    # Lógica de Cores baseada no Tema
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

    st.divider()

    # 3. Filtros
    st.markdown("### 📅 Filtros")
    tipo_filtro = st.radio("Período:", ["Mês Atual", "Personalizado", "Todo Histórico"], label_visibility="collapsed")
    
    data_inicio = None
    data_fim = None
    
    if tipo_filtro == "Mês Atual":
        hj = datetime.now()
        import calendar
        ultimo_dia = calendar.monthrange(hj.year, hj.month)[1]
        data_inicio = date(hj.year, hj.month, 1)
        data_fim = date(hj.year, hj.month, ultimo_dia)
        st.caption(f"🗓️ {data_inicio.strftime('%d/%m')} - {data_fim.strftime('%d/%m')}")
    elif tipo_filtro == "Personalizado":
        c1, c2 = st.columns(2)
        data_inicio = c1.date_input("De", value=date(datetime.now().year, datetime.now().month, 1))
        data_fim = c2.date_input("Até", value=datetime.now().date())

    st.divider()
    
    # 4. API Key
    st.markdown("### 🔑 API Key")
    openai_key = ""
    try:
        if "OPENAI_API_KEY" in st.secrets: openai_key = st.secrets["OPENAI_API_KEY"]
    except: pass
    if not openai_key: openai_key = st.text_input("OpenAI Key", type="password", label_visibility="collapsed")

# ==========================================
# 5. BUSCA CENTRALIZADA (HEADER)
# ==========================================
# Cria um container visualmente destacado para a busca
c_spacer1, c_search, c_spacer2 = st.columns([1, 6, 1])
with c_search:
    # A classe CSS vai garantir que isso fique visível em ambos os temas
    termo_busca = st.text_input("🔍 Buscar no Sistema", placeholder="Digite Nome, CPF ou Cliente...", label_visibility="collapsed")

# ==========================================
# 6. LÓGICA DE DADOS
# ==========================================
df_vendas_raw = load_data("vendas")
df_despesas_raw = load_data("despesas")
df_clientes_raw = load_data("clientes")
df_consultores = load_data("consultores")
df_bancos = load_data("bancos")

df_vendas_raw['Data'] = pd.to_datetime(df_vendas_raw['Data'], errors='coerce').dt.date
df_despesas_raw['Data'] = pd.to_datetime(df_despesas_raw['Data'], errors='coerce').dt.date

# Filtro Data
if tipo_filtro != "Todo Histórico" and data_inicio and data_fim:
    df_vendas = df_vendas_raw[(df_vendas_raw['Data'] >= data_inicio) & (df_vendas_raw['Data'] <= data_fim)].copy()
    df_despesas = df_despesas_raw[(df_despesas_raw['Data'] >= data_inicio) & (df_despesas_raw['Data'] <= data_fim)].copy()
else:
    df_vendas = df_vendas_raw.copy()
    df_despesas = df_despesas_raw.copy()

# Filtro Busca
if termo_busca:
    t = termo_busca.lower()
    mask_v = df_vendas.astype(str).apply(lambda x: x.str.lower().str.contains(t)).any(axis=1)
    df_vendas = df_vendas[mask_v]
    mask_c = df_clientes_raw.astype(str).apply(lambda x: x.str.lower().str.contains(t)).any(axis=1)
    df_clientes = df_clientes_raw[mask_c]
else:
    df_clientes = df_clientes_raw.copy()

lista_consultores = df_consultores["Nome"].tolist() if not df_consultores.empty else ["Geral"]
lista_bancos = df_bancos["Banco"].tolist() if not df_bancos.empty else ["Caixa Principal"]

# ==========================================
# 7. ROTEAMENTO
# ==========================================

# --- DASHBOARD ---
if escolha_menu == "📊 DASHBOARD":
    fat = df_vendas["Valor"].sum() if not df_vendas.empty else 0
    desp = df_despesas["Valor"].sum() if not df_despesas.empty else 0
    lucro = fat - desp
    ticket = fat / len(df_vendas) if len(df_vendas) > 0 else 0
    
    st.markdown(f"## 📊 Visão Geral ({tipo_filtro})")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faturamento", f"R$ {fat:,.2f}")
    c2.metric("Lucro Líquido", f"R$ {lucro:,.2f}", delta=f"{(lucro/fat)*100:.1f}%" if fat>0 else "0%")
    c3.metric("Despesas", f"R$ {desp:,.2f}", delta="Saídas", delta_color="inverse")
    c4.metric("Ticket Médio", f"R$ {ticket:,.2f}")

    st.markdown("<br>", unsafe_allow_html=True)

    g1, g2 = st.columns([1, 2])
    with g1:
        st.markdown("**Mix de Serviços**")
        if not df_vendas.empty:
            fig_pie = px.pie(df_vendas, names="Servico", values="Valor", hole=0.7, color_discrete_sequence=cor_grafico, template=plotly_template)
            fig_pie.update_layout(showlegend=False, margin=dict(t=20, b=20, l=20, r=20), height=280, paper_bgcolor="rgba(0,0,0,0)")
            fig_pie.add_annotation(text=f"Total<br>R${fat:,.0f}", showarrow=False, font_size=14, font_color=txt_chart)
            st.plotly_chart(fig_pie, use_container_width=True)
        else: st.info("Sem dados")

    with g2:
        st.markdown("**Evolução Financeira**")
        if not df_vendas.empty:
            daily_sales = df_vendas.groupby("Data")["Valor"].sum().reset_index()
            fig_area = px.area(daily_sales, x="Data", y="Valor", color_discrete_sequence=[cor_grafico[1]], template=plotly_template)
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
        st.markdown("**Meta**")
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number", value = fat, domain = {'x': [0, 1], 'y': [0, 1]},
            gauge = {'axis': {'range': [None, 50000]}, 'bar': {'color': cor_grafico[2]}, 'bgcolor': "#2D3748" if st.session_state.theme == "Escuro" else "#E5E7EB"}
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
            if soma >= 100: st.error("Erro: Margens > 100%")
            else:
                fator = (100 - soma) / 100
                preco_venda = custo / fator
                lucro_liq = preco_venda * (margem/100)
                st.metric("Sugerido", f"R$ {preco_venda:,.2f}")
                st.write(f"Lucro Líquido: R$ {lucro_liq:,.2f}")

# --- CRM ---
elif escolha_menu == "📇 CRM":
    st.markdown("## 📇 CRM")
    c1, c2 = st.columns([1, 2])
    with c1:
        with st.container(border=True):
            st.markdown("#### Novo")
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
        st.markdown(f"#### Clientes ({len(df_clientes)})")
        if "Excluir" not in df_clientes.columns: df_clientes.insert(0, "Excluir", False)
        ed = st.data_editor(df_clientes, hide_index=True, use_container_width=True, column_config={"id": st.column_config.NumberColumn(disabled=True)})
        if st.button("💾 Atualizar CRM"):
            df_final = ed[ed["Excluir"]==False].drop(columns=["Excluir"])
            update_full_table(df_final, "clientes"); st.rerun()

# --- VENDAS ---
elif escolha_menu == "👥 VENDAS":
    st.markdown("## 👥 Vendas")
    c1, c2 = st.columns([1, 2])
    with c1:
        with st.container(border=True):
            st.markdown("#### Lançar")
            with st.form("venda"):
                cons = st.selectbox("Consultor", lista_consultores)
                cli = st.text_input("Cliente*")
                cpf = st.text_input("CPF")
                serv = st.selectbox("Serviço", ["Limpeza Nome", "Score", "Consultoria", "Jurídico"])
                val = st.number_input("Valor", min_value=0.0)
                stt = st.selectbox("Status", ["Pago Total", "Parcial", "Pendente"])
                cnt = st.selectbox("Recebido em", lista_bancos)
                obs = st.text_area("Obs")
                docs = st.file_uploader("Docs", accept_multiple_files=True)
                if st.form_submit_button("Salvar"):
                    if cli:
                        qtd = salvar_arquivos(docs, cli)
                        run_query("INSERT INTO vendas (Data, Consultor, Cliente, CPF, Servico, Valor, Status_Pagamento, Conta_Recebimento, Obs, Docs) VALUES (?,?,?,?,?,?,?,?,?,?)", 
                                  (str(date.today()), cons, cli, cpf, serv, val, stt, cnt, obs, f"{qtd} arqs"))
                        exists = False
                        if not df_clientes_raw.empty:
                            if cli in df_clientes_raw['Nome'].values: exists = True
                        if not exists:
                             run_query("INSERT INTO clientes (Nome, CPF, Data_Cadastro, Obs) VALUES (?,?,?,?)", (cli, cpf, str(date.today()), "Auto Venda"))
                        st.toast("Salvo!"); st.rerun()
    with c2:
        st.markdown("#### Histórico")
        if "Excluir" not in df_vendas.columns: df_vendas.insert(0, "Excluir", False)
        ed_v = st.data_editor(df_vendas, hide_index=True, use_container_width=True, column_config={"id": st.column_config.NumberColumn(disabled=True)})
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
            st.markdown("#### Despesa")
            desc = st.text_input("Descrição")
            cat = st.selectbox("Categoria", ["Fixo", "Comissões", "Marketing", "Impostos"])
            con = st.selectbox("Saiu de", lista_bancos)
            val = st.number_input("Valor", min_value=0.0)
            if st.button("Salvar"):
                run_query("INSERT INTO despesas (Data, Categoria, Descricao, Conta_Origem, Valor) VALUES (?,?,?,?,?)",
                          (str(date.today()), cat, desc, con, val))
                st.toast("Salvo!"); st.rerun()
    with c2:
        st.markdown("#### Saídas")
        if "Excluir" not in df_despesas.columns: df_despesas.insert(0, "Excluir", False)
        ed_d = st.data_editor(df_despesas, hide_index=True, use_container_width=True)
        if st.button("💾 Atualizar Finanças"):
             df_f = ed_d[ed_d["Excluir"]==False].drop(columns=["Excluir"])
             df_f['Data'] = df_f['Data'].astype(str)
             update_full_table(df_f, "despesas"); st.rerun()

# --- CONFIG ---
elif escolha_menu == "⚙️ CONFIG":
    st.markdown("## ⚙️ Configurações")
    c1, c2 = st.columns(2)
    with c1:
        with st.form("add_c"):
            nm = st.text_input("Novo Consultor")
            if st.form_submit_button("Add") and nm: 
                run_query("INSERT INTO consultores (Nome) VALUES (?)", (nm,)); st.rerun()
        if not df_consultores.empty: st.dataframe(df_consultores, hide_index=True, use_container_width=True)
    with c2:
        with st.form("add_b"):
            nb = st.text_input("Novo Banco")
            if st.form_submit_button("Add") and nb: 
                run_query("INSERT INTO bancos (Banco) VALUES (?)", (nb,)); st.rerun()
        if not df_bancos.empty: st.dataframe(df_bancos, hide_index=True, use_container_width=True)

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