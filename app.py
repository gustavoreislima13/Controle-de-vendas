import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime
from openai import OpenAI # Importação atualizada

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="CMG Gestão Integrada + IA", layout="wide", page_icon="🚀")

# --- FUNÇÕES DE ARQUIVOS E DADOS ---
FILE_VENDAS = 'vendas.csv'
FILE_DESPESAS = 'despesas.csv'
BASE_DIR_ARQUIVOS = 'documentos_clientes'

# Garante que a pasta de documentos existe
if not os.path.exists(BASE_DIR_ARQUIVOS):
    os.makedirs(BASE_DIR_ARQUIVOS)

def load_data(file, columns):
    if os.path.exists(file):
        return pd.read_csv(file)
    return pd.DataFrame(columns=columns)

def save_data(df, file):
    if "Excluir" in df.columns:
        df = df.drop(columns=["Excluir"])
    df.to_csv(file, index=False)

def salvar_arquivos(arquivos, nome_cliente):
    """Salva arquivos na pasta específica do cliente"""
    if not arquivos:
        return "Nenhum"
    
    # Cria pasta segura para o cliente
    safe_folder = "".join([c for c in nome_cliente if c.isalnum() or c in (' ', '_')]).strip().replace(" ", "_")
    caminho_cliente = os.path.join(BASE_DIR_ARQUIVOS, safe_folder)
    
    if not os.path.exists(caminho_cliente):
        os.makedirs(caminho_cliente)
        
    nomes_salvos = []
    for arquivo in arquivos:
        caminho_final = os.path.join(caminho_cliente, arquivo.name)
        with open(caminho_final, "wb") as f:
            f.write(arquivo.getbuffer())
        nomes_salvos.append(arquivo.name)
        
    return f"{len(nomes_salvos)} arquivos em /{safe_folder}"

# --- INTEGRAÇÃO CHATGPT REAL (CORRIGIDA PARA V1.0+) ---
def chat_com_gpt(df_vendas, df_despesas, pergunta, api_key):
    if not api_key:
        return "⚠️ Por favor, insira sua API Key da OpenAI na barra lateral para ativar a IA."
    
    try:
        # NOVA SINTAXE: Criar o cliente
        client = OpenAI(api_key=api_key)
        
        # Prepara um resumo dos dados para a IA
        resumo_vendas = df_vendas.to_csv(index=False)
        resumo_despesas = df_despesas.to_csv(index=False)
        
        prompt_sistema = f"""
        Você é um assistente financeiro experiente da empresa CMG.
        Aqui estão os dados atuais de vendas (CSV):
        {resumo_vendas}
        
        Aqui estão as despesas (CSV):
        {resumo_despesas}
        
        Responda à pergunta do usuário com base NESSES dados. Seja analítico e profissional.
        Se a pergunta for sobre metas ou lucros, calcule baseados nos números fornecidos.
        """
        
        # NOVA SINTAXE: Chamada da API
        resposta = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": pergunta}
            ]
        )
        return resposta.choices[0].message.content
    except Exception as e:
        return f"❌ Erro na IA: {str(e)}"

# --- CARREGAMENTO INICIAL ---
df_vendas = load_data(FILE_VENDAS, ["Data", "Consultor", "Cliente", "Serviço", "Valor", "Status Pagamento", "Docs"])
df_despesas = load_data(FILE_DESPESAS, ["Data", "Categoria", "Descrição", "Valor", "Status"])

# --- BARRA LATERAL ---
st.sidebar.title("⚙️ Configurações")
openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password", help="Cole sua chave aqui para ativar o Chatbot")
meta_mensal = st.sidebar.number_input("Meta Mensal (R$)", value=50000.0)
st.sidebar.divider()

# --- MÓDULOS (ABAS) ---
tab1, tab2, tab3, tab4 = st.tabs(["🤖 Chatbot IA & Dashboard", "💰 Vendas & Arquivos", "💸 Financeiro", "📂 Navegador de Arquivos"])

# ==============================================================================
# ABA 1: DASHBOARD E CHATBOT REAL
# ==============================================================================
with tab1:
    st.header("📊 Visão Estratégica")
    
    # KPIs Rápidos
    total_vendas = df_vendas["Valor"].sum()
    total_despesas = df_despesas["Valor"].sum()
    lucro = total_vendas - total_despesas
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Faturamento", f"R$ {total_vendas:,.2f}")
    k2.metric("Lucro Líquido", f"R$ {lucro:,.2f}", delta_color="normal")
    k3.metric("Despesas", f"R$ {total_despesas:,.2f}", delta="-")
    
    st.divider()
    
    # Área do Chat
    c_chat, c_hint = st.columns([2, 1])
    
    with c_chat:
        st.subheader("🤖 Fale com seus Dados (ChatGPT)")
        pergunta_user = st.text_area("Pergunte qualquer coisa sobre vendas, desempenho ou financeiro:", height=100)
        
        if st.button("Enviar para IA", type="primary"):
            with st.spinner("Analisando dados..."):
                resposta_ia = chat_com_gpt(df_vendas, df_despesas, pergunta_user, openai_api_key)
                st.info(resposta_ia)
                
    with c_hint:
        st.info("💡 **Exemplos de perguntas:**\n\n- Qual consultor teve o melhor desempenho este mês?\n- Qual a margem de lucro atual em porcentagem?\n- Liste os clientes que ainda não pagaram.\n- Faça uma análise crítica dos gastos.")

# ==============================================================================
# ABA 2: VENDAS + UPLOAD INTEGRADO + FILTROS
# ==============================================================================
with tab2:
    st.subheader("Gestão de Vendas e Contratos")
    
    # --- FORMULÁRIO COM UPLOAD ---
    with st.expander("➕ Nova Venda (Com Upload de Documentos)", expanded=False):
        with st.form("form_venda_completa", clear_on_submit=True):
            st.write("DADOS DA VENDA")
            c1, c2, c3 = st.columns(3)
            consultor = c1.text_input("Consultor")
            cliente = c2.text_input("Nome do Cliente")
            servico = c3.selectbox("Serviço", ["Limpeza de Nome", "Score", "Consultoria", "Outros"])
            
            c4, c5 = st.columns(2)
            valor = c4.number_input("Valor (R$)", min_value=0.0)
            status_pgto = c5.selectbox("Pagamento", ["Pendente", "Pago Total", "Parcial"])
            
            st.write("DOCUMENTAÇÃO")
            arquivos_upload = st.file_uploader("Anexar Comprovantes, Contratos e Docs", accept_multiple_files=True)
            
            if st.form_submit_button("Salvar Venda e Arquivos"):
                if not cliente:
                    st.error("Nome do cliente é obrigatório!")
                else:
                    # 1. Salvar Arquivos
                    status_docs = salvar_arquivos(arquivos_upload, cliente)
                    
                    # 2. Salvar Dados
                    nova_venda = pd.DataFrame([{
                        "Data": datetime.now().strftime("%Y-%m-%d"),
                        "Consultor": consultor,
                        "Cliente": cliente,
                        "Serviço": servico,
                        "Valor": valor,
                        "Status Pagamento": status_pgto,
                        "Docs": status_docs
                    }])
                    df_vendas = pd.concat([df_vendas, nova_venda], ignore_index=True)
                    save_data(df_vendas, FILE_VENDAS)
                    st.success(f"Venda salva e {status_docs} armazenados!")
                    st.rerun()

    st.divider()
    
    # --- ÁREA DE FILTRAGEM AVANÇADA ---
    st.write("### 🔍 Filtrar Vendas")
    with st.container():
        col_f1, col_f2, col_f3 = st.columns(3)
        filtro_consultor = col_f1.multiselect("Consultor", options=df_vendas["Consultor"].unique())
        filtro_status = col_f2.multiselect("Status Pagamento", options=df_vendas["Status Pagamento"].unique())
        filtro_servico = col_f3.multiselect("Serviço", options=df_vendas["Serviço"].unique())
        
        # Lógica de Filtragem
        df_filtrado = df_vendas.copy()
        if filtro_consultor:
            df_filtrado = df_filtrado[df_filtrado["Consultor"].isin(filtro_consultor)]
        if filtro_status:
            df_filtrado = df_filtrado[df_filtrado["Status Pagamento"].isin(filtro_status)]
        if filtro_servico:
            df_filtrado = df_filtrado[df_filtrado["Serviço"].isin(filtro_servico)]
            
        st.info(f"Mostrando {len(df_filtrado)} registros filtrados.")

    # --- TABELA DE DADOS ---
    # Prepara tabela para edição
    if "Excluir" not in df_filtrado.columns:
        df_filtrado.insert(0, "Excluir", False)
        
    df_editado = st.data_editor(
        df_filtrado,
        use_container_width=True,
        num_rows="fixed",
        hide_index=True,
        column_config={
            "Docs": st.column_config.TextColumn("Arquivos", disabled=True),
            "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f")
        }
    )
    
    if st.button("💾 Salvar Alterações na Tabela"):
        st.warning("A edição direta em tabelas filtradas está desativada nesta versão. Para editar, remova os filtros primeiro.")

# ==============================================================================
# ABA 3: FINANCEIRO
# ==============================================================================
with tab3:
    st.subheader("Controle de Despesas")
    with st.form("form_despesa"):
        d_desc = st.text_input("Descrição")
        d_val = st.number_input("Valor", min_value=0.0)
        if st.form_submit_button("Lançar Despesa"):
            nova_d = pd.DataFrame([{"Data": datetime.now().strftime("%Y-%m-%d"), "Categoria": "Geral", "Descrição": d_desc, "Valor": d_val, "Status": "Pago"}])
            df_despesas = pd.concat([df_despesas, nova_d], ignore_index=True)
            save_data(df_despesas, FILE_DESPESAS)
            st.rerun()
    st.dataframe(df_despesas, use_container_width=True)

# ==============================================================================
# ABA 4: NAVEGADOR DE ARQUIVOS
# ==============================================================================
with tab4:
    st.subheader("📂 Repositório de Clientes")
    st.write("Aqui você acessa os contratos e comprovantes organizados por pastas.")
    
    if os.path.exists(BASE_DIR_ARQUIVOS):
        clientes_pastas = [f for f in os.listdir(BASE_DIR_ARQUIVOS) if os.path.isdir(os.path.join(BASE_DIR_ARQUIVOS, f))]
        
        cliente_selecionado = st.selectbox("Selecione a Pasta do Cliente:", ["-- Selecione --"] + clientes_pastas)
        
        if cliente_selecionado != "-- Selecione --":
            path_cliente = os.path.join(BASE_DIR_ARQUIVOS, cliente_selecionado)
            arquivos = os.listdir(path_cliente)
            
            if arquivos:
                st.write(f"arquivos encontrados para **{cliente_selecionado}**:")
                for arq in arquivos:
                    col_a, col_b = st.columns([4, 1])
                    col_a.text(f"📄 {arq}")
                    with open(os.path.join(path_cliente, arq), "rb") as f:
                        col_b.download_button("Baixar", f, file_name=arq)
            else:
                st.warning("Pasta vazia.")