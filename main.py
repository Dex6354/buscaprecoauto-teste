import streamlit as st
import requests
import json
import re

# --- CONFIGURAÇÕES GERAIS ---
st.set_page_config(page_title="Preços Nagumo", page_icon="🛒", layout="wide")

LOGO_NAGUMO = "https://rawcdn.githack.com/gymbr/precosmercados/main/logo-nagumo2.png"
IMG_PADRAO = "https://rawcdn.githack.com/gymbr/precosmercados/main/sem-imagem.png"

# --- CSS ---
st.markdown("""
<style>
    footer, #MainMenu, header {visibility: hidden;}
    .block-container { padding-top: 0rem; max-width: 600px; margin: auto; }
    img { max-width: 100%; height: auto; border-radius: 8px; }
    .produto {
        border: 1px solid #eee;
        border-radius: 12px;
        padding: 10px;
        margin-bottom: 15px;
        background-color: white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .preco-antigo {
        text-decoration: line-through;
        color: gray;
        font-size: 0.85em;
    }
    .preco-promocao {
        color: red;
        font-weight: bold;
        font-size: 0.9em;
    }
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<h4 style='text-align:center;'>🛒 Preços Nagumo</h4>
<img src='{LOGO_NAGUMO}' width='100' style='display:block;margin:auto;border-radius:8px;'>
""", unsafe_allow_html=True)

# --- FUNÇÃO DE BUSCA ---
def buscar_produto_por_sku(sku):
    url = "https://nextgentheadless.instaleap.io/api/v3"
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://www.nagumo.com",
        "Referer": "https://www.nagumo.com/",
        "User-Agent": "Mozilla/5.0"
    }

    payload = {
        "operationName": "GetProductBySku",
        "variables": {"getProductInput": {"clientId": "NAGUMO", "storeReference": "22", "sku": str(sku)}},
        "query": """
        query GetProductBySku($getProductInput: GetProductInput!) {
          getProduct(getProductInput: $getProductInput) {
            name
            description
            price
            photosUrl
            stock
            unit
            promotion {
              isActive
              conditions { price }
            }
          }
        }
        """
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        data = resp.json()
        return data.get("data", {}).get("getProduct", {})
    except Exception as e:
        st.error(f"Erro ao buscar SKU {sku}: {e}")
        return {}

# --- LEITURA DO JSON ---
with open("itens.json", "r", encoding="utf-8") as f:
    itens = json.load(f)

# --- EXIBIÇÃO ---
for item in itens:
    nome = item.get("nome")
    sku = item.get("sku")

    produto = buscar_produto_por_sku(sku)
    if not produto:
        st.warning(f"❌ Produto não encontrado: {nome}")
        continue

    preco = produto.get("price", 0)
    promocao = produto.get("promotion") or {}
    cond = (promocao.get("conditions") or [])
    preco_desconto = None
    if promocao.get("isActive") and len(cond) > 0:
        preco_desconto = cond[0].get("price")

    imagem = (produto.get("photosUrl") or [IMG_PADRAO])[0]
    descricao = produto.get("description", "")
    unidade = produto.get("unit", "un")
    estoque = produto.get("stock", 0)

    st.markdown("<div class='produto'>", unsafe_allow_html=True)
    st.image(imagem)
    st.markdown(f"<b>{nome}</b><br><small>{descricao}</small>", unsafe_allow_html=True)

    if preco_desconto and preco_desconto < preco:
        desconto_pct = ((preco - preco_desconto) / preco) * 100
        st.markdown(f"""
        <div>
            <span style='font-weight:bold;'>R$ {preco_desconto:.2f}</span>
            <span class='preco-promocao'> (-{desconto_pct:.0f}% OFF)</span><br>
            <span class='preco-antigo'>R$ {preco:.2f}</span><br>
            <span style='color:gray;'>Unidade: {unidade}</span><br>
            <span style='color:gray;'>Estoque: {estoque}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div>
            <b>R$ {preco:.2f}</b><br>
            <span style='color:gray;'>Unidade: {unidade}</span><br>
            <span style='color:gray;'>Estoque: {estoque}</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)
