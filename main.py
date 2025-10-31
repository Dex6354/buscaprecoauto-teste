import streamlit as st
import requests
import unicodedata
import re
import json
import os

# --- Constantes ---

# Link do logo Nagumo e imagem padrão
LOGO_NAGUMO_URL = "https://rawcdn.githack.com/gymbr/precosmercados/main/logo-nagumo2.png"
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
    """Cria o arquivo itens.json padrão se ele não existir."""
    if not os.path.exists(JSON_FILE):
        st.info(f"Arquivo '{JSON_FILE}' não encontrado. Criando um arquivo de exemplo...")
        default_data = [
            { "nome": "🍌 Banana Nanica", "sku": "2004" },
            { "nome": "🍌 Banana Prata", "sku": "2011" },
            { "nome": "🍎 Maçã Gala", "sku": "2023" },
            { "nome": "🧻 Papel Higiênico Neve", "sku": "117215" }
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
        return criar_json_padrao()
    
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except json.JSONDecodeError:
        st.error(f"Erro: O arquivo '{JSON_FILE}' contém um JSON inválido.")
        return []
    except IOError as e:
        st.error(f"Erro ao ler o arquivo {JSON_FILE}: {e}")
        return []

# --- Funções Utilitárias (Copiadas do script original) ---

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

    # Prioritize name for unit information
    # Pattern 1: X Un Y Folhas (e.g., "Papel Toalha Kitchen Com 2Un 60 Folhas")
    match = re.search(r'(\d+)\s*(un|unidades?|rolos?)\s*(\d+)\s*(folhas|toalhas)', texto_nome)
    if match:
        rolos = int(match.group(1))
        folhas_por_rolo = int(match.group(3))
        total_folhas = rolos * folhas_por_rolo
        return rolos, folhas_por_rolo, total_folhas, f"{rolos} {match.group(2)}, {folhas_por_rolo} {match.group(4)}"

    # Pattern 2: X Folhas (e.g., "Papel Toalha 200 Folhas")
    match = re.search(r'(\d+)\s*(folhas|toalhas)', texto_nome)
    if match:
        total_folhas = int(match.group(1))
        return None, None, total_folhas, f"{total_folhas} {match.group(2)}"

    # If not in name, try description with the same priority
    texto_completo = f"{texto_nome} {texto_desc}" # Combine for broader search if not found in name

    # Pattern 1 (from description): X Un Y Folhas
    match = re.search(r'(\d+)\s*(un|unidades?|rolos?)\s*.*?(\d+)\s*(folhas|toalhas)', texto_completo)
    if match:
        rolos = int(match.group(1))
        folhas_por_rolo = int(match.group(3))
        total_folhas = rolos * folhas_por_rolo
        return rolos, folhas_por_rolo, total_folhas, f"{rolos} {match.group(2)}, {folhas_por_rolo} {match.group(4)}"

    # Pattern 2 (from description): X Folhas
    match = re.search(r'(\d+)\s*(folhas|toalhas)', texto_completo)
    if match:
        total_folhas = int(match.group(1))
        return None, None, total_folhas, f"{total_folhas} {match.group(2)}"

    # Pattern 3: X Unidades (general unit, less specific for paper towels)
    m_un = re.search(r"(\d+)\s*(un|unidades?)", texto_completo)
    if m_un:
        total = int(m_un.group(1))
        return None, None, total, f"{total} unidades"

    return None, None, None, None


def calcular_preco_unitario_nagumo(preco_valor, descricao, nome, unidade_api=None):
    preco_unitario = "Sem unidade"
    texto_completo = f"{nome} {descricao}".lower() # Combine name and description for unit extraction

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

    # General unit extraction (for other products)
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

# --- Nova Função de API (Busca por SKU) ---

def buscar_produto_nagumo_por_sku(sku: str):
    """
    Busca um produto específico no Nagumo usando o SKU.
    """
    payload = {
        "operationName": "SearchProducts",
        "variables": {
            "searchProductsInput": {
                "clientId": "NAGUMO",
                "storeReference": "22",
                "currentPage": 1,
                "minScore": 0.1,  # Score baixo, pois o filtro é o principal
                "pageSize": 5,    # Buscar poucos, já que o SKU deve ser único
                "search": [],     # Não usamos busca por termo
                "filters": {"sku": [str(sku)]}, # Filtro por SKU
                "googleAnalyticsSessionId": ""
            }
        },
        "query": NAGUMO_QUERY
    }
    try:
        response = requests.post(NAGUMO_API_URL, headers=NAGUMO_HEADERS, json=payload, timeout=10)
        response.raise_for_status() # Lança erro para status HTTP ruins
        data = response.json()
        produtos = data.get("data", {}).get("searchProducts", {}).get("products", [])
        
        # Garante que estamos pegando o SKU exato
        for produto in produtos:
            if produto.get('sku') == str(sku):
                return produto
        
        # Fallback: se não encontrar o SKU exato (improvável), retorna o primeiro
        if produtos:
            return produtos[0]
            
        return None # Nenhum produto encontrado
        
    except requests.exceptions.RequestException as e:
        st.error(f"Erro de conexão com Nagumo ao buscar SKU {sku}: {e}")
        return None
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar a resposta do Nagumo (SKU {sku}): {e}")
        return None

# --- Configuração da Página Streamlit ---

st.set_page_config(page_title="Preços Nagumo", page_icon="🛒", layout="wide")

# CSS para customizar a aparência (baseado no script original)
st.markdown("""
    <style>
        .block-container { 
            padding-top: 0rem; 
            padding-bottom: 15px !important;
            margin-bottom: 15px !important;
            /* Remove o padding lateral excessivo para layout de coluna única */
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        footer {visibility: hidden;}
        #MainMenu {visibility: hidden;}
        header[data-testid="stHeader"] { display: none; }

        /* Estilos do Bloco de Produto (copiado do original) */
        div, span, strong, small { font-size: 0.75rem !important; }
        img { max-width: 100px; height: auto; }
        hr.product-separator {
            border: none;
            border-top: 1px solid #eee;
            margin: 10px 0;
        }
        .info-cinza {
            color: gray;
            font-size: 0.8rem;
        }
    </style>
""", unsafe_allow_html=True)

# --- Interface Principal ---

# Cabeçalho com Logo
st.markdown(f"""
    <h5 style="display: flex; align-items: center; justify-content: center; margin-top: 1rem;">
        <img src="{LOGO_NAGUMO_URL}" width="120" alt="Nagumo" style="margin-right:8px; border-radius: 6px; border: 1.5px solid white; padding: 0px;"/>
    </h5>
    <h6 style='text-align: center;'>🛒 Preços Nagumo</h6>
""", unsafe_allow_html=True)

# Carrega os itens do JSON
itens_para_buscar = ler_itens_json()

if not itens_para_buscar:
    st.warning(f"Nenhum item encontrado em '{JSON_FILE}'. Por favor, crie o arquivo ou adicione itens a ele.")
else:
    st.markdown(f"<small style='text-align: center; display: block;'>🔎 Consultando {len(itens_para_buscar)} item(ns)...</small>", unsafe_allow_html=True)
    st.markdown("---")

    with st.spinner("Buscando preços no Nagumo..."):
        for item in itens_para_buscar:
            sku = item.get("sku")
            nome_json = item.get("nome", "Item sem nome")

            if not sku:
                st.warning(f"Item '{nome_json}' não possui 'sku' no arquivo JSON. Pulando.")
                continue

            # Busca o produto na API pelo SKU
            p = buscar_produto_nagumo_por_sku(str(sku))

            if not p:
                st.warning(f"Produto não encontrado para SKU: {sku} ({nome_json})")
                st.markdown("<hr class='product-separator' />", unsafe_allow_html=True)
                continue

            # --- Processamento dos dados (copiado do script original) ---
            
            # Imagem
            photos_list = p.get('photosUrl')
            imagem = photos_list[0] if photos_list else DEFAULT_IMAGE_URL

            # Preço
            preco_normal = p.get("price", 0)
            promocao = p.get("promotion") or {}
            cond = promocao.get("conditions") or []
            preco_desconto = None
            
            if promocao.get("isActive") and isinstance(cond, list) and len(cond) > 0:
                preco_desconto = cond[0].get("price")
            
            preco_exibir = preco_desconto if preco_desconto else preco_normal
            
            # Preço Unitário
            preco_unitario_str = calcular_preco_unitario_nagumo(
                preco_exibir, 
                p.get('description', ''), 
                p.get('name', ''), 
                p.get("unit")
            )

            # Título (com destaques para papel)
            titulo = p['name']
            texto_completo = p['name'] + " " + p.get('description', '')
            if contem_papel_toalha(texto_completo):
                rolos, folhas_por_rolo, total_folhas, texto_exibicao = extrair_info_papel_toalha(p['name'], p['description'])
                if texto_exibicao:
                    titulo += f" <span class='info-cinza'>({texto_exibicao})</span>"
            if "papel higi" in remover_acentos(titulo.lower()):
                titulo_lower = remover_acentos(titulo.lower())
                if "folha simples" in titulo_lower:
                    titulo = re.sub(r"(folha simples)", r"<span style='color:red; font-weight:bold;'>\1</span>", titulo, flags=re.IGNORECASE)
                if "folha dupla" in titulo_lower or "folha tripla" in titulo_lower:
                    titulo = re.sub(r"(folha dupla|folha tripla)", r"<span style='color:green; font-weight:bold;'>\1</span>", titulo, flags=re.IGNORECASE)

            # HTML do Preço
            if preco_desconto and preco_desconto < preco_normal:
                desconto_percentual = ((preco_normal - preco_desconto) / preco_normal) * 100
                preco_html = f"""
                    <span style='font-weight: bold; font-size: 1rem;'>R$ {preco_desconto:.2f}</span><br>
                    <span style='color: red; font-weight: bold;'> ({desconto_percentual:.0f}% OFF)</span><br>
                    <span style='text-decoration: line-through; color: gray;'>R$ {preco_normal:.2f}</span>
                """
            else:
                preco_html = f"<span style='font-weight: bold; font-size: 1rem;'>R$ {preco_normal:.2f}</span>"
            
            # Estoque
            estoque = p.get('stock', 'N/D')

            # --- Renderização do Produto (HTML copiado do original) ---
            st.markdown(f"""
                <div style="display: flex; align-items: flex-start; gap: 10px; margin-bottom: 0rem; flex-wrap: wrap;">
                    <div style="flex: 0 0 auto;">
                        <img src="{imagem}" width="80" style="background-color: white; border-top-left-radius: 6px; border-top-right-radius: 6px; border-bottom-left-radius: 0; border-bottom-right-radius: 0; display: block;"/>
                        <img src="{LOGO_NAGUMO_URL}" width="80" style="border-top-left-radius: 0; border-top-right-radius: 0; border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; border: 1.5px solid white; padding: 0px; display: block;"/>
                    </div>
                    <div style="flex: 1; word-break: break-word; overflow-wrap: anywhere;">
                        <strong>{titulo}</strong><br>
                        <strong>{preco_html}</strong><br>
                        <div style="margin-top: 4px; font-size: 0.9em; color: #666;">{preco_unitario_str}</div>
                        <div style="color: gray; font-size: 0.8em;">Estoque: {estoque}</div>
                    </div>
                </div>
                <hr class='product-separator' />
            """, unsafe_allow_html=True)
