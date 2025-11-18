import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime

# Configuração da Página
st.set_page_config(page_title="Controle de Vendas - CMG", layout="wide")

# --- FUNÇÃO PARA CARREGAR/SALVAR DADOS ---
FILE_NAME = 'vendas.csv'

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
    # Salva o arquivo sem a coluna de controle 'Excluir'
    if "Excluir" in df.columns:
        df = df.drop(columns=["Excluir"])
    df.to_csv(FILE_NAME, index=False)

# Carregar dados iniciais
df = load_data()

# --- BARRA LATERAL (CADASTRO) ---
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
        new_data = pd.DataFrame({
            "Data": [datetime.now().strftime("%Y-%m-%d")],
            "Consultor": [consultor],
            "Cliente": [cliente],
            "Serviço": [servico],
            "Valor": [valor],
            "Status Pagamento": [status_pgto],
            "Status Serviço": [status_servico]
        })
        # Concatena e salva
        if "Excluir" in df.columns: # Remove coluna temporaria antes de juntar
            df = df.drop(columns=["Excluir"])
            
        df = pd.concat([df, new_data], ignore_index=True)
        save_data(df)
        st.rerun() # Recarrega a página para atualizar a tabela

# --- ÁREA PRINCIPAL ---
st.title("Painel de Controle de Vendas")

# --- FILTROS (Visuais apenas para os gráficos) ---
st.sidebar.divider()
st.sidebar.header("🔍 Filtros de Visualização")
filtro_consultor = st.sidebar.multiselect("Filtrar Consultor", options=df["Consultor"].unique())

# Dados filtrados para GRÁFICOS (Cópia)
df_graficos = df.copy()
if filtro_consultor:
    df_graficos = df_graficos[df_graficos["Consultor"].isin(filtro_consultor)]

# --- KPIS ---
col1, col2, col3 = st.columns(3)
total_vendas = df_graficos["Valor"].sum()
pendentes = df_graficos[df_graficos["Status Pagamento"] != "Pago Total"].shape[0]

col1.metric("Faturamento Total (Filtro)", f"R$ {total_vendas:,.2f}")
col2.metric("Vendas Visualizadas", df_graficos.shape[0])
col3.metric("Pagamentos Pendentes", pendentes)

st.divider()

# --- EDIÇÃO E TABELA ---
st.subheader("📝 Gerenciar Vendas (Editar e Excluir)")
st.info("💡 Dica: Para **Editar**, clique duas vezes na célula. Para **Excluir**, marque a caixa 'Excluir' e clique no botão abaixo.")

# Adiciona coluna temporária 'Excluir' para a interface
if "Excluir" not in df.columns:
    df.insert(0, "Excluir", False)

# Mostra a tabela editável
df_editado = st.data_editor(
    df,
    use_container_width=True,
    num_rows="fixed", # Não deixa adicionar linhas vazias por aqui (use a sidebar)
    hide_index=True,
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

# Botão para salvar as edições
col_btn, _ = st.columns([1, 4])
if col_btn.button("Salvar Alterações", type="primary"):
    # 1. Remove as linhas marcadas como 'Excluir'
    linhas_para_manter = df_editado[df_editado["Excluir"] == False]
    
    # 2. Salva no arquivo (A função save_data já remove a coluna 'Excluir')
    save_data(linhas_para_manter)
    
    st.success("Dados atualizados com sucesso!")
    st.rerun()

st.divider()

# --- GRÁFICOS ---
st.subheader("Análise Gráfica")
g1, g2 = st.columns(2)

with g1:
    if not df_graficos.empty:
        fig_consultor = px.bar(df_graficos, x="Consultor", y="Valor", color="Status Pagamento", title="Vendas por Consultor")
        st.plotly_chart(fig_consultor, use_container_width=True)

with g2:
    if not df_graficos.empty:
        fig_pizza = px.pie(df_graficos, names="Status Serviço", values="Valor", title="Status dos Envios")
        st.plotly_chart(fig_pizza, use_container_width=True)