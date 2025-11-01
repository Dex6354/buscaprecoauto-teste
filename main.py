import streamlit as st
import requests
import unicodedata
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

# ----------------------------------------------------------------------
# CONSTANTES GLOBAIS
# ----------------------------------------------------------------------
JSON_FILE = "itens.json" # Define o nome do arquivo JSON
TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJ2aXBjb21tZXJjZSIsImF1ZCI6ImFwaS1hZG1pbiIsInN1YiI6IjZiYzQ4NjdlLWRjYTktMTFlOS04NzQyLTAyMGQ3OTM1OWNhMCIsInZpcGNvbW1lcmNlQ2xpZW50ZUlkIjpudWxsLCJpYXQiOjE3NTE5MjQ5MjgsInZlciI6MSwiY2xpZW50IjpudWxsLCJvcGVyYXRvciI6bnVsbCwib3JnIjoiMTYxIn0.yDCjqkeJv7D3wJ0T_fu3AaKlX9s5PQYXD19cESwPH-j3F_Is-Zb-bDdUvduwoI_RkOeqbYCuxN0ppQQXb1ArVg"
ORG_ID = "161"
HEADERS_SHIBATA = {
    "Authorization": f"Bearer {TOKEN}",
    "organizationid": ORG_ID,
    "sessao-id": "4ea572793a132ad95d7e758a4eaf6b09",
    "domainkey": "loja.shibata.com.br",
    "User-Agent": "Mozilla/5.0"
}

# Links dos logos
LOGO_SHIBATA_URL = "https://rawcdn.githack.com/gymbr/precosmercados/main/logo-shibata.png"
LOGO_NAGUMO_URL = "https://rawcdn.githack.com/gymbr/precosmercados/main/logo-nagumo2.png"
DEFAULT_IMAGE_URL = "https://rawcdn.githack.com/gymbr/precosmercados/main/sem-imagem.png"


# ----------------------------------------------------------------------
# FUNÇÕES DE LEITURA E EXTRAÇÃO DO JSON
# ----------------------------------------------------------------------

def ler_itens_json():
    """Lê o arquivo JSON especificado pela constante JSON_FILE."""
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        st.error(f"Erro: Arquivo {JSON_FILE} não encontrado no diretório. Usando lista de fallback.")
        # Fallback list simulating the JSON content
        return [
            { "nome": "🍌 Banana Nanica R$6", "nagumo": "https://www.nagumo.com/p/banana-nanica-kg-2004", "shibata": "https://www.loja.shibata.com.br/produto/16286/banana-nanica-14kg-aprox-6-unidades" },
            { "nome": "🍌 Banana Prata R$7", "nagumo": "https://www.nagumo.com/p/banana-prata-kg-2011", "shibata": "https://www.loja.shibata.com.br/produto/16465/banana-prata-11kg-aprox-8-unidades" }
        ]
    except json.JSONDecodeError:
        st.error(f"Erro: Não foi possível decodificar o arquivo {JSON_FILE}. Verifique se o JSON está formatado corretamente.")
        return []
    except Exception as e:
        st.error(f"Erro inesperado ao ler o arquivo {JSON_FILE}: {e}")
        return []

def extrair_termos_busca(nome_completo):
    """Extrai o nome de exibição (mantido apenas para formatar o output)."""
    # Remove preços (R$XX ou R$X,XX) do nome para obter o nome de exibição limpo
    nome_sem_preco = re.sub(r'\sR\$\d+(?:[.,]\d+)?', '', nome_completo, flags=re.IGNORECASE).strip()
    return nome_sem_preco # Retorna o nome de exibição

def extract_shibata_id(url):
    """Extrai o ID do produto da URL do Shibata."""
    match = re.search(r'/produto/(\d+)/', url)
    return match.group(1) if match else None

def extract_nagumo_sku(url):
    """Extrai o SKU do produto da URL do Nagumo."""
    # O SKU geralmente é o número no final da URL
    match = re.search(r'-(\d+)$', url)
    return match.group(1) if match else None


# ----------------------------------------------------------------------
# NOVAS FUNÇÕES DE BUSCA DIRETA POR ID/SKU
# ----------------------------------------------------------------------

def fetch_shibata_product(product_id):
    """Busca um produto específico no Shibata pelo ID."""
    if not product_id:
        return None
    # Endpoint de busca direta por ID (assumindo padrão RESTful)
    url = f"https://services.vipcommerce.com.br/api-admin/v1/org/{ORG_ID}/filial/1/centro_distribuicao/1/loja/produto/{product_id}"
    try:
        response = requests.get(url, headers=HEADERS_SHIBATA, timeout=10)
        if response.status_code == 200:
            # Retorna o objeto 'produto' dentro de 'data'
            return response.json().get('data', {}).get('produto')
        return None
    except requests.exceptions.RequestException:
        return None
    except Exception:
        return None

def fetch_nagumo_product(sku):
    """Busca um produto específico no Nagumo pelo SKU usando a API GraphQL."""
    url = "https://nextgentheadless.instaleap.io/api/v3"
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://www.nagumo.com",
        "Referer": "https://www.nagumo.com/",
        "User-Agent": "Mozilla/5.0",
        "apollographql-client-name": "Ecommerce SSR",
        "apollographql-client-version": "0.11.0"
    }
    payload = {
        "operationName": "SearchProducts",
        "variables": {
            "searchProductsInput": {
                "clientId": "NAGUMO",
                "storeReference": "22",
                "currentPage": 1,
                "minScore": 1,
                "pageSize": 1,
                "search": [{"query": sku}], # Busca diretamente pelo SKU
                "filters": {},
                "googleAnalyticsSessionId": ""
            }
        },
        "query": """
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
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        products = data.get("data", {}).get("searchProducts", {}).get("products", [])
        # Confirma que o SKU retornado é o SKU buscado (evita resultados de busca ampla)
        for product in products:
            if str(product.get('sku')) == sku:
                return product
        return None
    except requests.exceptions.RequestException:
        return None
    except Exception:
        return None


# ----------------------------------------------------------------------
# FUNÇÕES DE CÁLCULO DE PREÇO UNITÁRIO (Mantidas)
# ----------------------------------------------------------------------
def remover_acentos(texto):
    if not texto: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower()

def calcular_preco_unidade(descricao, preco_total):
    desc_minus = remover_acentos(descricao)
    match_kg = re.search(r'(\d+(?:[\.,]\d+)?)\s*(kg|quilo)', desc_minus)
    if match_kg:
        peso = float(match_kg.group(1).replace(',', '.'))
        return preco_total / peso, f"R$ {preco_total / peso:.2f}".replace('.', ',') + "/kg"
    match_g = re.search(r'(\d+(?:[\.,]\d+)?)\s*(g|gramas?)', desc_minus)
    if match_g:
        peso = float(match_g.group(1).replace(',', '.')) / 1000
        return preco_total / peso, f"R$ {preco_total / peso:.2f}".replace('.', ',') + "/kg"
    match_l = re.search(r'(\d+(?:[\.,]\d+)?)\s*(l|litros?)', desc_minus)
    if match_l:
        litros = float(match_l.group(1).replace(',', '.'))
        return preco_total / litros, f"R$ {preco_total / litros:.2f}".replace('.', ',') + "/L"
    match_ml = re.search(r'(\d+(?:[\.,]\d+)?)\s*(ml|mililitros?)', desc_minus)
    if match_ml:
        litros = float(match_ml.group(1).replace(',', '.')) / 1000
        return preco_total / litros, f"R$ {preco_total / litros:.2f}".replace('.', ',') + "/L"
    return None, None

def formatar_preco_unidade_personalizado(preco_total, quantidade, unidade):
    if not unidade: return None
    unidade = unidade.lower()
    if quantidade and quantidade != 1:
        return f"R$ {preco_total:.2f}".replace('.', ',') + f"/{str(quantidade).replace('.', ',')}{unidade.lower()}"
    else:
        return f"R$ {preco_total:.2f}".replace('.', ',') + f"/{unidade.lower()}"

def contem_papel_toalha(texto):
    return "papel" in remover_acentos(texto.lower()) and "toalha" in remover_acentos(texto.lower())

def extrair_info_papel_toalha(nome, descricao):
    texto_nome = remover_acentos(nome.lower())
    texto_desc = remover_acentos(descricao.lower())
    texto_completo = f"{texto_nome} {texto_desc}"
    match = re.search(r'(\d+)\s*(un|unidades?|rolos?)\s*.*?(\d+)\s*(folhas|toalhas)', texto_completo)
    if match:
        rolos = int(match.group(1))
        folhas_por_rolo = int(match.group(3))
        total_folhas = rolos * folhas_por_rolo
        return total_folhas
    match = re.search(r'(\d+)\s*(folhas|toalhas)', texto_completo)
    if match:
        return int(match.group(1))
    m_un = re.search(r"(\d+)\s*(un|unidades?)", texto_completo)
    if m_un:
        return int(m_un.group(1))
    return None

def calcular_preco_unitario_nagumo(preco_valor, descricao, nome, unidade_api=None):
    texto_completo = f"{nome} {descricao}".lower()
    if contem_papel_toalha(texto_completo):
        total_folhas = extrair_info_papel_toalha(nome, descricao)
        if total_folhas and total_folhas > 0:
            preco_por_item = preco_valor / total_folhas
            return f"R$ {preco_por_item:.3f}/folha"
        return "Preço por folha: n/d"
    if "papel higi" in texto_completo:
        match_rolos = re.search(r"(\d+)\s*rolos?", texto_completo)
        match_metros = re.search(r"(\d+[.,]?\d*)\s*(m|metros?|mt)", texto_completo)
        if match_rolos and match_metros:
            try:
                rolos = int(match_rolos.group(1))
                metros = float(match_metros.group(1).replace(',', '.'))
                if rolos > 0 and metros > 0:
                    preco_por_metro = preco_valor / rolos / metros
                    return f"R$ {preco_por_metro:.3f}/m"
            except: pass
    
    # Lógica padrão para Kg/L/Un
    val, str_ = calcular_preco_unidade(texto_completo, preco_valor)
    if str_ and "R$" in str_: return str_
    
    # Fallback para unidade da API
    if unidade_api:
        unidade_api = unidade_api.lower()
        if unidade_api == 'kg': return f"R$ {preco_valor:.2f}/kg"
        elif unidade_api == 'l': return f"R$ {preco_valor:.2f}/L"
        elif unidade_api == 'un': return f"R$ {preco_valor:.2f}/un"
    return f"R$ {preco_valor:.2f}/un"

def extrair_valor_unitario(preco_unitario):
    match = re.search(r"R\$ (\d+[.,]?\d*)", preco_unitario)
    if match:
        return float(match.group(1).replace(',', '.'))
    return float('inf')


# ----------------------------------------------------------------------
# LÓGICA PRINCIPAL DE COMPARAÇÃO
# ----------------------------------------------------------------------
def realizar_comparacao_automatica():
    """Executa a busca por link e retorna os resultados formatados."""
    lista_itens = ler_itens_json()
    if not lista_itens:
        return []

    resultados_finais = []
    
    for item in lista_itens:
        nome_exibicao = extrair_termos_busca(item['nome'])
        
        shibata_id = extract_shibata_id(item['shibata'])
        nagumo_sku = extract_nagumo_sku(item['nagumo'])

        shibata_produto = fetch_shibata_product(shibata_id)
        nagumo_produto = fetch_nagumo_product(nagumo_sku)

        # 1. Processamento Shibata
        preco_shibata_val = float('inf')
        preco_shibata_str = "Preço indisponível"
        if shibata_produto:
            p = shibata_produto
            preco = float(p.get('preco') or 0)
            em_oferta = p.get('em_oferta', False)
            oferta_info = p.get('oferta') or {}
            preco_oferta = oferta_info.get('preco_oferta')
            preco_total = float(preco_oferta) if em_oferta and preco_oferta else preco
            descricao = p.get('descricao', '')
            quantidade_dif = p.get('quantidade_unidade_diferente')
            unidade_sigla = p.get('unidade_sigla')
            
            # Tenta calcular o preço unitário
            preco_unidade_val, preco_unidade_str_temp = calcular_preco_unidade(descricao, preco_total)
            
            if preco_unidade_val and preco_unidade_val > 0 and preco_unidade_val != float('inf'):
                preco_shibata_val = preco_unidade_val
                preco_shibata_str = preco_unidade_str_temp
            else:
                # Fallback para preço por unidade padrão do produto
                if unidade_sigla and unidade_sigla.lower() == "grande": unidade_sigla = "un"
                preco_shibata_str = formatar_preco_unidade_personalizado(preco_total, quantidade_dif, unidade_sigla or "un")
                preco_shibata_val = preco_total / (quantidade_dif if quantidade_dif else 1)
        
        # 2. Processamento Nagumo
        preco_nagumo_val = float('inf')
        preco_nagumo_str = "Preço indisponível"
        if nagumo_produto:
            p = nagumo_produto
            preco_normal = p.get("price", 0)
            promocao = p.get("promotion") or {}
            cond = promocao.get("conditions") or []
            preco_desconto = None
            if promocao.get("isActive") and isinstance(cond, list) and len(cond) > 0:
                preco_desconto = cond[0].get("price")
            preco_exibir = preco_desconto if preco_desconto else preco_normal

            preco_nagumo_str = calcular_preco_unitario_nagumo(preco_exibir, p.get('description', ''), p.get('name', ''), p.get("unit"))
            preco_nagumo_val = extrair_valor_unitario(preco_nagumo_str)


        # 3. Formata os Resultados Finais
        
        # Determina o preço mais baixo para exibição
        preco_principal_str = ""
        if preco_shibata_val <= preco_nagumo_val:
            preco_principal_str = preco_shibata_str
        elif preco_nagumo_val < preco_shibata_val:
            preco_principal_str = preco_nagumo_str
        else:
            preco_principal_str = preco_shibata_str if preco_shibata_str != "Preço indisponível" else preco_nagumo_str

        
        # Monta o objeto final
        resultados_finais.append({
            "nome": f"{nome_exibicao} ({preco_principal_str})",
            "nagumo": item['nagumo'],
            "shibata": item['shibata'],
            "shibata_preco_val": preco_shibata_val,
            "nagumo_preco_val": preco_nagumo_val
        })
        
    resultados_finais.sort(key=lambda x: min(x['shibata_preco_val'], x['nagumo_preco_val']))
    
    return resultados_finais

# ----------------------------------------------------------------------
# CONFIGURAÇÃO E EXIBIÇÃO DO STREAMLIT
# ----------------------------------------------------------------------
st.set_page_config(page_title="Comparador de Preços", page_icon="🛒", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 0rem; }
        footer {visibility: hidden;}
        #MainMenu {visibility: hidden;}
        .comparison-item {
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 10px;
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        .price-badge {
            font-weight: bold;
            font-size: 1.1em;
        }
        .market-link {
            text-decoration: none;
            display: block;
            padding: 5px 0;
        }
        .shibata-link { color: #880000; }
        .nagumo-link { color: #004488; }
    </style>
""", unsafe_allow_html=True)

st.markdown(f"<h6>🛒 Comparação Automática de Preços (Busca por Link no {JSON_FILE})</h6>", unsafe_allow_html=True)
st.markdown("Itens carregados e comparados por ID/SKU do produto.")

# Executa a comparação
with st.spinner("🔍 Buscando e comparando preços..."):
    resultados_comparacao = realizar_comparacao_automatica()

if resultados_comparacao:
    st.markdown("<h5>Resultados Comparativos (Preços Unitários Mais Baixos)</h5>", unsafe_allow_html=True)

    # Exibe os resultados na lista formatada
    for item in resultados_comparacao:
        is_shibata_melhor = item['shibata_preco_val'] <= item['nagumo_preco_val']
        
        shibata_link_style = "color: red; font-weight: bold;" if is_shibata_melhor and item['shibata_preco_val'] != float('inf') else "color: #880000;"
        nagumo_link_style = "color: red; font-weight: bold;" if not is_shibata_melhor and item['nagumo_preco_val'] != float('inf') else "color: #004488;"
        
        shibata_preco_str_final = f"R$ {item['shibata_preco_val']:.2f}".replace('.', ',') if item['shibata_preco_val'] != float('inf') else "N/D"
        nagumo_preco_str_final = f"R$ {item['nagumo_preco_val']:.2f}".replace('.', ',') if item['nagumo_preco_val'] != float('inf') else "N/D"

        st.markdown(f"""
            <div class='comparison-item'>
                <div class='price-badge'>
                    {item['nome']}
                </div>
                
                <a href="{item['shibata']}" target="_blank" class='market-link shibata-link' style="{shibata_link_style}">
                    <img src="{LOGO_SHIBATA_URL}" width="20" style="vertical-align: middle; margin-right: 5px;"/> Shibata: {shibata_preco_str_final}
                </a>
                
                <a href="{item['nagumo']}" target="_blank" class='market-link nagumo-link' style="{nagumo_link_style}">
                    <img src="{LOGO_NAGUMO_URL}" width="20" style="vertical-align: middle; margin-right: 5px;"/> Nagumo: {nagumo_preco_str_final}
                </a>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<h5>Saída JSON (Estrutura Completa)</h5>", unsafe_allow_html=True)
    st.json(resultados_comparacao)
