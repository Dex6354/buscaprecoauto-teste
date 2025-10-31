import streamlit as st
import requests
import unicodedata
import re
import json
import os
from urllib.parse import urlparse

# --- Constantes ---

# Link do logo Nagumo e imagem padrão
LOGO_NAGUMO_URL = "https://rawcdn.githack.com/gymbr/precosmercados/main/logo-nagumo2.png"
LOGO_SHIBATA_URL = "https://rawcdn.githack.com/gymbr/precosmercados/main/logo-shibata.png" # Nova constante

DEFAULT_IMAGE_URL = "https://rawcdn.githack.com/gymbr/precosmercados/main/sem-imagem.png"

# Configurações da API Nagumo
NAGUMO_API_URL = "https://nextgentheadless.instaleap.io/api/v3"
NAGUMO_HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.nagumo.com",
    "Referer": "https://www.nagumo.com/",
    "User-Agent": "Mozilla/5.0",
    "apollographql-client-name": "Ecommerce SSR",
    "apollographql-client-version": "0.11.0"
}
# Query GraphQL para buscar produtos (usada na função de busca)
NAGUMO_QUERY = """
query SearchProducts($searchProductsInput: SearchProductsInput!) {
  searchProducts(searchProductsInput: $searchProductsInput) {
    products {
      name
      price
      photosUrl
      sku
      stock
      description
      unit
      promotion {
        isActive
        type
        conditions {
          price
          priceBeforeTaxes
        }
      }
    }
  }
}
"""

# Nome do arquivo JSON
JSON_FILE = "itens.json"

# --- Funções de Leitura/Criação do JSON ---

def criar_json_padrao():
    """Cria o arquivo itens.json padrão com a nova estrutura, se ele não existir."""
    if not os.path.exists(JSON_FILE):
        st.info(f"Arquivo '{JSON_FILE}' não encontrado. Criando um arquivo de exemplo com as novas URLs...")
        # Nova estrutura de dados baseada na sua solicitação
        default_data = [
            # Preço R$6 e R$7 no nome são usados para o mock do Shibata
            { "nome": "🍌 Banana Nanica R$6", "nagumo": "https://www.nagumo.com/p/banana-nanica-kg-2004", "shibata": "https://www.loja.shibata.com.br/produto/16286/banana-nanica-14kg-aprox-6-unidades" },
            { "nome": "🍌 Banana Prata R$7", "nagumo": "https://www.nagumo.com/p/banana-prata-kg-2011", "shibata": "https://www.loja.shibata.com.br/produto/16465/banana-prata-11kg-aprox-8-unidades" }
        ]
        try:
            with open(JSON_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            st.error(f"Erro ao criar o arquivo {JSON_FILE}: {e}")
            return None
    return ler_itens_json()

def ler_itens_json():
    """Lê o arquivo itens.json e retorna a lista de itens."""
    if not os.path.exists(JSON_FILE):
        # Tenta criar o padrão se não existir.
        return criar_json_padrao()
    
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not data:
                 st.warning(f"O arquivo '{JSON_FILE}' está vazio. Tentando criar padrão...")
                 return criar_json_padrao()
            return data
    except json.JSONDecodeError:
        # Captura o erro que você mencionou
        st.error(f"Erro: O arquivo '{JSON_FILE}' contém um JSON inválido. Verifique a formatação.")
        # Opcional: tentar criar/sobrescrever com o padrão aqui se desejar recuperar
        return []
    except IOError as e:
        st.error(f"Erro ao ler o arquivo {JSON_FILE}: {e}")
        return []

# --- Funções Utilitárias ---
# (As funções remover_acentos, contem_papel_toalha, extrair_info_papel_toalha, e calcular_preco_unitario_nagumo foram omitidas por serem longas e não alteradas, mas estão no código final abaixo)

# --- Funções Utilitárias (Mantidas do código anterior) ---

def remover_acentos(texto):
    if not texto:
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower()

def contem_papel_toalha(texto):
    texto = remover_acentos(texto.lower())
    return "papel" in texto and "toalha" in texto

def extrair_info_papel_toalha(nome, descricao):
    texto_nome = remover_acentos(nome.lower())
    texto_desc = remover_acentos(descricao.lower())

    match = re.search(r'(\d+)\s*(un|unidades?|rolos?)\s*(\d+)\s*(folhas|toalhas)', texto_nome)
    if match:
        rolos = int(match.group(1))
        folhas_por_rolo = int(match.group(3))
        total_folhas = rolos * folhas_por_rolo
        return rolos, folhas_por_rolo, total_folhas, f"{rolos} {match.group(2)}, {folhas_por_rolo} {match.group(4)}"
    match = re.search(r'(\d+)\s*(folhas|toalhas)', texto_nome)
    if match:
        total_folhas = int(match.group(1))
        return None, None, total_folhas, f"{total_folhas} {match.group(2)}"
    texto_completo = f"{texto_nome} {texto_desc}"
    match = re.search(r'(\d+)\s*(un|unidades?|rolos?)\s*.*?(\d+)\s*(folhas|toalhas)', texto_completo)
    if match:
        rolos = int(match.group(1))
        folhas_por_rolo = int(match.group(3))
        total_folhas = rolos * folhas_por_rolo
        return rolos, folhas_por_rolo, total_folhas, f"{rolos} {match.group(2)}, {folhas_por_rolo} {match.group(4)}"
    match = re.search(r'(\d+)\s*(folhas|toalhas)', texto_completo)
    if match:
        total_folhas = int(match.group(1))
        return None, None, total_folhas, f"{total_folhas} {match.group(2)}"
    m_un = re.search(r"(\d+)\s*(un|unidades?)", texto_completo)
    if m_un:
        total = int(m_un.group(1))
        return None, None, total, f"{total} unidades"
    return None, None, None, None


def calcular_preco_unitario_nagumo(preco_valor, descricao, nome, unidade_api=None):
    preco_unitario = "Sem unidade"
    texto_completo = f"{nome} {descricao}".lower() 

    if contem_papel_toalha(texto_completo):
        rolos, folhas_por_rolo, total_folhas, texto_exibicao = extrair_info_papel_toalha(nome, descricao)
        if total_folhas and total_folhas > 0:
            preco_por_item = preco_valor / total_folhas
            return f"R$ {preco_por_item:.3f}/folha"
        return "Preço por folha: n/d"

    if "papel higi" in texto_completo:
        match_rolos = re.search(r"leve\s*0*(\d+)", texto_completo)
        if not match_rolos:
            match_rolos = re.search(r"\blv?\s*0*(\d+)", texto_completo)
        if not match_rolos:
            match_rolos = re.search(r"\blv?(\d+)", texto_completo)
        if not match_rolos:
            match_rolos = re.search(r"\bl\s*0*(\d+)", texto_completo)
        if not match_rolos:
            match_rolos = re.search(r"c/\s*0*(\d+)", texto_completo)
        if not match_rolos:
            match_rolos = re.search(r"(\d+)\s*rolos?", texto_completo)
        if not match_rolos:
            match_rolos = re.search(r"(\d+)\s*(un|unidades?)", texto_completo)
        match_metros = re.search(r"(\d+[.,]?\d*)\s*(m|metros?|mt)", texto_completo)
        if match_rolos and match_metros:
            try:
                rolos = int(match_rolos.group(1))
                metros = float(match_metros.group(1).replace(',', '.'))
                if rolos > 0 and metros > 0:
                    preco_por_metro = preco_valor / rolos / metros
                    return f"R$ {preco_por_metro:.3f}/m"
            except:
                pass

    fontes = [descricao.lower(), nome.lower()]
    for fonte in fontes:
        match_g = re.search(r"(\d+[.,]?\d*)\s*(g|gramas?)", fonte)
        if match_g:
            gramas = float(match_g.group(1).replace(',', '.'))
            if gramas > 0:
                return f"R$ {preco_valor / (gramas / 1000):.2f}/kg"
        match_kg = re.search(r"(\d+[.,]?\d*)\s*(kg|quilo)", fonte)
        if match_kg:
            kg = float(match_kg.group(1).replace(',', '.'))
            if kg > 0:
                return f"R$ {preco_valor / kg:.2f}/kg"
        match_ml = re.search(r"(\d+[.,]?\d*)\s*(ml|mililitros?)", fonte)
        if match_ml:
            ml = float(match_ml.group(1).replace(',', '.'))
            if ml > 0:
                return f"R$ {preco_valor / (ml / 1000):.2f}/L"
        match_l = re.search(r"(\d+[.,]?\d*)\s*(l|litros?)", fonte)
        if match_l:
            litros = float(match_l.group(1).replace(',', '.'))
            if litros > 0:
                return f"R$ {preco_valor / litros:.2f}/L"
        match_un = re.search(r"(\d+[.,]?\d*)\s*(un|unidades?)", fonte)
        if match_un:
            unidades = float(match_un.group(1).replace(',', '.'))
            if unidades > 0:
                return f"R$ {preco_valor / unidades:.2f}/un"

    if unidade_api:
        unidade_api = unidade_api.lower()
        if unidade_api == 'kg':
            return f"R$ {preco_valor:.2f}/kg"
        elif unidade_api == 'g':
            return f"R$ {preco_valor * 1000:.2f}/kg"
        elif unidade_api == 'l':
            return f"R$ {preco_valor:.2f}/L"
        elif unidade_api == 'ml':
            return f"R$ {preco_valor * 1000:.2f}/L"
        elif unidade_api == 'un':
            return f"R$ {preco_valor:.2f}/un"

    return preco_unitario

def extrair_sku_da_url_nagumo(url_nagumo: str):
    """
    Extrai o SKU do final de uma URL do Nagumo no formato '.../p/nome-do-produto-sku'.
    Ex: 'https://www.nagumo.com/p/banana-nanica-kg-2004' -> '2004'
    """
    if not url_nagumo or not isinstance(url_nagumo, str):
        return None
    
    try:
        path = urlparse(url_nagumo).path
        path_segments = [seg for seg in path.split('/') if seg]
        
        if path_segments:
            last_segment = path_segments[-1]
            
            match = re.search(r'-(\d+)$', last_segment)
            if match:
                return match.group(1)
                
    except Exception as e:
        return None
        
    return None

# --- FUNÇÃO DE BUSCA NAGUMO (Ajustada) ---

def buscar_produto_nagumo_pela_url(url_nagumo: str):
    """
    Extrai o SKU da URL do Nagumo e busca o produto na API.
    """
    sku = extrair_sku_da_url_nagumo(url_nagumo)
    
    if not sku:
        st.error(f"Não foi possível extrair o SKU da URL do Nagumo: {url_nagumo}")
        return None
        
    payload = {
        "operationName": "SearchProducts",
        "variables": {
            "searchProductsInput": {
                "clientId": "NAGUMO",
                "storeReference": "22",
                "currentPage": 1,
                "minScore": 0.1,  
                "pageSize": 10,   
                "search": [{"query": str(sku)}],
                "filters": {},
                "googleAnalyticsSessionId": ""
            }
        },
        "query": NAGUMO_QUERY
    }
    try:
        response = requests.post(NAGUMO_API_URL, headers=NAGUMO_HEADERS, json=payload, timeout=10)
        response.raise_for_status() 
        data = response.json()
        produtos = data.get("data", {}).get("searchProducts", {}).get("products", [])
        
        for produto in produtos:
            if produto.get('sku') == str(sku):
                return produto
        
        if produtos:
            return produtos[0]
            
        return None
        
    except requests.exceptions.RequestException as e:
        st.error(f"Erro de conexão com Nagumo ao buscar URL {url_nagumo} (SKU {sku}): {e}")
        return None
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar a resposta do Nagumo (URL {url_nagumo}, SKU {sku}): {e}")
        return None

# --- NOVO MOCK PARA SHIBATA ---

def buscar_produto_shibata_mock(nome_item: str):
    """
    Simula a busca do Shibata, extraindo o preço do nome do item no JSON.
    NOTA: Isso é um MOCK (simulação). A integração real precisa da API do Shibata.
    """
    match = re.search(r'R\$(\d+[.,]?\d*)', nome_item)
    if match:
        preco_str = match.group(1).replace(',', '.')
        try:
            # Retorna um preço (Float) e uma descrição simulada
            return {
                "preco": float(preco_str),
                "descricao": "Preço simulado do nome (R$/kg)",
                "unidade": "kg"
            }
        except ValueError:
            pass
    
    # Preço padrão/fallback se não encontrar no nome
    return {
        "preco": None,
        "descricao": "N/D (API indisponível/Preço não encontrado no nome)"
    }

# --- Configuração da Página Streamlit ---

st.set_page_config(page_title="Preços Nagumo vs Shibata", page_icon="🛒", layout="wide")

# CSS para customizar a aparência
st.markdown("""
    <style>
        /* CSS Geral */
        .block-container { 
            padding-top: 0rem; 
            padding-bottom: 15px !important;
            margin-bottom: 15px !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        footer {visibility: hidden;}
        #MainMenu {visibility: hidden;}
        header[data-testid="stHeader"] { display: none; }

        /* Estilos do Bloco de Produto */
        div, span, strong, small { font-size: 0.75rem !important; }
        img { max-width: 80px; height: auto; }
        hr.product-separator {
            border: none;
            border-top: 1px solid #eee;
            margin: 10px 0;
        }
        .info-cinza { color: gray; font-size: 0.8rem; }
        
        /* Layout de Preços */
        .price-container {
            display: flex;
            flex-direction: column;
            gap: 5px; /* Espaço entre Nagumo e Shibata */
            margin-top: 5px;
        }
        .price-box {
            border: 1px solid #ddd;
            padding: 5px;
            border-radius: 4px;
            font-size: 0.8rem !important;
        }
        .market-logo {
            width: 40px; /* Reduz o tamanho do logo do mercado */
            height: auto;
            margin-right: 5px;
            vertical-align: middle;
        }
        .market-header {
            font-weight: bold;
            display: flex;
            align-items: center;
        }
        .price-value {
            font-weight: bold;
            font-size: 1rem;
            color: #1e8449; /* Verde para destaque */
        }
    </style>
""", unsafe_allow_html=True)

# --- Interface Principal ---

# Cabeçalho com Logos
st.markdown(f"""
    <h5 style="display: flex; align-items: center; justify-content: center; margin-top: 1rem;">
        <img src="{LOGO_NAGUMO_URL}" width="120" alt="Nagumo" style="margin-right:15px; border-radius: 6px; border: 1.5px solid white; padding: 0px;"/>
        <img src="{LOGO_SHIBATA_URL}" width="120" alt="Shibata" style="border-radius: 6px; border: 1.5px solid white; padding: 0px;"/>
    </h5>
    <h6 style='text-align: center;'>🛒 Comparação de Preços</h6>
""", unsafe_allow_html=True)

# Carrega os itens do JSON
itens_para_buscar = ler_itens_json()

if not itens_para_buscar:
    st.error("❌ Não foi possível carregar os itens. Verifique o arquivo 'itens.json'.")
else:
    st.markdown(f"<small style='text-align: center; display: block;'>🔎 Consultando {len(itens_para_buscar)} item(ns)...</small>", unsafe_allow_html=True)
    st.markdown("---")

    with st.spinner("Buscando preços..."):
        for item in itens_para_buscar:
            url_nagumo = item.get("nagumo")
            nome_json = item.get("nome", "Item sem nome")
            
            # 1. Busca Nagumo
            p_nagumo = None
            if url_nagumo:
                p_nagumo = buscar_produto_nagumo_pela_url(url_nagumo)

            # 2. Busca/Mock Shibata
            p_shibata = buscar_produto_shibata_mock(nome_json)

            # Se nenhum dado do Nagumo for encontrado, exibe um aviso e pula a renderização detalhada
            if not p_nagumo:
                st.warning(f"Produto Nagumo não encontrado para: {nome_json}")
                st.markdown("<hr class='product-separator' />", unsafe_allow_html=True)
                continue

            # --- Processamento dos dados Nagumo (mantido) ---
            photos_list = p_nagumo.get('photosUrl')
            imagem = photos_list[0] if photos_list else DEFAULT_IMAGE_URL
            
            # Preço Nagumo
            preco_normal_nagumo = p_nagumo.get("price", 0)
            promocao = p_nagumo.get("promotion") or {}
            cond = promocao.get("conditions") or []
            preco_desconto_nagumo = None
            if promocao.get("isActive") and isinstance(cond, list) and len(cond) > 0:
                preco_desconto_nagumo = cond[0].get("price")
            preco_exibir_nagumo = preco_desconto_nagumo if preco_desconto_nagumo else preco_normal_nagumo
            
            preco_unitario_nagumo_str = calcular_preco_unitario_nagumo(
                preco_exibir_nagumo, 
                p_nagumo.get('description', ''), 
                p_nagumo.get('name', ''), 
                p_nagumo.get("unit")
            )

            # Título (com destaques para papel)
            titulo = p_nagumo['name']
            texto_completo = p_nagumo['name'] + " " + p_nagumo.get('description', '')
            # Lógica de destaque de papel (omitida aqui por brevidade, mas mantida no final)
            if contem_papel_toalha(texto_completo):
                rolos, folhas_por_rolo, total_folhas, texto_exibicao = extrair_info_papel_toalha(p_nagumo['name'], p_nagumo['description'])
                if texto_exibicao:
                    titulo += f" <span class='info-cinza'>({texto_exibicao})</span>"
            if "papel higi" in remover_acentos(titulo.lower()):
                titulo_lower = remover_acentos(titulo.lower())
                if "folha simples" in titulo_lower:
                    titulo = re.sub(r"(folha simples)", r"<span style='color:red; font-weight:bold;'>\1</span>", titulo, flags=re.IGNORECASE)
                if "folha dupla" in titulo_lower or "folha tripla" in titulo_lower:
                    titulo = re.sub(r"(folha dupla|folha tripla)", r"<span style='color:green; font-weight:bold;'>\1</span>", titulo, flags=re.IGNORECASE)


            # HTML do Preço Nagumo
            if preco_desconto_nagumo and preco_desconto_nagumo < preco_normal_nagumo:
                desconto_percentual = ((preco_normal_nagumo - preco_desconto_nagumo) / preco_normal_nagumo) * 100
                preco_nagumo_html = f"""
                    <span class='price-value'>R$ {preco_desconto_nagumo:.2f}</span>
                    <span style='color: red; font-weight: bold; font-size:0.8em;'> ({desconto_percentual:.0f}% OFF)</span><br>
                    <span style='text-decoration: line-through; color: gray; font-size:0.8em;'>R$ {preco_normal_nagumo:.2f}</span>
                """
            else:
                preco_nagumo_html = f"<span class='price-value'>R$ {preco_normal_nagumo:.2f}</span>"

            # HTML do Preço Shibata (MOCK)
            if p_shibata["preco"]:
                 # Formatação simples para o preço mock
                 preco_shibata_html = f"<span class='price-value'>R$ {p_shibata['preco']:.2f}</span>"
            else:
                 preco_shibata_html = f"<span style='color:red;'>{p_shibata['descricao']}</span>"


            # --- Renderização com Colunas ---
            # Cria duas colunas: uma para a imagem/título, outra para os preços
            col1, col2 = st.columns([1, 1.5]) 
            
            with col1:
                # Layout de Imagem e Estoque
                st.markdown(f"""
                    <div style="display: flex; align-items: flex-start; gap: 10px; margin-bottom: 0rem;">
                        <div style="flex: 0 0 auto;">
                            <img src="{imagem}" width="80" style="background-color: white; border-radius: 6px; display: block;"/>
                        </div>
                        <div style="flex: 1; word-break: break-word; overflow-wrap: anywhere;">
                            <strong>{titulo}</strong><br>
                            <div style="color: gray; font-size: 0.8em;">Estoque: {p_nagumo.get('stock', 'N/D')}</div>
                            <div style="margin-top: 4px; font-size: 0.9em; color: #666;">{preco_unitario_nagumo_str} (Nagumo Ref.)</div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

            with col2:
                # Layout de Preços Nagumo vs Shibata
                st.markdown(f"""
                    <div class="price-container">
                        <div class="price-box" style="border-color: #581845;">
                            <div class="market-header">
                                <img src="{LOGO_NAGUMO_URL}" class="market-logo" alt="Nagumo Logo"> Nagumo
                            </div>
                            {preco_nagumo_html}
                        </div>
                        
                        <div class="price-box" style="border-color: #ffc300;">
                            <div class="market-header">
                                <img src="{LOGO_SHIBATA_URL}" class="market-logo" alt="Shibata Logo"> Shibata
                            </div>
                            {preco_shibata_html}
                            <small style='color:red;'> (Preço MOCK/Simulado do nome)</small>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
            
            st.markdown("<hr class='product-separator' />", unsafe_allow_html=True)
