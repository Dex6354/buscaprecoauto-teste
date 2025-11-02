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
TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJ2aXBjb21tZXJjZSIsImF1ZCI6ImFwaS1hZG1pbiIsInN1YiI6IjZiYzQ4NjdlLWRjYTktMTFlOS04NzQyLTAyMGQ3OTM1OWNhMCIsInZpcGNvbW1lcmNlQ2xpZW50ZUlkIjpudWxsLCJpYXQiOjE3NTE5MjQ5MjgsInZlciI6MSwiY2xpZW50IjpudWxsLCJvcGVyYXRvciI6bnVsbCwib3JnIjoiMTYxIn0.yDCjqkeJv7D3wJ0T_fu3AaKlX9s5PQYXD19cESWpH-j3F_Is-Zb-bDdUvduwoI_RkOeqbYCuxN0ppQQXb1ArVg"
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
# URL base para a imagem do Shibata
SHIBATA_IMAGE_BASE_URL = "https://produto-assets-vipcommerce-com-br.br-se1.magaluobjects.com/500x500/"


# ----------------------------------------------------------------------
# FUNÇÕES DE LEITURA E EXTRAÇÃO DO JSON
# ----------------------------------------------------------------------

def ler_itens_json():
    """Lê o arquivo JSON especificado pela constante JSON_FILE."""
    try:
        # Tenta ler o arquivo local
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        st.error(f"Erro: Arquivo {JSON_FILE} não encontrado no diretório. Por favor, certifique-se de que ele existe.")
        return []
    except json.JSONDecodeError:
        st.error(f"Erro: Não foi possível decodificar o arquivo {JSON_FILE}. Verifique se o JSON está formatado corretamente.")
        return []
    except Exception as e:
        st.error(f"Erro inesperado ao ler o arquivo {JSON_FILE}: {e}")
        return []

def extrair_termos_busca(nome_completo):
    """Extrai o nome de busca e o nome de exibição do campo 'nome' do JSON."""
    # 1. Remove preços (R$XX ou R$X,XX) do nome
    nome_sem_preco = re.sub(r'\sR\$\d+(?:[.,]\d+)?', '', nome_completo, flags=re.IGNORECASE).strip()
    
    # 2. Assume que o termo de busca é o nome sem preço e sem emojis (apenas letras, números e espaços)
    nome_busca = re.sub(r'[^\w\s\-\/]', '', nome_sem_preco).strip()
    
    return nome_busca, nome_sem_preco # nome_busca, nome_exibicao

def extrair_preco_referencia(nome_completo):
    """Extrai o preço de referência (R$X,XX) do nome do item e retorna como float."""
    # Procura por R$X,XX ou R$X.X ou R$X
    match = re.search(r'R\$(\d+[.,]\d{2})', nome_completo)
    if not match:
        match = re.search(r'R\$(\d+[.,]\d{1})', nome_completo)
    if not match:
        match = re.search(r'R\$(\d+)', nome_completo)
    
    if match:
        # Substitui vírgula por ponto para conversão para float
        preco_str = match.group(1).replace(',', '.')
        try:
            return float(preco_str)
        except ValueError:
            return float('inf') # Preço inválido
    return float('inf') # Nenhum preço encontrado

# Funções utilitárias (mantidas)
def remover_acentos(texto):
    if not texto:
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower()

def calcular_precos_papel(descricao, preco_total):
    desc_minus = descricao.lower()
    match_leve = re.search(r'leve\s*(\d+)', desc_minus)
    if match_leve:
        q_rolos = int(match_leve.group(1))
    else:
        match_rolos = re.search(r'(\d+)\s*(rolos|unidades|uni|pacotes|pacote)', desc_minus)
        q_rolos = int(match_rolos.group(1)) if match_rolos else None
    match_metros = re.search(r'(\d+(?:[\.,]\d+)?)\s*m(?:etros)?', desc_minus)
    m_rolos = float(match_metros.group(1).replace(',', '.')) if match_metros else None
    if q_rolos and m_rolos and q_rolos > 0 and m_rolos > 0:
        preco_por_metro = preco_total / (q_rolos * m_rolos)
        return preco_por_metro, f"R$ {preco_por_metro:.3f}".replace('.', ',') + "/m"
    return None, None

def calcular_preco_unidade(descricao, preco_total):
    desc_minus = remover_acentos(descricao)
    match_kg = re.search(r'(\d+(?:[\.,]\d+)?)\s*(kg|quilo)', desc_minus)
    if match_kg:
        peso = float(match_kg.group(1).replace(',', '.'))
        if peso > 0: return preco_total / peso, f"R$ {preco_total / peso:.2f}".replace('.', ',') + "/kg"
    match_g = re.search(r'(\d+(?:[\.,]\d+)?)\s*(g|gramas?)', desc_minus)
    if match_g:
        peso = float(match_g.group(1).replace(',', '.')) / 1000
        if peso > 0: return preco_total / peso, f"R$ {preco_total / peso:.2f}".replace('.', ',') + "/kg"
    match_l = re.search(r'(\d+(?:[\.,]\d+)?)\s*(l|litros?)', desc_minus)
    if match_l:
        litros = float(match_l.group(1).replace(',', '.'))
        if litros > 0: return preco_total / litros, f"R$ {preco_total / litros:.2f}".replace('.', ',') + "/L"
    match_ml = re.search(r'(\d+(?:[\.,]\d+)?)\s*(ml|mililitros?)', desc_minus)
    if match_ml:
        litros = float(match_ml.group(1).replace(',', '.')) / 1000
        if litros > 0: return preco_total / litros, f"R$ {preco_total / litros:.2f}".replace('.', ',') + "/L"
    return None, None

def calcular_preco_papel_toalha(descricao, preco_total):
    desc = descricao.lower()
    qtd_unidades = None
    match_unidades = re.search(r'(\d+)\s*(rolos|unidades|pacotes|pacote|kits?)', desc)
    if match_unidades:
        qtd_unidades = int(match_unidades.group(1))

    folhas_por_unidade = None
    match_folhas = re.search(r'(\d+)\s*(folhas|toalhas)\s*cada', desc)
    if not match_folhas:
        match_folhas = re.search(r'(\d+)\s*(folhas|toalhas)', desc)
    if match_folhas:
        folhas_por_unidade = int(match_folhas.group(1))

    match_leve_folhas = re.search(r'leve\s*(\d+)\s*pague\s*\d+\s*folhas', desc)
    if match_leve_folhas:
        folhas_leve = int(match_leve_folhas.group(1))
        preco_por_folha = preco_total / folhas_leve if folhas_leve else None
        return folhas_leve, preco_por_folha

    match_leve_pague = re.findall(r'(\d+)', desc)
    folhas_leve = None
    if 'leve' in desc and 'folhas' in desc and match_leve_pague:
        folhas_leve = max(int(n) for n in match_leve_pague)

    match_unidades_kit = re.search(r'unidades por kit[:\- ]+(\d+)', desc)
    match_folhas_rolo = re.search(r'quantidade de folhas por (?:rolo|unidade)[:\- ]+(\d+)', desc)
    if match_unidades_kit and match_folhas_rolo:
        total_folhas = int(match_unidades_kit.group(1)) * int(match_folhas_rolo.group(1))
        preco_por_folha = preco_total / total_folhas if total_folhas else None
        return total_folhas, preco_por_folha

    if qtd_unidades and folhas_por_unidade:
        total_folhas = qtd_unidades * folhas_por_unidade
        preco_por_folha = preco_total / total_folhas if total_folhas else None
        return total_folhas, preco_por_folha

    if folhas_por_unidade:
        preco_por_folha = preco_total / folhas_por_unidade
        return folhas_por_unidade, preco_por_folha

    if folhas_leve:
        preco_por_folha = preco_total / folhas_leve
        return folhas_leve, preco_por_folha

    return None, None


def formatar_preco_unidade_personalizado(preco_total, quantidade, unidade):
    if not unidade:
        return None
    unidade = unidade.lower()
    if quantidade and quantidade != 1:
        return f"R$ {preco_total:.2f}".replace('.', ',') + f"/{str(quantidade).replace('.', ',')}{unidade.lower()}"
    else:
        return f"R$ {preco_total:.2f}".replace('.', ',') + f"/{unidade.lower()}"

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
    
    if preco_valor == 0:
        return "N/D"

    if contem_papel_toalha(texto_completo):
        rolos, folhas_por_rolo, total_folhas, texto_exibicao = extrair_info_papel_toalha(nome, descricao)
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
        elif unidade_api == 'l':
            return f"R$ {preco_valor:.2f}/L"
        elif unidade_api == 'un':
            return f"R$ {preco_valor:.2f}/un"
            
    # Fallback se nenhuma unidade for encontrada
    return f"R$ {preco_valor:.2f}/un"

def extrair_valor_unitario(preco_unitario):
    # Ajustado para lidar com formatação de 3 casas decimais (papel higiênico/toalha)
    match = re.search(r"R\$ (\d+[.,]?\d+)", preco_unitario)
    if match:
        # Usa o grupo inteiro para manter a precisão
        return float(match.group(1).replace(',', '.'))
    return float('inf')


# ----------------------------------------------------------------------
# FUNÇÕES DE BUSCA POR ID / SKU
# ----------------------------------------------------------------------

def buscar_detalhes_shibata(produto_id):
    """
    Busca os detalhes de um produto específico no Shibata pelo ID.
    Esta função resolve o erro 'OrganizationId' enviando os HEADERS corretos.
    """
    url = f"https://services.vipcommerce.com.br/api-admin/v1/org/{ORG_ID}/filial/1/centro_distribuicao/1/loja/produtos/{produto_id}/detalhes"
    try:
        response = requests.get(url, headers=HEADERS_SHIBATA, timeout=10)
        if response.status_code == 200:
            return response.json().get('data', {}).get('produto')
        else:
            st.warning(f"Shibata API (detalhes) falhou para ID {produto_id}. Status: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Erro de conexão ao buscar detalhes do Shibata (ID: {produto_id}): {e}")
        return None
    except Exception as e:
        st.error(f"Erro inesperado ao buscar detalhes do Shibata (ID: {produto_id}): {e}")
        return None

def buscar_detalhes_nagumo_por_sku(sku):
    """
    Busca os detalhes de um produto específico no Nagumo pelo SKU.
    (CORRIGIDO) Utiliza a 'SearchProducts' buscando o SKU como termo de busca.
    """
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
                "pageSize": 5, # Busca 5 por segurança
                "search": [{"query": sku}], # *** CORREÇÃO: Busca o SKU como termo
                "filters": {}, # *** CORREÇÃO: Remove o filtro que não funcionava
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
        produtos = data.get("data", {}).get("searchProducts", {}).get("products", [])
        
        if not produtos:
            st.warning(f"Nagumo API (SKU search) não encontrou o item: {sku}")
            return None
            
        # *** CORREÇÃO: Itera nos resultados para achar o SKU exato
        for produto in produtos:
            if produto.get('sku') == sku:
                return produto # Retorna o produto exato

        # Se saiu do loop, não encontrou o SKU exato
        st.warning(f"Nagumo API (SKU search) encontrou {len(produtos)} itens para '{sku}', mas NENHUM correspondeu ao SKU exato.")
        return None

    except requests.exceptions.RequestException as e:
        st.error(f"Erro de conexão ao buscar detalhes do Nagumo (SKU: {sku}): {e}")
        return None
    except Exception as e:
        st.error(f"Erro inesperado ao buscar detalhes do Nagumo (SKU: {sku}): {e}")
        return None

def processar_busca_nagumo(item):
    """Processa a busca no Nagumo por todos os SKUs no item."""
    produtos_nagumo_processados = []
    nagumo_imagem_url = None

    for nagumo_url in item.get('nagumo', []):
        match_sku = re.search(r'produto/(\d+)', nagumo_url)
        if not match_sku:
            match_sku = re.search(r'produto=(\d+)', nagumo_url)
        
        if match_sku:
            sku = match_sku.group(1)
            produto = buscar_detalhes_nagumo_por_sku(sku)
            
            if produto:
                nome = produto.get('name', '')
                descricao = produto.get('description', '') or ''
                preco_total = (produto.get("promotion") or {}).get("conditions", [{}])[0].get("price") or produto.get("price", 0)
                unidade_api = produto.get('unit')
                
                preco_unitario_str = calcular_preco_unitario_nagumo(preco_total, descricao, nome, unidade_api)
                preco_unitario_valor = extrair_valor_unitario(preco_unitario_str)

                # Imagem - Pega a primeira imagem de um item válido
                photos = produto.get('photosUrl', [])
                if photos and not nagumo_imagem_url:
                    nagumo_imagem_url = photos[0]

                p = {
                    'sku': sku,
                    'preco_total': preco_total,
                    'preco_unitario_valor': preco_unitario_valor,
                    'preco_unitario_str': preco_unitario_str,
                    'url': nagumo_url,
                    'promotion': produto.get('promotion'),
                    'price': produto.get('price'),
                }
                produtos_nagumo_processados.append(p)
            else:
                st.warning(f"Não foi possível obter detalhes do Nagumo para SKU: {sku}.")
        else:
            st.warning(f"Não foi possível extrair SKU do Nagumo da URL: {nagumo_url}.")

    produtos_nagumo_ordenados = sorted(produtos_nagumo_processados, key=lambda x: x['preco_unitario_valor'])
    return produtos_nagumo_ordenados, nagumo_imagem_url

def processar_busca_shibata(item):
    """Processa a busca no Shibata por todas as URLs no item."""
    produtos_shibata_processados = []
    shibata_imagem_url = None

    for shibata_url in item.get('shibata', []):
        match_id = re.search(r'produto-cod-(\d+)', shibata_url)
        if match_id:
            produto_id = match_id.group(1)
            produto = buscar_detalhes_shibata(produto_id)

            if produto:
                nome = produto.get('nome', '')
                descricao = produto.get('descricao', '') or ''
                
                # Preço total: Promoção > Preço Comum
                preco_total = produto.get('precoPromocional', produto.get('preco', 0))

                # Extração de preço unitário / por peso / por metro/folha
                descricao_limpa = f"{nome} {descricao}"
                
                preco_unidade_val = float('inf')
                preco_unidade_str = "Preço unitário: n/d"

                # 1. Tenta calcular por peso/litragem
                preco_unidade_val_generico, preco_un_str_generico = calcular_preco_unidade(descricao_limpa, preco_total)
                if preco_unidade_val_generico:
                    preco_unidade_val = preco_unidade_val_generico
                    preco_unidade_str = preco_un_str_generico
                
                # 2. Tenta calcular papel higiênico/toalha (preço por metro/folha é mais específico)
                if contem_papel_toalha(descricao_limpa) or "papel higi" in remover_acentos(descricao_limpa.lower()):
                    preco_por_metro_val, preco_por_metro_str = calcular_precos_papel(descricao_limpa, preco_total)
                    if preco_por_metro_val:
                        preco_unidade_val = preco_por_metro_val
                        preco_unidade_str = preco_por_metro_str.replace('.', ',')
                    else:
                        total_folhas, preco_por_folha = calcular_preco_papel_toalha(descricao_limpa, preco_total)
                        if preco_por_folha:
                            preco_unidade_val = preco_por_folha
                            preco_unidade_str = f"R$ {preco_por_folha:.3f}/folha".replace('.', ',')

                # Se ainda for float('inf') ou None, usa o preço total como unitário (fallback)
                if preco_unidade_val == float('inf') or preco_unidade_val == 0:
                    preco_unidade_val = preco_total
                    unidade_sigla = produto.get('unidadeSigla') or 'un'
                    preco_unidade_str = f"R$ {preco_total:.2f}/{unidade_sigla.lower()}".replace('.', ',')


                # Imagem - Pega a primeira imagem de um item válido
                if produto.get('produtoImagens'):
                    nome_imagem = produto['produtoImagens'][0]['nome']
                    shibata_imagem_url = f"{SHIBATA_IMAGE_BASE_URL}{nome_imagem}"
                
                # Formatação final (garantindo 2 casas para KG/L/UN e 3 para M/FOLHA)
                match_unidade_str = re.search(r"/([a-zA-Z]+)", preco_unidade_str)
                unidade = match_unidade_str.group(1).lower() if match_unidade_str else "un"
                
                if preco_unidade_val != float('inf'):
                    if unidade in ['kg', 'l', 'un']:
                        preco_unidade_str = f"R$ {preco_unidade_val:.2f}/{unidade}".replace('.', ',')
                    elif unidade in ['m', 'folha']:
                        preco_unidade_str = f"R$ {preco_unidade_val:.3f}/{unidade}".replace('.', ',')
                
                p = {
                    'id': produto_id,
                    'preco_total': preco_total,
                    'preco_unidade_val': preco_unidade_val,
                    'preco_unidade_str': preco_unidade_str,
                    'url': shibata_url,
                    'imagem_url': shibata_imagem_url
                }
                produtos_shibata_processados.append(p)
            else:
                st.warning(f"Não foi possível obter detalhes do Shibata para ID: {produto_id}.")
        else:
            st.warning(f"Não foi possível extrair ID do Shibata da URL: {shibata_url}.")

    produtos_shibata_ordenados = sorted(produtos_shibata_processados, key=lambda x: x['preco_unidade_val'])
    return produtos_shibata_ordenados, shibata_imagem_url


def obter_melhor_preco_shibata(produtos_ordenados):
    """Retorna o melhor preço unitário (valor e string formatada) do Shibata."""
    if not produtos_ordenados:
        return float('inf'), "Preço indisponível"
    
    melhor_produto = produtos_ordenados[0]
    preco_unidade_val = melhor_produto['preco_unidade_val']
    preco_unidade_str = melhor_produto['preco_unidade_str']
    
    if preco_unidade_val != float('inf') and preco_unidade_val > 0:
        return preco_unidade_val, preco_unidade_str.replace('.', ',')

    # Fallback se o cálculo falhar
    preco_total = melhor_produto.get('preco_total', 0)
    unidade_sigla = 'un' 
    return preco_total, f"R$ {preco_total:.2f}/{unidade_sigla.lower()}".replace('.', ',')

def obter_melhor_preco_nagumo(produtos_ordenados):
    """Retorna o melhor preço unitário (valor e string formatada) do Nagumo."""
    if not produtos_ordenados:
        return float('inf'), "Preço indisponível"

    melhor_produto = produtos_ordenados[0]
    preco_unitario_valor = melhor_produto['preco_unitario_valor']
    preco_unitario_str = melhor_produto['preco_unitario_str']

    if preco_unitario_valor != float('inf') and preco_unitario_valor > 0:
        return preco_unitario_valor, preco_unitario_str.replace('.', ',')

    # Fallback 
    preco_exibir = (melhor_produto.get("promotion") or {}).get("conditions", [{}])[0].get("price") or melhor_produto.get("price", 0)
    if preco_exibir == 0:
        return float('inf'), "Preço indisponível"

    return preco_exibir, f"R$ {preco_exibir:.2f}/un".replace('.', ',')

# ----------------------------------------------------------------------
# LÓGICA PRINCIPAL DE COMPARAÇÃO (AJUSTADA PARA IMAGENS)
# ----------------------------------------------------------------------
def realizar_comparacao_automatica():
    """Executa a busca para a lista de itens lida do JSON e retorna os resultados formatados."""
    lista_itens = ler_itens_json()
    if not lista_itens:
        return []

    resultados_finais = []
    for item in lista_itens:
        # Extrai o nome de exibição do JSON
        nome_completo = item['nome']
        _, nome_exibicao = extrair_termos_busca(nome_completo)

        # *** NOVA LÓGICA: EXTRAIR PREÇO DE REFERÊNCIA ***
        preco_referencia_val = extrair_preco_referencia(nome_completo)
        # **********************************************

        # Processamento paralelo (ajustado para passar 'item' completo)
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_shibata = executor.submit(processar_busca_shibata, item)
            future_nagumo = executor.submit(processar_busca_nagumo, item)
            
            produtos_shibata_ordenados, shibata_imagem_url = future_shibata.result()
            produtos_nagumo_ordenados, nagumo_imagem_url = future_nagumo.result()

        preco_shibata_val, preco_shibata_str = obter_melhor_preco_shibata(produtos_shibata_ordenados)
        preco_nagumo_val, preco_nagumo_str = obter_melhor_preco_nagumo(produtos_nagumo_ordenados)

        # Determina qual é o melhor preço entre os mercados
        shibata_disponivel = preco_shibata_val != float('inf')
        nagumo_disponivel = preco_nagumo_val != float('inf')

        is_shibata_melhor = False
        if shibata_disponivel and nagumo_disponivel:
            is_shibata_melhor = preco_shibata_val <= preco_nagumo_val
        elif shibata_disponivel:
            is_shibata_melhor = True
        elif nagumo_disponivel:
            is_shibata_melhor = False
        # else: Ambos indisponíveis, is_shibata_melhor = False

        # Preço principal a ser exibido (o menor)
        if is_shibata_melhor:
            preco_principal_str = preco_shibata_str
        elif nagumo_disponivel:
            preco_principal_str = preco_nagumo_str
        else:
            preco_principal_str = "Preço indisponível"

        # Lógica de prioridade de imagem
        imagem_principal = DEFAULT_IMAGE_URL
        if shibata_imagem_url:
            imagem_principal = shibata_imagem_url
        elif nagumo_imagem_url:
            imagem_principal = nagumo_imagem_url

        # Monta o objeto final
        resultados_finais.append({
            "nome_original_completo": item['nome'], # <-- NOME COMPLETO DO JSON
            "nome_exibicao": nome_exibicao,
            "preco_principal_str": preco_principal_str,
            "imagem_principal": imagem_principal,
            "nagumo": item['nagumo'],
            "shibata": item['shibata'],
            "shibata_preco_val": preco_shibata_val,
            "nagumo_preco_val": preco_nagumo_val,
            "preco_referencia_val": preco_referencia_val, # NOVO CAMPO
            "shibata_preco_str": preco_shibata_str,
            "nagumo_preco_str": preco_nagumo_str
        })

    resultados_finais.sort(key=lambda x: min(x['shibata_preco_val'], x['nagumo_preco_val']))
    return resultados_finais

# ----------------------------------------------------------------------
# CONFIGURAÇÃO E EXIBIÇÃO DO STREAMLIT (AJUSTADO PARA NOVO LAYOUT E ESTILO E LINKS)
# ----------------------------------------------------------------------
st.set_page_config(layout="wide")

st.markdown(f"""
<style>
/* Streamlit theme color variables (para referência) */
:root {{
    --link-color: #008cff; /* Cor padrão do link do Streamlit (Azul/Primary) */
    --text-color: #262730; /* Cor padrão do texto (Escuro) */
}}

/* Estilo para manter a cor do hiperlink mesmo após o clique (a:visited) */
/* Devido às restrições de privacidade do navegador, forçamos o visited a ter a mesma cor do link normal. */
a, .market-link, .market-link:link, .market-link:active {{
    color: var(--link-color); /* Garante que a cor base seja a do Streamlit */
    text-decoration: none;
}}
a:visited, .market-link:visited {{
    color: var(--link-color) !important; /* Mantém a cor do link como a cor padrão mesmo após o clique */
}}

.comparison-item {{
    /* Estilos existentes */
    display: flex;
    flex-direction: column;
    align-items: center;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 10px;
    margin-bottom: 20px;
    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.1);
    min-height: 380px;
    position: relative;
}}
.product-image {{
    width: 100%;
    max-width: 150px;
    height: auto;
    object-fit: contain;
    margin: 10px 0;
}}
.market-link {{
    display: flex;
    align-items: center;
    margin: 5px 0;
    width: 100%;
    justify-content: center;
    text-decoration: none; /* remove underline by default */
    font-size: 1.1em;
}}
.logo-pequeno {{
    height: 25px;
    margin-right: 5px;
    object-fit: contain;
}}
.price-badge {{
    background-color: #f0f2f6;
    border-radius: 4px;
    padding: 5px 10px;
    margin-bottom: 10px;
    text-align: center;
}}
/* Ajuste o layout para alinhar os itens horizontalmente */
div[data-testid="stHorizontalBlock"] > div {{
    width: 100%;
}}
</style>
""", unsafe_allow_html=True)


def exibir_resultados(resultados):
    """Exibe os resultados da comparação no Streamlit com o novo layout."""
    
    if not resultados:
        st.info("Nenhum resultado para exibir.")
        return
    
    # Exibe os resultados em colunas horizontais (3 por linha)
    for i in range(0, len(resultados), 3):
        cols = st.columns(3)
        for j in range(3):
            if i + j < len(resultados):
                item = resultados[i+j]
                
                with cols[j]:
                    nome_original = item['nome_original_completo']
                    shibata_disponivel = item['shibata_preco_val'] != float('inf')
                    nagumo_disponivel = item['nagumo_preco_val'] != float('inf')
                    preco_ref = item.get('preco_referencia_val', float('inf'))

                    # Determina quem é o melhor entre os mercados (para negrito)
                    is_shibata_melhor = False
                    if shibata_disponivel and nagumo_disponivel:
                        is_shibata_melhor = item['shibata_preco_val'] <= item['nagumo_preco_val']
                    elif shibata_disponivel:
                        is_shibata_melhor = True
                    # Se não for Shibata e Nagumo estiver disponível, Nagumo é o melhor

                    # Prepara as strings finais dos preços, aplicando a cor verde se for menor que a referência
                    shibata_preco_str_final = item['shibata_preco_str']
                    nagumo_preco_str_final = item['nagumo_preco_str']

                    # Lógica do preço menor que a referência (texto verde)
                    if item['shibata_preco_val'] < preco_ref and item['shibata_preco_val'] != float('inf'):
                        shibata_preco_str_final = f"<span style='color: green;'>{shibata_preco_str_final}</span>"
                        
                    if item['nagumo_preco_val'] < preco_ref and item['nagumo_preco_val'] != float('inf'):
                        nagumo_preco_str_final = f"<span style='color: green;'>{nagumo_preco_str_final}</span>"

                    # Preserva o estilo de negrito para o melhor preço entre os mercados
                    shibata_link_style = "font-weight: bold;" if is_shibata_melhor else ""
                    nagumo_link_style = "font-weight: bold;" if not is_shibata_melhor and nagumo_disponivel else ""
                    
                    # Prepara a string de referência para exibição (se for float('inf') exibe N/A)
                    preco_ref_str = f"R$ {preco_ref:.2f}" if preco_ref != float('inf') else "N/A"

                    # URL da Imagem
                    img_src = item.get('imagem_principal', DEFAULT_IMAGE_URL)
                    if not img_src:
                         img_src = DEFAULT_IMAGE_URL

                    # Bloco HTML ajustado com preço de referência e strings finais formatadas
                    st.markdown(f"""
<div class='comparison-item'>
    <span style="font-weight: bold; font-size: 1.15em; line-height: 1.2;">{nome_original}</span>
    <img src="{img_src}" class='product-image' alt="{nome_original}" />
    <div class='price-badge'>
        <span style="font-weight: normal; font-size: 1em; line-height: 1.2;">Preço Ref.: {preco_ref_str}</span>
    </div>
    <a href="{item['shibata']}" target="_blank" class='market-link shibata-link' style="{shibata_link_style}">
<img src="{LOGO_SHIBATA_URL}" class='logo-pequeno' style="background-color: white;
  padding: 2px 2px;       
  border-radius: 6px;        
  overflow: hidden;          
  height: 22px;" alt="Logo Shibata"/> {shibata_preco_str_final}
    </a>
    <a href="{item['nagumo']}" target="_blank" class='market-link nagumo-link' style="{nagumo_link_style}">
        <img src="{LOGO_NAGUMO_URL}" class='logo-pequeno' style="background-color: white; 
  border-radius: 6px;                  
  height: 24px;object-fit: cover;" alt="Logo Nagumo"/> {nagumo_preco_str_final}
    </a>
</div>
""", unsafe_allow_html=True)
                    

def main():
    st.title("Comparação de Preços Nagumo vs. Shibata")
    st.subheader("Melhor Preço Unitário por Item")
    st.write("Atualizado em 24 de Novembro de 2025") # Data de referência
    st.warning("Os preços são extraídos diretamente das APIs dos supermercados, mas podem mudar a qualquer momento e devem ser verificados na loja.")

    if st.button("Recarregar e Comparar Preços"):
        with st.spinner('Buscando preços...'):
            resultados = realizar_comparacao_automatica()
            if resultados:
                st.session_state['resultados'] = resultados
    
    # Exibe a data da última atualização do JSON (simulação)
    try:
        data_modificacao = '24/11/2025'
        st.info(f"Dados dos itens carregados em: {data_modificacao}")
    except:
        st.info("Não foi possível determinar a data de modificação dos dados.")
        
    if 'resultados' in st.session_state:
        exibir_resultados(st.session_state['resultados'])
    else:
        st.info("Clique em 'Recarregar e Comparar Preços' para iniciar a busca.")

if __name__ == '__main__':
    main()
