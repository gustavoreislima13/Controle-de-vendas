import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import sqlite3
import io
import pdfplumber
import re
import shutil  # Adicionado para apagar pastas
import time    # Adicionado para delay na mensagem de sucesso
from datetime import datetime, date
from openai import OpenAI

# ==========================================
# 1. CONFIGURAÇÃO INICIAL
# ==========================================
st.set_page_config(page_title="CMG System Pro", layout="wide", page_icon="💎")

# ==========================================
# 2. FUNÇÕES AUXILIARES E FORMATAÇÃO BR
# ==========================================
def format_brl(value):
    """Formata float para moeda brasileira (R$ 1.000,00)"""
    if value is None or pd.isna(value):
        return "R$ 0,00"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

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
        
        c.execute('CREATE TABLE IF NOT EXISTS servicos (id INTEGER PRIMARY KEY AUTOINCREMENT, Nome TEXT)')
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
        
        # Migrations de segurança
        for col in ["Email", "Telefone", "Obs", "Conta_Recebimento"]:
            try: c.execute(f"ALTER TABLE vendas ADD COLUMN {col} TEXT"); 
            except: pass
        try: c.execute("ALTER TABLE despesas ADD COLUMN Conta_Origem TEXT"); 
        except: pass
        
        # Inserir configurações padrão se não existirem
        try: c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('meta_mensal', '50000')")
        except: pass
        try: c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('meta_anual', '600000')")
        except: pass
        try: c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES ('tema_preferido', 'Escuro')")
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
        try:
            df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
        except:
            df = pd.DataFrame() # Retorna vazio se a tabela não existir
    return df

def get_config(chave):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT valor FROM config WHERE chave=?", (chave,))
        res = c.fetchone()
        try:
            return float(res[0]) if res else 0.0
        except:
            return 0.0

def get_config_text(chave):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT valor FROM config WHERE chave=?", (chave,))
        res = c.fetchone()
        return res[0] if res else None

def set_config(chave, valor):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", (chave, str(valor)))
        conn.commit()
    st.cache_data.clear()

# --- ATUALIZAÇÃO SEGURA (MERGE) ---
def update_full_table(df_edited_view, table_name):
    with sqlite3.connect(DB_NAME) as conn:
        df_full = pd.read_sql(f"SELECT * FROM {table_name}", conn)
        
        if "Excluir" in df_edited_view.columns:
            ids_to_delete = df_edited_view[df_edited_view["Excluir"] == True]["id"].tolist()
            df_to_update = df_edited_view[df_edited_view["Excluir"] == False].drop(columns=["Excluir"])
        else:
            ids_to_delete = []
            df_to_update = df_edited_view

        if ids_to_delete:
            df_full = df_full[~df_full['id'].isin(ids_to_delete)]

        if not df_to_update.empty:
            df_full["id"] = df_full["id"].astype(int)
            df_to_update["id"] = df_to_update["id"].astype(int)
            if 'Data' in df_to_update.columns:
                df_to_update['Data'] = df_to_update['Data'].astype(str)

            df_full.set_index("id", inplace=True)
            df_to_update.set_index("id", inplace=True)
            df_full.update(df_to_update)
            df_full.reset_index(inplace=True)

        if 'Data' in df_full.columns:
            df_full['Data'] = df_full['Data'].astype(str)
            
        df_full.to_sql(table_name, conn, if_exists='replace', index=False)
        
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
            df_export = df.copy()
            if "Data" in df_export.columns:
                df_export["Data"] = df_export["Data"].astype(str)
            df_export.to_excel(writer, index=False, sheet_name=name)
    return output.getvalue()

# ==========================================
# 4. SISTEMA DE TEMAS & CSS
# ==========================================
if "theme" not in st.session_state:
    tema_salvo = get_config_text("tema_preferido")
    st.session_state.theme = tema_salvo if tema_salvo else "Escuro"

CSS_BASE = """
<style>
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    div[data-testid="stTextInput"] input { font-size: 16px; padding: 10px; }
</style>
"""
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
# 5. FUNÇÕES DE IMPORTAÇÃO
# ==========================================
def clean_currency(val_str):
    if pd.isna(val_str): return 0.0
    if isinstance(val_str, (int, float)): return float(val_str)
    clean = str(val_str).strip()
    is_negative = "-" in clean or "D" in clean.upper() or "(" in clean
    clean = re.sub(r'[^\d.,]', '', clean)
    if not clean: return 0.0
    if "," in clean and "." in clean:
        clean = clean.replace(".", "").replace(",", ".")
    elif "," in clean:
        clean = clean.replace(",", ".")
    try:
        val = float(clean)
        return -val if is_negative else val
    except:
        return 0.0

def parse_pdf_data(date_str):
    if not date_str: return str(date.today())
    match = re.search(r'\d{2}/\d{2}/\d{2,4}', str(date_str))
    if match:
        d = match.group(0)
        try: return str(datetime.strptime(d, "%d/%m/%Y").date())
        except:
            try: return str(datetime.strptime(d, "%d/%m/%y").date())
            except: pass
    return str(date.today())

def processar_arquivo_inteligente(file):
    df = pd.DataFrame()
    filename = file.name.lower()
    if filename.endswith(('.xlsx', '.xls')):
        try: df = pd.read_excel(file)
        except: return None, "Erro ao ler Excel."
    elif filename.endswith('.pdf'):
        all_rows = []
        try:
            with pdfplumber.open(file) as pdf:
                for page in pdf.pages:
                    table = page.extract_table()
                    if not table:
                        table = page.extract_table(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text", "snap_tolerance": 3})
                    if table: all_rows.extend(table)
            if not all_rows: return None, "PDF vazio ou ilegível."
            df = pd.DataFrame(all_rows[1:], columns=all_rows[0])
        except Exception as e: return None, f"Erro PDF: {e}"
    else:
        return None, "Formato não suportado."

    df = df.dropna(axis=1, how='all')
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    cols_lower = [c.lower() for c in df.columns]

    def get_col_by_keyword(keywords):
        for i, c in enumerate(cols_lower):
            if any(k in c for k in keywords): return df.iloc[:, i]
        return None

    s_data = get_col_by_keyword(['data', 'dt', 'date', 'movimento'])
    s_valor = get_col_by_keyword(['valor', 'value', 'amount', 'débito', 'crédito', 'saldo'])
    if s_data is None and len(df.columns) > 0: s_data = df.iloc[:, 0]
    if s_valor is None and len(df.columns) > 1: s_valor = df.iloc[:, -1]

    s_desc = get_col_by_keyword(['descri', 'histórico', 'memo', 'lançamento', 'discriminacao'])
    if s_desc is None:
        max_len = 0
        best_col_idx = -1
        for i, col_name in enumerate(df.columns):
            is_data = (s_data is not None and df.iloc[:, i].equals(s_data))
            is_valor = (s_valor is not None and df.iloc[:, i].equals(s_valor))
            if not is_data and not is_valor:
                try:
                    mean_len = df.iloc[:, i].astype(str).map(len).mean()
                    if mean_len > max_len: max_len, best_col_idx = mean_len, i
                except: pass
        if best_col_idx != -1: s_desc = df.iloc[:, best_col_idx]

    s_ent = get_col_by_keyword(['entidade', 'cliente', 'nome', 'favorecido'])
    s_cat = get_col_by_keyword(['categoria', 'classifica'])
    s_conta = get_col_by_keyword(['conta', 'banco', 'origem'])

    df_final = pd.DataFrame()
    df_final["Data"] = s_data.apply(parse_pdf_data) if s_data is not None else str(date.today())
    if s_desc is not None: df_final["Descrição"] = s_desc.astype(str).str.replace("\n", " ").fillna("")
    else: df_final["Descrição"] = "Sem Descrição"
    df_final["Valor"] = s_valor.apply(clean_currency) if s_valor is not None else 0.0
    if s_ent is not None: df_final["Entidade"] = s_ent.astype(str).fillna("")
    else: df_final["Entidade"] = df_final["Descrição"] 
    df_final["Conta"] = s_conta.astype(str) if s_conta is not None else "Banco Principal"
    df_final["Categoria"] = s_cat.astype(str) if s_cat is not None else "Geral"
    for col in ["Conta", "Categoria", "Entidade", "Descrição"]:
        df_final[col] = df_final[col].replace({"nan": "", "None": "", "Nb": "", "NaT": ""}).fillna("")
    df_final = df_final[df_final["Valor"] != 0]
    return df_final[["Conta", "Categoria", "Entidade", "Descrição", "Data", "Valor"]], "OK"

def classificar_lote_com_ia(df, api_key):
    if not api_key: return df
    try:
        client = OpenAI(api_key=api_key)
        descricoes = df["Descrição"].unique()[:40] 
        lista = "\n".join([f"- {d}" for d in descricoes])
        prompt = f"""
        Analise estas descrições bancárias. Identifique:
        1. Categoria (Ex: Alimentação, Transporte, Marketing, Fixo, Venda, Serviços).
        2. Entidade (Nome da Loja, Pessoa ou Cliente).
        Retorne no formato exato: Descrição -> Categoria | Entidade
        Itens:
        {lista}
        """
        resp = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}], temperature=0)
        texto = resp.choices[0].message.content
        mapa_cat, mapa_ent = {}, {}
        for linha in texto.split("\n"):
            if "->" in linha and "|" in linha:
                pt1, pt2 = linha.split("->")
                desc_key, (cat_val, ent_val) = pt1.strip("- ").strip(), pt2.split("|")
                mapa_cat[desc_key], mapa_ent[desc_key] = cat_val.strip(), ent_val.strip()
        df["Categoria"] = df["Descrição"].map(mapa_cat).fillna(df["Categoria"])
        mask = (df["Entidade"] == "") | (df["Entidade"] == df["Descrição"])
        df.loc[mask, "Entidade"] = df.loc[mask, "Descrição"].map(mapa_ent).fillna(df.loc[mask, "Entidade"])
        return df
    except Exception as e:
        st.error(f"Erro IA: {e}")
        return df

def chat_ia(df_v, df_d, user_msg, key):
    if not key: return "⚠️ Configure sua API Key."
    try:
        client = OpenAI(api_key=key)
        contexto = f"Vendas recentes: {df_v.tail(5).to_string()}\nDespesas recentes: {df_d.tail(5).to_string()}"
        resp = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "system", "content": f"Você é um analista financeiro. Contexto atual: {contexto}"}, {"role": "user", "content": user_msg}])
        return resp.choices[0].message.content
    except Exception as e: return f"Erro IA: {e}"

# ==========================================
# 6. BARRA LATERAL
# ==========================================
with st.sidebar:
    st.title("💎 CMG Pro")
    st.markdown("Manager v27.3 (Reset)")
    
    st.markdown("### Menu")
    menu_options = ["📊 DASHBOARD", "🧮 PRECIFICAÇÃO", "📇 CRM", "👥 VENDAS", "💰 FINANCEIRO", "⚙️ CONFIG", "📂 ARQUIVOS", "🤖 I.A."]
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
# 7. LÓGICA DE DADOS
# ==========================================
df_vendas_raw = load_data("vendas")
df_despesas_raw = load_data("despesas")
df_clientes_raw = load_data("clientes")
df_consultores = load_data("consultores")
df_bancos = load_data("bancos")
df_servicos = load_data("servicos")

meta_mensal = get_config('meta_mensal')
meta_anual = get_config('meta_anual')

# TRATAMENTO DE DADOS
if not df_vendas_raw.empty:
    df_vendas_raw['Data'] = pd.to_datetime(df_vendas_raw['Data'], errors='coerce').dt.date
    df_vendas_raw['Valor'] = pd.to_numeric(df_vendas_raw['Valor'], errors='coerce').fillna(0.0)

if not df_despesas_raw.empty:
    df_despesas_raw['Data'] = pd.to_datetime(df_despesas_raw['Data'], errors='coerce').dt.date
    df_despesas_raw['Valor'] = pd.to_numeric(df_despesas_raw['Valor'], errors='coerce').fillna(0.0)

# FILTRO
if tipo_filtro != "Todo Histórico" and data_inicio and data_fim:
    df_vendas = df_vendas_raw[(df_vendas_raw['Data'] >= data_inicio) & (df_vendas_raw['Data'] <= data_fim)].copy() if not df_vendas_raw.empty else df_vendas_raw
    df_despesas = df_despesas_raw[(df_despesas_raw['Data'] >= data_inicio) & (df_despesas_raw['Data'] <= data_fim)].copy() if not df_despesas_raw.empty else df_despesas_raw
else:
    df_vendas = df_vendas_raw.copy()
    df_despesas = df_despesas_raw.copy()

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
# 8. ROTEAMENTO
# ==========================================

# --- DASHBOARD ---
if escolha_menu == "📊 DASHBOARD":
    st.markdown("## 📊 Visão Geral")
    termo_busca = st.text_input("🔍 Buscar rápido...", placeholder="Digite para filtrar os dados abaixo...")
    df_v = df_vendas.copy()
    if termo_busca and not df_v.empty:
        mask = df_v.astype(str).apply(lambda x: x.str.lower().str.contains(termo_busca.lower())).any(axis=1)
        df_v = df_v[mask]

    fat = df_v["Valor"].sum() if not df_v.empty else 0
    desp = df_despesas["Valor"].sum() if not df_despesas.empty else 0
    lucro = fat - desp
    ticket = fat / len(df_v) if len(df_v) > 0 else 0
    
    st.caption(f"Período: {tipo_filtro}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faturamento", format_brl(fat))
    c2.metric("Lucro Líquido", format_brl(lucro), delta=f"{(lucro/fat)*100:.1f}%" if fat>0 else "0%")
    c3.metric("Despesas", format_brl(desp), delta="Saídas", delta_color="inverse")
    c4.metric("Ticket Médio", format_brl(ticket))

    st.markdown("<br>", unsafe_allow_html=True)
    g1, g2 = st.columns([1, 2])
    with g1:
        st.markdown("**Mix de Serviços**")
        if not df_v.empty:
            fig_pie = px.pie(df_v, names="Servico", values="Valor", hole=0.7, color_discrete_sequence=cor_grafico, template=plotly_template)
            fig_pie.update_layout(showlegend=False, margin=dict(t=20, b=20, l=20, r=20), height=280, paper_bgcolor="rgba(0,0,0,0)")
            fig_pie.add_annotation(text=f"R$ {fat:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), showarrow=False, font_size=14, font_color=txt_chart)
            st.plotly_chart(fig_pie, use_container_width=True)
        else: st.info("Sem dados")
    with g2:
        st.markdown("**Evolução Financeira**")
        if not df_v.empty:
            daily = df_v.groupby("Data")["Valor"].sum().reset_index()
            daily['Data'] = pd.to_datetime(daily['Data'])
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
                st.metric("Sugerido", format_brl(preco_venda))
                st.write(f"Lucro Líquido: {format_brl(lucro_liq)}")

# --- CRM ---
elif escolha_menu == "📇 CRM":
    st.markdown("## 📇 Clientes")
    busca_crm = st.text_input("🔍 Buscar Cliente...", placeholder="Nome ou CPF")
    df_c = df_clientes_raw.copy()
    if busca_crm and not df_c.empty:
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
        if not df_c.empty:
            if "Excluir" not in df_c.columns: df_c.insert(0, "Excluir", False)
            ed = st.data_editor(df_c, hide_index=True, use_container_width=True, column_config={"id": st.column_config.NumberColumn(disabled=True)})
            if st.button("💾 Atualizar CRM"):
                update_full_table(ed, "clientes"); st.rerun()

# --- VENDAS ---
elif escolha_menu == "👥 VENDAS":
    st.markdown("## 👥 Vendas")
    busca_vendas = st.text_input("🔍 Filtrar Vendas...", placeholder="Cliente, Consultor...")
    df_v = df_vendas.copy()
    if busca_vendas and not df_v.empty:
        mask = df_v.astype(str).apply(lambda x: x.str.lower().str.contains(busca_vendas.lower())).any(axis=1)
        df_v = df_v[mask]
        
    c1, c2 = st.columns([1, 2])
    with c1:
        with st.container(border=True):
            st.markdown("#### Lançar")
            with st.form("venda"):
                cons = st.selectbox("Consultor", lista_consultores)
                c_cli, c_cpf = st.columns(2)
                cli = c_cli.text_input("Cliente*")
                cpf = c_cpf.text_input("CPF")
                c_email, c_tel = st.columns(2)
                email = c_email.text_input("Email")
                tel = c_tel.text_input("Telefone")
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
                            run_query("INSERT INTO clientes (Nome, CPF, Email, Telefone, Data_Cadastro, Obs) VALUES (?,?,?,?,?,?)", (cli, cpf, email, tel, str(date.today()), "Auto Venda"))
                        st.toast("Salvo!"); st.rerun()
    with c2:
        st.markdown("#### Histórico")
        if not df_v.empty:
            if "Excluir" not in df_v.columns: df_v.insert(0, "Excluir", False)
            df_v_editor = df_v.copy()
            if 'Data' in df_v_editor.columns: df_v_editor['Data'] = df_v_editor['Data'].astype(str)
            ed_v = st.data_editor(df_v_editor, hide_index=True, use_container_width=True, column_config={"id": st.column_config.NumberColumn(disabled=True)})
            if st.button("💾 Atualizar Vendas"):
                update_full_table(ed_v, "vendas"); st.rerun()

# --- FINANCEIRO ---
elif escolha_menu == "💰 FINANCEIRO":
    st.markdown("## 💰 Financeiro")
    c1, c2 = st.columns([1, 2])
    with c1:
        with st.container(border=True):
            st.markdown("#### Lançar Saída")
            desc = st.text_input("Descrição")
            cat = st.selectbox("Categoria", ["Fixo", "Comissões", "Marketing", "Impostos", "Pessoal", "Transporte"])
            con = st.selectbox("Saiu de", lista_bancos)
            val = st.number_input("Valor", min_value=0.0)
            if st.button("Salvar"):
                run_query("INSERT INTO despesas (Data, Categoria, Descricao, Conta_Origem, Valor) VALUES (?,?,?,?,?)",
                          (str(date.today()), cat, desc, con, val))
                st.toast("Salvo!"); st.rerun()
    with c2:
        st.markdown("#### Despesas")
        if not df_despesas.empty:
            if "Excluir" not in df_despesas.columns: df_despesas.insert(0, "Excluir", False)
            df_d_editor = df_despesas.copy()
            if 'Data' in df_d_editor.columns: df_d_editor['Data'] = df_d_editor['Data'].astype(str)
            ed_d = st.data_editor(df_d_editor, hide_index=True, use_container_width=True)
            if st.button("💾 Atualizar Finanças"):
                 update_full_table(ed_d, "despesas"); st.rerun()

# --- CONFIG ---
elif escolha_menu == "⚙️ CONFIG":
    st.markdown("## ⚙️ Configurações")
    
    # -----------------------------------------------
    # NOVO: ZONA DE PERIGO (RESET DE FÁBRICA)
    # -----------------------------------------------
    with st.expander("🚨 ZONA DE PERIGO (Apagar Tudo)", expanded=False):
        st.error("⚠️ ATENÇÃO: AÇÃO DESTRUTIVA")
        st.markdown("Esta ação irá **apagar todas as vendas, clientes, despesas e arquivos** permanentemente. O sistema voltará ao estado original (vazio).")
        
        col_reset1, col_reset2 = st.columns([3, 1])
        with col_reset1:
            check_reset = st.checkbox("Eu entendo que vou perder todos os dados e quero continuar.")
        with col_reset2:
            if check_reset:
                if st.button("🗑️ EXCLUIR TUDO AGORA", type="primary"):
                    try:
                        with sqlite3.connect(DB_NAME) as conn:
                            c = conn.cursor()
                            # Lista de tabelas para limpar (mantendo a estrutura)
                            tables_to_clear = ["vendas", "despesas", "clientes", "consultores", "bancos", "servicos", "config"]
                            for t in tables_to_clear:
                                try:
                                    c.execute(f"DELETE FROM {t}")
                                except: pass # Se a tabela não existir, ignora
                            conn.commit()
                        
                        # Apagar pasta de arquivos físicos
                        if os.path.exists(BASE_DIR_ARQUIVOS):
                            shutil.rmtree(BASE_DIR_ARQUIVOS)
                            os.makedirs(BASE_DIR_ARQUIVOS)
                            
                        # Limpar cache e reiniciar
                        st.cache_data.clear()
                        st.session_state.clear()
                        
                        st.success("♻️ SISTEMA FORMATADO COM SUCESSO!")
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao resetar: {e}")
    
    st.divider()
    
    tab_geral, tab_backup, tab_import = st.tabs(["Cadastros & Aparência", "Backup & Relatórios", "📥 Importação"])
    
    with tab_geral:
        col_cadastros, col_sistema = st.columns(2)
        with col_cadastros:
            st.markdown("#### 📋 Cadastros Auxiliares")
            with st.expander("Serviços (Venda)", expanded=True):
                with st.form("add_s"):
                    ns = st.text_input("Novo Serviço")
                    if st.form_submit_button("Add") and ns: 
                        run_query("INSERT INTO servicos (Nome) VALUES (?)", (ns,)); st.rerun()
                if not df_servicos.empty: 
                    if "Excluir" not in df_servicos.columns: df_servicos.insert(0, "Excluir", False)
                    ed_s = st.data_editor(df_servicos, hide_index=True, key="editor_servicos")
                    if st.button("Salvar Serviços"):
                        update_full_table(ed_s, "servicos"); st.rerun()

            with st.expander("Consultores"):
                with st.form("add_c"):
                    nm = st.text_input("Novo Consultor")
                    if st.form_submit_button("Add") and nm: 
                        run_query("INSERT INTO consultores (Nome) VALUES (?)", (nm,)); st.rerun()
                if not df_consultores.empty: st.dataframe(df_consultores, hide_index=True)
            
            with st.expander("Contas Bancárias"):
                with st.form("add_b"):
                    nb = st.text_input("Novo Banco")
                    if st.form_submit_button("Add") and nb: 
                        run_query("INSERT INTO bancos (Banco) VALUES (?)", (nb,)); st.rerun()
                if not df_bancos.empty: st.dataframe(df_bancos, hide_index=True)

        with col_sistema:
            st.markdown("#### 🖥️ Sistema")
            st.write("**Aparência**")
            current_theme_idx = 0 if st.session_state.theme == "Claro" else 1
            novo_tema = st.radio("Selecione o tema:", ["Claro", "Escuro"], index=current_theme_idx)
            if novo_tema != st.session_state.theme:
                st.session_state.theme = novo_tema
                set_config('tema_preferido', novo_tema)
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

    with tab_import:
        st.markdown("### 📥 Importação em Lote")
        st.info("Suporta múltiplos arquivos (PDF/Excel) de uma só vez. Limite recomendado: 50 arqs.")
        tipo_arq = st.radio("Tipo de Lançamento:", ["Receitas (Vendas)", "Despesas (Saídas)"], horizontal=True)
        uploaded_files = st.file_uploader("Arraste seus arquivos aqui", type=["pdf", "xlsx", "xls"], accept_multiple_files=True)
        if uploaded_files:
            tipo_imp = "Receita" if "Receitas" in tipo_arq else "Despesa"
            upload_id = str(sorted([f.name for f in uploaded_files]))
            if "df_preview" not in st.session_state or st.session_state.get("upload_id") != upload_id:
                lista_dfs_processados = []
                erros_leitura = []
                progresso = st.progress(0, text="Lendo arquivos...")
                total_arquivos = len(uploaded_files)
                for i, file in enumerate(uploaded_files):
                    progresso.progress((i + 1) / total_arquivos, text=f"Lendo {file.name}...")
                    df_res, msg = processar_arquivo_inteligente(file)
                    if df_res is not None and not df_res.empty:
                        if tipo_imp == "Despesa": df_res["Valor"] = df_res["Valor"].abs()
                        lista_dfs_processados.append(df_res)
                    else: erros_leitura.append(f"{file.name}: {msg}")
                progresso.empty()
                if lista_dfs_processados:
                    df_final_preview = pd.concat(lista_dfs_processados, ignore_index=True)
                    st.session_state.df_preview = df_final_preview
                    st.session_state.upload_id = upload_id
                    if erros_leitura: st.warning(f"Alguns arquivos não foram lidos: {', '.join(erros_leitura)}")
                else: st.error("Nenhum dado válido encontrado.")
            
            if "df_preview" in st.session_state:
                df_p = st.session_state.df_preview
                st.markdown(f"#### 📝 Prévia ({len(df_p)} registros)")
                c_ia, c_limpar = st.columns([1, 4])
                if c_ia.button("✨ Completar Tudo com IA"):
                    with st.spinner("Classificando..."):
                        df_p = classificar_lote_com_ia(df_p, openai_key)
                        st.session_state.df_preview = df_p
                        st.rerun()
                if c_limpar.button("Limpar Tudo"):
                    del st.session_state["df_preview"]
                    if "upload_id" in st.session_state: del st.session_state["upload_id"]
                    st.rerun()

                edited_df = st.data_editor(df_p, num_rows="dynamic", use_container_width=True)
                if st.button(f"✅ Confirmar Importação"):
                    try:
                        edited_df['Data'] = edited_df['Data'].astype(str)
                        with sqlite3.connect(DB_NAME) as conn:
                            if tipo_imp == "Receita":
                                df_b = pd.DataFrame()
                                df_b["Data"] = edited_df["Data"]
                                df_b["Cliente"] = edited_df["Entidade"]
                                df_b["Servico"] = edited_df["Categoria"]
                                df_b["Conta_Recebimento"] = edited_df["Conta"]
                                df_b["Obs"] = edited_df["Descrição"]
                                df_b["Valor"] = edited_df["Valor"]
                                df_b["Consultor"] = "Importação em Lote"
                                df_b["Status_Pagamento"] = "Pago Total"
                                df_b.to_sql("vendas", conn, if_exists="append", index=False)
                            else:
                                df_b = pd.DataFrame()
                                df_b["Data"] = edited_df["Data"]
                                df_b["Categoria"] = edited_df["Categoria"]
                                df_b["Conta_Origem"] = edited_df["Conta"]
                                df_b["Descricao"] = edited_df["Descrição"] + " (" + edited_df["Entidade"] + ")"
                                df_b["Valor"] = edited_df["Valor"]
                                df_b.to_sql("despesas", conn, if_exists="append", index=False)
                        st.success(f"Sucesso!")
                        del st.session_state["df_preview"]
                        del st.session_state["upload_id"]
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e: st.error(f"Erro ao salvar: {e}")

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