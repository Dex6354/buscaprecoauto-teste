import streamlit as st
import unicodedata
import json
import re

# -----------------------------
# FUNÇÕES AUXILIARES
# -----------------------------
def remover_acentos(texto):
    if not texto:
        return ""
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    ).lower()

def ler_itens_json():
    try:
        with open("itens.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Erro ao ler itens.json: {e}")
        return []

# -----------------------------
# CONFIGURAÇÃO STREAMLIT
# -----------------------------
st.set_page_config(page_title="Comparador de Preços", page_icon="🛒", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 0rem; }
        footer, header, #MainMenu {visibility: hidden;}
        .comparison-item {
            border: none;
            border-bottom: 1px solid #ddd;
            padding: 10px;
            display: grid;
            grid-template-columns: 80px 1fr;
            grid-template-rows: auto auto auto;
            grid-template-areas:
                "image title"
                "image shibata"
                "image nagumo";
            gap: 1px 10px;
            min-height: 90px;
        }
        .comparison-item.first-comparison-item {
            border-top: 1px solid #ddd;
        }
        .product-image {
            grid-area: image;
            width: 80px;
            height: 80px;
            object-fit: contain;
            border-radius: 4px;
        }
        .price-badge { grid-area: title; }
        .market-link {
            text-decoration: none;
            display: block;
            font-size: 0.9em;
            color: red;
        }
        .logo-pequeno {
            vertical-align: middle;
            margin-right: 5px;
            height: 22px;
            width: 22px;
            object-fit: contain;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown("<h6>🛒 Busca Preço Automático</h6>", unsafe_allow_html=True)

# -----------------------------
# CARREGA RESULTADOS SALVOS
# -----------------------------
if "resultados_comparacao" not in st.session_state:
    with st.spinner("🔍 Carregando lista de itens..."):
        st.session_state.resultados_comparacao = ler_itens_json()

resultados_comparacao = st.session_state.resultados_comparacao

# -----------------------------
# CAMPO DE FILTRO RÁPIDO
# -----------------------------
filtro = st.text_input(
    "",
    placeholder="🔎 Digite para filtrar instantaneamente...",
    label_visibility="collapsed",
    key="filtro_rapido"
)

# Filtra localmente a lista já carregada
if filtro:
    termo = remover_acentos(filtro)
    resultados_filtrados = [
        item for item in resultados_comparacao
        if termo in remover_acentos(item["nome"])
    ]
else:
    resultados_filtrados = resultados_comparacao

if not resultados_filtrados:
    st.info("Nenhum item encontrado com o filtro aplicado.")
else:
    for index, item in enumerate(resultados_filtrados):
        extra_class = " first-comparison-item" if index == 0 else ""
        nome = item.get("nome", "")
        preco = item.get("preco_principal_str", "N/D")
        imagem = item.get("imagem_principal", "https://rawcdn.githack.com/gymbr/precosmercados/main/sem-imagem.png")
        shibata = item.get("shibata", "#")
        nagumo = item.get("nagumo", "#")
        shibata_preco = item.get("shibata_preco_str", "N/D")
        nagumo_preco = item.get("nagumo_preco_str", "N/D")

        st.markdown(f"""
<div class='comparison-item{extra_class}'>
  <img src="{imagem}" class='product-image' />
  <div class='price-badge'>
    <span style="font-weight: bold; font-size: 1.1em;">{nome}</span><br>
    <span style="color: #333;">{preco}</span>
  </div>
  <a href="{shibata}" target="_blank" class='market-link'>
    🏪 Shibata: {shibata_preco}
  </a>
  <a href="{nagumo}" target="_blank" class='market-link'>
    🏬 Nagumo: {nagumo_preco}
  </a>
</div>
""", unsafe_allow_html=True)
