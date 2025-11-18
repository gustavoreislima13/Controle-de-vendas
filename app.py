import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime

# Configuração da Página
st.set_page_config(page_title="Controle de Vendas - CMG", layout="wide")

# --- ARQUIVO ---
FILE_NAME = 'vendas.csv'

# --- FUNÇÕES ---
def load_data():
    if os.path.exists(FILE_NAME):
        df = pd.read_csv(FILE_NAME)
    else:
        df = pd.DataFrame(columns=[
            "Data", "Consultor", "Cliente", "Serviço", 
            "Valor", "Status Pagamento", "Status Serviço"
        ])
    return df

def save_data(df):
    # Remove a coluna de controle 'Excluir' antes de salvar no CSV
    if "Excluir" in df.columns:
        df = df.drop(columns=["Excluir"])
    df.to_csv(FILE_NAME, index=False)

# Carregar dados
df = load_data()

# --- BARRA LATERAL (CADASTRO E FILTROS) ---
st.sidebar.header("🔍 Filtros")
# O filtro agora fica no topo da barra lateral para ficar claro que afeta tudo
lista_consultores = df["Consultor"].unique() if not df.empty else []
filtro_consultor = st.sidebar.multiselect("Filtrar por Consultor", options=lista_consultores)

st.sidebar.divider()
st.sidebar.header("📝 Nova Venda")

with st.sidebar.form("form_venda"):
    consultor = st.text_input("Nome do Consultor")
    cliente = st.text_input("Nome do Cliente")
    servico = st.selectbox("Tipo de Serviço", ["Limpeza de Nome", "Aumento de Score", "Consultoria", "Outros"])
    valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
    status_pgto = st.selectbox("Pagamento", ["Pendente", "Parcial", "Pago Total"])
    status_servico = st.selectbox("Serviço Enviado?", ["Não", "Sim", "Em Andamento"])
    
    submitted = st.form_submit_button("Adicionar Venda")
    
    if submitted:
        if not consultor:
            st.sidebar.error("O nome do consultor é obrigatório.")
        else:
            new_data = pd.DataFrame({
                "Data": [datetime.now().strftime("%Y-%m-%d")],
                "Consultor": [consultor],
                "Cliente": [cliente],
                "Serviço": [servico],
                "Valor": [valor],
                "Status Pagamento": [status_pgto],
                "Status Serviço": [status_servico]
            })
            # Carrega o atual, adiciona e salva
            df_atual = load_data()
            df_final = pd.concat([df_atual, new_data], ignore_index=True)
            save_data(df_final)
            st.sidebar.success("Venda salva!")
            st.rerun()

# --- LÓGICA DE FILTRAGEM ---
# Se houver filtro selecionado, filtramos o DF. Se não, usamos ele inteiro.
if filtro_consultor:
    df_filtrado = df[df["Consultor"].isin(filtro_consultor)].copy()
else:
    df_filtrado = df.copy()

# --- ÁREA PRINCIPAL ---
st.title("📊 Painel de Controle de Vendas")

# --- KPIS (Baseados no filtro) ---
col1, col2, col3 = st.columns(3)
total_vendas = df_filtrado["Valor"].sum()
pendentes = df_filtrado[df_filtrado["Status Pagamento"] != "Pago Total"].shape[0]

col1.metric("Faturamento (Visão Atual)", f"R$ {total_vendas:,.2f}")
col2.metric("Vendas Listadas", df_filtrado.shape[0])
col3.metric("Pagamentos Pendentes", pendentes)

st.divider()

# --- TABELA DE EDIÇÃO COM FILTRO APLICADO ---
st.subheader(f"📝 Gerenciar Vendas {'(Filtrado)' if filtro_consultor else '(Geral)'}")

# Adiciona coluna temporária 'Excluir'
if "Excluir" not in df_filtrado.columns:
    df_filtrado.insert(0, "Excluir", False)

# Exibe o editor APENAS com as linhas filtradas
df_editado = st.data_editor(
    df_filtrado,
    use_container_width=True,
    num_rows="fixed", 
    hide_index=True,
    key="editor_vendas", # Chave única para não perder estado
    column_config={
        "Excluir": st.column_config.CheckboxColumn(
            "Excluir?",
            help="Marque para apagar esta venda",
            default=False,
        ),
        "Valor": st.column_config.NumberColumn(
            "Valor (R$)",
            format="R$ %.2f"
        ),
        "Status Pagamento": st.column_config.SelectboxColumn(
            "Status Pagamento",
            options=["Pendente", "Parcial", "Pago Total"]
        ),
        "Status Serviço": st.column_config.SelectboxColumn(
            "Status Serviço",
            options=["Não", "Sim", "Em Andamento"]
        )
    }
)

# --- BOTÃO DE SALVAR INTELIGENTE ---
if st.button("💾 Salvar Alterações na Tabela", type="primary"):
    # 1. Carrega o banco de dados ORIGINAL completo
    df_original_completo = load_data()
    
    # 2. Identifica quais linhas foram marcadas para exclusão no editor
    # Usamos o índice (index) para saber qual linha é qual no original
    indices_para_excluir = df_editado[df_editado["Excluir"] == True].index
    
    # 3. Atualiza os valores modificados
    # O método .update do pandas usa o índice para atualizar apenas as linhas correspondentes
    # Removemos a coluna 'Excluir' do editado antes de atualizar para não dar erro
    df_editado_sem_excluir = df_editado.drop(columns=["Excluir"])
    df_original_completo.update(df_editado_sem_excluir)
    
    # 4. Aplica as exclusões
    df_final_para_salvar = df_original_completo.drop(indices_para_excluir)
    
    # 5. Salva tudo
    save_data(df_final_para_salvar)
    
    st.success("Banco de dados atualizado com sucesso!")
    st.rerun()

st.divider()

# --- GRÁFICOS (Sempre seguem o filtro da tabela agora) ---
st.subheader("Análise Gráfica")
g1, g2 = st.columns(2)

with g1:
    if not df_filtrado.empty:
        fig_consultor = px.bar(df_filtrado, x="Consultor", y="Valor", color="Status Pagamento", title="Vendas Filtradas")
        st.plotly_chart(fig_consultor, use_container_width=True)

with g2:
    if not df_filtrado.empty:
        fig_pizza = px.pie(df_filtrado, names="Status Serviço", values="Valor", title="Status Serviços Filtrados")
        st.plotly_chart(fig_pizza, use_container_width=True)