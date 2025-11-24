import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import sqlite3
import io
from datetime import datetime
from openai import OpenAI

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E ESTILO (CSS)
# ==========================================
st.set_page_config(page_title="CMG System Pro", layout="wide", page_icon="💎")

# CSS "Dark Mode" Profissional
st.markdown("""
<style>
    /* FUNDO GERAL ESCURO */
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    
    /* BARRA LATERAL */
    section[data-testid="stSidebar"] { background-color: #171923; border-right: 1px solid #2D3748; }

    /* ABAS (TABS) */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: transparent; padding-bottom: 10px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #262730; border-radius: 6px; color: #A0AEC0;
        padding: 8px 16px; border: 1px solid #4A5568; font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background-color: #E53E3E; color: white !important;
        border: 1px solid #E53E3E; font-weight: bold;
        box-shadow: 0 0 12px rgba(229, 62, 62, 0.4);
    }
    .stTabs [data-baseweb="tab"]:hover { border-color: #E53E3E; color: #E53E3E; }

    /* INPUTS E TABELAS */
    .stTextInput input, .stNumberInput input, .stSelectbox div, .stDateInput input {
        background-color: #2D3748; color: white; border-color: #4A5568;
    }
    div[data-testid="stDataFrame"] { background-color: #1A202C; border: 1px solid #2D3748; border-radius: 10px; }
    
    /* BOTÕES */
    div.stButton > button {
        background-color: #2D3748; color: white; border: 1px solid #4A5568; border-radius: 6px;
    }
    div.stButton > button:hover { border-color: #E53E3E; color: #E53E3E; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CONFIGURAÇÃO DO BANCO DE DADOS (SQLITE)
# ==========================================
DB_NAME = 'cmg_system.db'
BASE_DIR_ARQUIVOS = 'documentos_clientes'

if not os.path.exists(BASE_DIR_ARQUIVOS):
    os.makedirs(BASE_DIR_ARQUIVOS)

def init_db():
    """Cria as tabelas se não existirem"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Tabela Vendas
    c.execute('''
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Data TEXT,
            Consultor TEXT,
            Cliente TEXT,
            CPF TEXT,
            Servico TEXT,
            Valor REAL,
            Status_Pagamento TEXT,
            Docs TEXT
        )
    ''')
    
    # Tabela Despesas
    c.execute('''
        CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Data TEXT,
            Categoria TEXT,
            Descricao TEXT,
            Valor REAL
        )
    ''')
    conn.commit()
    conn.close()

# Inicializa o banco ao rodar o app
init_db()

def run_query(query, params=()):
    """Executa queries de modificação (INSERT/DELETE)"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def load_data(table_name):
    """Carrega dados do banco para Pandas DataFrame"""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
    conn.close()
    return df

def update_full_table(df, table_name):
    """Atualiza a tabela inteira (usado para edições/exclusões em massa)"""
    conn = sqlite3.connect(DB_NAME)
    # if_exists='replace' recria a tabela com os dados novos do dataframe
    df.to_sql(table_name, conn, if_exists='replace', index=False)
    conn.close()

# ==========================================
# 3. FUNÇÕES AUXILIARES
# ==========================================
def salvar_arquivos(arquivos, nome_cliente):
    if not arquivos: return 0
    safe_folder = "".join([c for c in nome_cliente if c.isalnum() or c in (' ', '_')]).strip().replace(" ", "_")
    caminho_cliente = os.path.join(BASE_DIR_ARQUIVOS, safe_folder)
    
    if not os.path.exists(caminho_cliente):
        os.makedirs(caminho_cliente)
        
    for arquivo in arquivos:
        with open(os.path.join(caminho_cliente, arquivo.name), "wb") as f:
            f.write(arquivo.getbuffer())
    return len(arquivos)

def converter_para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados')
    return output.getvalue()

def chat_ia(df_v, df_d, user_msg, key):
    if not key: return "⚠️ Configure sua API Key na barra lateral para usar a IA."
    try:
        client = OpenAI(api_key=key)
        # Limita contexto para economizar tokens
        contexto = f"Vendas (Últimas 15): {df_v.tail(15).to_string()}\nDespesas (Últimas 10): {df_d.tail(10).to_string()}"
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"Você é um analista financeiro da CMG. Responda curto e direto baseado em: {contexto}"},
                {"role": "user", "content": user_msg}
            ]
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"Erro IA: {e}"

# ==========================================
# 4. BARRA LATERAL (FILTROS E CONFIG)
# ==========================================
with st.sidebar:
    st.title("💎 CMG Pro")
    st.markdown("Sistema Database v8.0")
    st.divider()
    
    st.markdown("### 🔎 Busca Global")
    termo_busca = st.text_input("Buscar (Nome, CPF ou Consultor)", placeholder="Digite e dê Enter...")
    
    st.divider()
    st.markdown("### ⚙️ Configurações")
    openai_key = st.text_input("🔑 API Key (OpenAI)", type="password")
    meta_mensal = st.number_input("🎯 Meta Mensal (R$)", value=50000.0, step=1000.0)

# Carregamento Inicial dos Dados
df_vendas = load_data("vendas")
df_despesas = load_data("despesas")

# Filtro Global
df_view = df_vendas.copy()
if termo_busca:
    t = termo_busca.lower()
    mask = (
        df_view['Cliente'].astype(str).str.lower().str.contains(t) | 
        df_view['CPF'].astype(str).str.lower().str.contains(t) | 
        df_view['Consultor'].astype(str).str.lower().str.contains(t)
    )
    df_view = df_view[mask]

# ==========================================
# 5. ÁREA PRINCIPAL
# ==========================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 DASHBOARD", "👥 VENDAS", "💰 FINANCEIRO", 
    "🧮 PRECIFICAÇÃO", "📂 ARQUIVOS", "🤖 I.A."
])

# --- ABA 1: DASHBOARD ---
with tab1:
    st.markdown("### 🚀 Visão Geral de Performance")
    fat_total = df_view["Valor"].sum() if not df_view.empty else 0
    desp_total = df_despesas["Valor"].sum() if not df_despesas.empty else 0
    lucro = fat_total - desp_total
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faturamento", f"R$ {fat_total:,.2f}")
    c2.metric("Lucro Líquido", f"R$ {lucro:,.2f}", delta="Resultado")
    c3.metric("Despesas", f"R$ {desp_total:,.2f}", delta="-Saídas", delta_color="inverse")
    c4.metric("Vendas Qtd", len(df_view))
    
    st.divider()
    g1, g2 = st.columns([2, 1])
    with g1:
        if not df_view.empty:
            fig = px.bar(df_view, x="Consultor", y="Valor", color="Servico", template="plotly_dark", title="Vendas por Consultor")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
    with g2:
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number+delta", value = fat_total,
            delta = {'reference': meta_mensal},
            gauge = {'axis': {'range': [None, meta_mensal]}, 'bar': {'color': "#E53E3E"}, 'bgcolor': "#2D3748"}
        ))
        fig_gauge.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font={'color': "white"}, margin=dict(t=30,b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

# --- ABA 2: VENDAS (SQL INSERT) ---
with tab2:
    col_form, col_data = st.columns([1, 2])
    
    with col_form:
        with st.container(border=True):
            st.markdown("#### ➕ Nova Venda")
            with st.form("form_venda", clear_on_submit=True):
                consultor = st.text_input("Consultor")
                cliente = st.text_input("Cliente")
                cpf = st.text_input("CPF")
                servico = st.selectbox("Serviço", ["Limpeza de Nome", "Score", "Consultoria", "Jurídico"])
                valor = st.number_input("Valor (R$)", min_value=0.0, step=100.0)
                status = st.selectbox("Status", ["Pendente", "Pago Total", "Parcial"])
                files = st.file_uploader("Docs", accept_multiple_files=True)
                
                if st.form_submit_button("💾 SALVAR NO BANCO"):
                    if cliente:
                        qtd = salvar_arquivos(files, cliente)
                        data_hoje = datetime.now().strftime("%Y-%m-%d")
                        
                        # SQL INSERT
                        run_query('''
                            INSERT INTO vendas (Data, Consultor, Cliente, CPF, Servico, Valor, Status_Pagamento, Docs)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (data_hoje, consultor, cliente, cpf, servico, valor, status, f"{qtd} arqs"))
                        
                        st.toast("Venda salva no Banco de Dados!", icon="✅")
                        st.rerun()
                    else:
                        st.error("Nome do Cliente obrigatório.")

    with col_data:
        st.markdown("#### 📋 Base de Dados")
        
        # Download Excel
        st.download_button("📥 Baixar Excel", converter_para_excel(df_view), "vendas.xlsx")
        
        # Edição e Exclusão
        if "Excluir" not in df_view.columns: df_view.insert(0, "Excluir", False)
        
        # Ocultar ID na edição, mas manter no dataframe original para controle
        cols_config = {"id": st.column_config.NumberColumn(disabled=True), "Docs": st.column_config.TextColumn(disabled=True)}
        
        edited_df = st.data_editor(df_view, use_container_width=True, hide_index=True, column_config=cols_config)
        
        if st.button("🗑️ Salvar Alterações / Excluir Marcados"):
            if termo_busca:
                st.warning("Limpe a busca antes de excluir para evitar erros de índice.")
            else:
                # Remove marcados
                df_final = edited_df[edited_df["Excluir"] == False].drop(columns=["Excluir"])
                # Atualiza banco completo
                update_full_table(df_final, "vendas")
                st.success("Banco de Dados Atualizado!")
                st.rerun()

# --- ABA 3: FINANCEIRO (SQL INSERT) ---
with tab3:
    c1, c2 = st.columns([1, 2])
    with c1:
        with st.container(border=True):
            st.markdown("#### 💸 Nova Despesa")
            desc = st.text_input("Descrição")
            cat = st.selectbox("Categoria", ["Fixo", "Comissões", "Marketing", "Impostos"])
            val_d = st.number_input("Valor (R$)", min_value=0.0)
            
            if st.button("Registrar Saída"):
                run_query("INSERT INTO despesas (Data, Categoria, Descricao, Valor) VALUES (?, ?, ?, ?)",
                          (datetime.now().strftime("%Y-%m-%d"), cat, desc, val_d))
                st.toast("Despesa salva!", icon="💸")
                st.rerun()
    
    with c2:
        st.dataframe(df_despesas, use_container_width=True, hide_index=True)
        if not df_despesas.empty:
            fig_pie = px.pie(df_despesas, names="Categoria", values="Valor", hole=0.4, template="plotly_dark")
            fig_pie.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_pie, use_container_width=True)

# --- ABA 4: PRECIFICAÇÃO ---
with tab4:
    st.markdown("### 🧮 Calculadora de Lucro Real")
    cp1, cp2 = st.columns(2)
    with cp1:
        custo = st.number_input("Custo Operacional", value=100.0)
        imposto = st.slider("Impostos (%)", 0, 30, 6)
        comissao = st.slider("Comissão (%)", 0, 30, 10)
        lucro_meta = st.slider("Margem Lucro (%)", 0, 100, 30)
    with cp2:
        soma = imposto + comissao + lucro_meta
        if soma < 100:
            preco = custo / (1 - (soma/100))
            st.metric("PREÇO DE VENDA", f"R$ {preco:,.2f}")
            st.success(f"Lucro Líquido: R$ {preco*(lucro_meta/100):,.2f}")
        else:
            st.error("Margens somam mais de 100%!")

# --- ABA 5: ARQUIVOS ---
with tab5:
    st.markdown("### 📂 Documentos por Cliente")
    pastas = [f for f in os.listdir(BASE_DIR_ARQUIVOS) if os.path.isdir(os.path.join(BASE_DIR_ARQUIVOS, f))]
    sel = st.selectbox("Selecione:", ["--"] + pastas)
    if sel != "--":
        path = os.path.join(BASE_DIR_ARQUIVOS, sel)
        for arq in os.listdir(path):
            with open(os.path.join(path, arq), "rb") as f:
                st.download_button(f"📥 {arq}", f, file_name=arq)

# --- ABA 6: IA ---
with tab6:
    st.markdown("### 🤖 Assistente Database")
    if "msgs" not in st.session_state: st.session_state.msgs = []
    
    for m in st.session_state.msgs:
        st.chat_message(m["role"]).write(m["content"])
        
    if prompt := st.chat_input("Pergunte sobre os dados..."):
        st.session_state.msgs.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)
        with st.spinner("Consultando banco..."):
            res = chat_ia(df_vendas, df_despesas, prompt, openai_key)
            st.session_state.msgs.append({"role": "assistant", "content": res})
            st.chat_message("assistant").write(res)