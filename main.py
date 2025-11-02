import streamlit as st
import requests
import unicodedata
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed # Importação importante

# ----------------------------------------------------------------------
# CONSTANTES GLOBAIS
# ----------------------------------------------------------------------
JSON_FILE = "itens.json" # Define o nome do arquivo JSON
TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJ2aXBjb21tZXJjZSIsImF1ZCI6ImFwaS1hZG1pbiIsInN1YiI6IjZiYzQ4NjdlLWRjYTktMTFlOS04NzQyLTAyMGQ3OTM1OWNhMCIsInZpcGNvbW1lcmNlQ2xpZW50ZUlkIjpudWxsLCJpYXQiOjE3NTE5MjQ5MjgsInZlciI6MSwiY2xpZW50IjpudWxsLCJvcGVyYXRvciI6bnVsbCwib3JnIjoiMTYxIn0.yDCjqkeJv7D3wJJ0T_fu3AaKlX9s5PQYXD19cESWpH-j3F_Is-Zb-bDdUvduwoI_RkOeqbYCuxN0ppQQXb1ArVg"
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

# *** EXTRAI O VALOR DE PREÇO DO NOME DO ITEM NO JSON ***
def extrair_preco_do_nome(nome_completo):
    """Extrai o primeiro preço (R$X,XX ou R$X.XX) do nome completo e retorna como float."""
    match = re.search(r'R\$(\s*\d+(?:[.,]\d+)?)', nome_completo, flags=re.IGNORECASE)
    if match:
        # Substitui a vírgula por ponto para conversão para float
        preco_str = match.group(1).strip().replace(',', '.')
        try:
            return float(preco_str)
        except ValueError:
            return None
    return None

# ----------------------------------------------------------------------
# FUNÇÕES DE CÁLCULO DE PREÇO UNITÁRIO
# ----------------------------------------------------------------------

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
    """
    url = f"https://services.vipcommerce.com.br/api-admin/v1/org/{ORG_ID}/filial/1/centro_distribuicao/1/loja/produtos/{produto_id}/detalhes"
    try:
        response = requests.get(url, headers=HEADERS_SHIBATA, timeout=10)
        if response.status_code == 200:
            return response.json().get('data', {}).get('produto')
        else:
            # Não usa st.warning/error aqui para evitar problemas de thread
            return None
    except requests.exceptions.RequestException:
        return None
    except Exception:
        return None

def buscar_detalhes_nagumo_por_sku(sku):
    """
    Busca os detalhes de um produto específico no Nagumo pelo SKU.
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
                "pageSize": 5, 
                "search": [{"query": sku}], 
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
        produtos = data.get("data", {}).get("searchProducts", {}).get("products", [])
        
        if not produtos:
            return None

        # Itera nos resultados para achar o SKU exato
        for produto in produtos:
            if produto.get('sku') == sku:
                return produto 
        
        return None

    except requests.exceptions.RequestException:
        return None
    except Exception:
        return None

# ----------------------------------------------------------------------
# FUNÇÕES DE PROCESSAMENTO PARA OBTENÇÃO DO MELHOR PREÇO UNITÁRIO
# ----------------------------------------------------------------------

def obter_melhor_preco_shibata(produtos_ordenados):
    """
    Retorna o melhor preço unitário (valor e string formatada) 
    e o preço total do Shibata.
    """
    if not produtos_ordenados:
        return float('inf'), "Preço indisponível", float('inf') 

    melhor_produto = produtos_ordenados[0]
    preco_total = float(melhor_produto.get('preco_oferta') or melhor_produto.get('preco') or 0)
    
    if preco_total == 0:
        return float('inf'), "Preço indisponível", float('inf')
    
    preco_unidade_str = f"R$ {preco_total:.2f}/un".replace('.', ',') 
    preco_unidade_val = preco_total 
    
    if 'preco_unidade_val' in melhor_produto and melhor_produto['preco_unidade_val'] != float('inf') and melhor_produto['preco_unidade_val'] > 0:
        preco_unidade_val = melhor_produto['preco_unidade_val']
        preco_unidade_str = melhor_produto.get('preco_unidade_str', 'R$ 0,00/un')
        
        match = re.search(r"/([a-zA-Z]+)", preco_unidade_str)
        unidade = match.group(1).lower() if match else "un"
        
        if unidade in ['kg', 'l', 'un']:
            preco_unidade_str = f"R$ {preco_unidade_val:.2f}/{unidade}".replace('.', ',')
        elif unidade in ['m', 'folha']:
            preco_unidade_str = f"R$ {preco_unidade_val:.3f}/{unidade}".replace('.', ',')
        else:
            preco_unidade_str = preco_unidade_str.replace('.', ',')
        
        return preco_unidade_val, preco_unidade_str, preco_total 
    
    unidade_sigla = melhor_produto.get('unidade_sigla') or 'un'
    return preco_total, f"R$ {preco_total:.2f}/{unidade_sigla.lower()}".replace('.', ','), preco_total

def obter_melhor_preco_nagumo(produtos_ordenados):
    """
    Retorna o melhor preço unitário (valor e string formatada) 
    e o preço total do Nagumo.
    """
    if not produtos_ordenados:
        return float('inf'), "Preço indisponível", float('inf')

    melhor_produto = produtos_ordenados[0]
    preco_unitario_valor = melhor_produto['preco_unitario_valor']
    preco_unitario_str = melhor_produto['preco_unitario_str']
    
    # Preço total (exibido na loja, seja em promoção ou normal)
    preco_total = (melhor_produto.get("promotion") or {}).get("conditions", [{}])[0].get("price") or melhor_produto.get("price", 0)
    
    if preco_unitario_valor != float('inf') and preco_unitario_valor > 0:
        return preco_unitario_valor, preco_unitario_str.replace('.', ','), preco_total
        
    # Fallback
    if preco_total == 0:
         return float('inf'), "Preço indisponível", float('inf') 
         
    return preco_total, f"R$ {preco_total:.2f}/un".replace('.', ','), preco_total

# ----------------------------------------------------------------------
# FUNÇÃO DE PROCESSAMENTO DE ITEM (CORE LÓGICA)
# ----------------------------------------------------------------------
def processar_item(item):
    """Processa a busca de preços para um único item em paralelo."""
    
    # 1. Extração de informações do JSON
    nome_completo = item['nome']
    _, nome_exibicao = extrair_termos_busca(nome_completo)
    preco_referencia_nome = extrair_preco_do_nome(nome_completo)
    
    shibata_url = item['shibata']
    nagumo_url = item['nagumo']
    
    produtos_shibata_processados = []
    shibata_imagem_url = None
    
    # ----------------------------------------------------------------------
    # 2. Busca e Processamento Shibata (POR ID)
    # ----------------------------------------------------------------------
    match_shibata_id = re.search(r'/produto/(\d+)', shibata_url)
    
    if match_shibata_id:
        produto_id = match_shibata_id.group(1)
        p = buscar_detalhes_shibata(produto_id) # p = 'produto_detalhe'
        
        if p and p.get("disponivel", True):
            preco = float(p.get('preco') or 0)
            em_oferta = p.get('em_oferta', False)
            preco_oferta = p.get('preco_oferta')
            
            imagem_nome = p.get('imagem')
            if imagem_nome:
                shibata_imagem_url = f"{SHIBATA_IMAGE_BASE_URL}{imagem_nome}"
            
            if not preco_oferta:
                oferta_info = p.get('oferta') or {}
                preco_oferta = oferta_info.get('preco_oferta')
                
            preco_total = float(preco_oferta) if em_oferta and preco_oferta else preco
            
            descricao = p.get('descricao', '')
            quantidade_dif = p.get('quantidade_unidade_diferente')
            unidade_sigla = p.get('unidade_sigla')
            if unidade_sigla and unidade_sigla.lower() == "grande": unidade_sigla = None
            
            preco_unidade_str = formatar_preco_unidade_personalizado(preco_total, quantidade_dif, unidade_sigla)
            
            descricao_limpa = descricao.lower().replace('grande', '').strip()
            
            preco_unidade_val, preco_un_str_papel = calcular_precos_papel(descricao, preco_total)
            if preco_un_str_papel:
                 preco_unidade_str = preco_un_str_papel
            
            if not preco_unidade_val:
                preco_unidade_val, preco_un_str_generico = calcular_preco_unidade(descricao_limpa, preco_total)
                if preco_un_str_generico:
                    preco_unidade_str = preco_un_str_generico

            match = re.search(r"/\s*([\d.,]+)\s*(kg|g|l|ml)", str(preco_unidade_str).lower())
            if match:
                try:
                    quantidade = float(match.group(1).replace(",", "."))
                    unidade = match.group(2).lower()
                    if unidade == "g": quantidade /= 1000
                    elif unidade == "ml": quantidade /= 1000
                    if quantidade > 0:
                        preco_unidade_val = preco_total / quantidade
                except: pass
            
            if contem_papel_toalha(f"{p.get('nome', '')} {descricao}"):
                total_folhas, preco_por_folha = calcular_preco_papel_toalha(f"{p.get('nome', '')} {descricao}", preco_total)
                if preco_por_folha:
                    preco_unidade_val = preco_por_folha
                    preco_unidade_str = f"R$ {preco_por_folha:.3f}/folha".replace('.', ',')

            preco_por_metro_val, preco_por_metro_str = calcular_precos_papel(descricao, preco_total)
            if preco_por_metro_val:
                 preco_unidade_val = preco_por_metro_val 
                 preco_unidade_str = preco_por_metro_str.replace('.', ',')
            
            if not preco_unidade_val or preco_unidade_val == float('inf') or preco_unidade_val == 0: 
                 preco_unidade_val = preco_total
            
            p['preco_unidade_val'] = preco_unidade_val
            p['preco_unidade_str'] = preco_unidade_str 
            p['imagem_url'] = shibata_imagem_url
            
            produtos_shibata_processados.append(p)

    produtos_shibata_ordenados = sorted(produtos_shibata_processados, key=lambda x: x['preco_unidade_val'])

    # ----------------------------------------------------------------------
    # 3. Busca e Processamento Nagumo (POR SKU)
    # ----------------------------------------------------------------------
    produtos_nagumo_processados = []
    nagumo_imagem_url = None
    
    sku_match_list = re.findall(r'(\d+)', nagumo_url.split('?')[0])
    sku = sku_match_list[-1] if sku_match_list else None
    
    if sku and sku.isdigit():
        produto = buscar_detalhes_nagumo_por_sku(sku)
        
        if produto and (produto.get('stock', 0) > 0 or produto.get('stock') is None):
            preco_normal = produto.get("price", 0)
            promocao = produto.get("promotion") or {}
            cond = promocao.get("conditions") or []
            preco_desconto = None
            if promocao.get("isActive") and isinstance(cond, list) and len(cond) > 0:
                preco_desconto = cond[0].get("price")
            preco_exibir = preco_desconto if preco_desconto else preco_normal
            
            photos = produto.get('photosUrl')
            if photos and isinstance(photos, list) and len(photos) > 0:
                nagumo_imagem_url = photos[0]

            produto['preco_unitario_str'] = calcular_preco_unitario_nagumo(preco_exibir, produto.get('description', ''), produto['name'], produto.get("unit"))
            produto['preco_unitario_valor'] = extrair_valor_unitario(produto['preco_unitario_str'])
            
            produtos_nagumo_processados.append(produto)

    produtos_nagumo_ordenados = sorted(produtos_nagumo_processados, key=lambda x: x['preco_unitario_valor'])

    # ----------------------------------------------------------------------
    # 4. Formata os Resultados Finais
    # ----------------------------------------------------------------------
    preco_shibata_val, preco_shibata_str, shibata_total_val = obter_melhor_preco_shibata(produtos_shibata_ordenados)
    preco_nagumo_val, preco_nagumo_str, nagumo_total_val = obter_melhor_preco_nagumo(produtos_nagumo_ordenados)

    imagem_principal = DEFAULT_IMAGE_URL
    if produtos_shibata_ordenados and produtos_shibata_ordenados[0].get('imagem_url'):
        imagem_principal = produtos_shibata_ordenados[0]['imagem_url']
    elif nagumo_imagem_url:
        imagem_principal = nagumo_imagem_url

    shibata_total_str = f"{shibata_total_val:.2f}".replace('.', ',') if shibata_total_val != float('inf') and shibata_total_val > 0 else "N/D"
    nagumo_total_str = f"{nagumo_total_val:.2f}".replace('.', ',') if nagumo_total_val != float('inf') and nagumo_total_val > 0 else "N/D"
    
    # Retorna o dicionário de resultado para o item
    return {
        "nome_original_completo": nome_completo,
        "nome_exibicao": nome_exibicao,
        "imagem_principal": imagem_principal,
        "nagumo": nagumo_url, 
        "shibata": shibata_url, 
        "shibata_preco_val": preco_shibata_val,
        "nagumo_preco_val": preco_nagumo_val,
        "shibata_preco_str": preco_shibata_str, 
        "nagumo_preco_str": preco_nagumo_str,
        "preco_referencia_nome": preco_referencia_nome,
        "shibata_total_val": shibata_total_val,
        "nagumo_total_val": nagumo_total_val,
        "shibata_total_str": shibata_total_str,
        "nagumo_total_str": nagumo_total_str,
    }


# ----------------------------------------------------------------------
# LÓGICA PRINCIPAL DE COMPARAÇÃO (AJUSTADA PARA PARALELISMO)
# ----------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def realizar_comparacao_automatica():
    """
    Executa a busca em paralelo para a lista de itens lida do JSON e 
    retorna os resultados formatados.
    """
    lista_itens = ler_itens_json()
    if not lista_itens:
        return []

    resultados_finais = []
    MAX_WORKERS = 10 # Define o número máximo de threads (ajustável)
    
    # Inicia a execução em paralelo
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Mapeia a função processar_item para todos os itens da lista
        futures = [executor.submit(processar_item, item) for item in lista_itens]
        
        # Coleta os resultados assim que estiverem prontos
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    resultados_finais.append(result)
            except Exception as e:
                # Loga erros de processamento para itens individuais, mas continua
                st.error(f"Erro ao processar um item: {e}") 

    # Classifica os resultados finais pelo menor preço unitário
    resultados_finais.sort(key=lambda x: min(x.get('shibata_preco_val', float('inf')), x.get('nagumo_preco_val', float('inf'))))
    
    return resultados_finais

# ----------------------------------------------------------------------
# CONFIGURAÇÃO E EXIBIÇÃO DO STREAMLIT (SEM ALTERAÇÕES)
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
            display: grid; 
            grid-template-columns: 80px 1fr; 
            grid-template-rows: auto auto auto; 
            grid-template-areas:
                "image title"
                "image shibata"
                "image nagumo";
            gap: 1px 10px; 
            min-height: 90px; 
            overflow: hidden; 
        }
        .product-image {
            grid-area: image;
            width: 80px;
            height: 80px;
            object-fit: contain;
            border-radius: 4px;
            align-self: center; 
        }
        .price-badge {
            grid-area: title;
            align-self: end; 
            padding-bottom: 2px;
            line-height: 1.2; 
        }
        .market-link {
            text-decoration: none;
            display: block;
            padding: 2px 0;
            align-self: start; 
            font-size: 0.9em; 
            white-space: nowrap; 
            overflow: hidden; 
            text-overflow: ellipsis; 
            color: red; 
        }
        .market-link:visited {
            /* Mantém a cor do link após o clique */
            color: inherit; 
        }
        .shibata-link { 
            grid-area: shibata;
        }
        .nagumo-link { 
            grid-area: nagumo;
        }
        .logo-pequeno {
            vertical-align: middle; 
            margin-right: 5px;
            height: 60px; 
            width: 60px; 
            object-fit: contain;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown(f"<h6>🛒 Comparação Automática de Preços (Lendo {JSON_FILE})</h6>", unsafe_allow_html=True)

# Executa a comparação (agora em paralelo)
with st.spinner("🔍 Buscando e comparando preços em paralelo..."):
    # Adicionado o decorator @st.cache_data para evitar re-execução desnecessária
    resultados_comparacao = realizar_comparacao_automatica() 

if resultados_comparacao:
    st.markdown("<h5>Busca Automática de Preços</h5>", unsafe_allow_html=True)

    # Exibe os resultados na lista formatada
    for item in resultados_comparacao:
        # Valores para comparação
        shibata_val = item['shibata_preco_val']
        nagumo_val = item['nagumo_preco_val']
        preco_ref = item['preco_referencia_nome']
        
        # Disponibilidade
        shibata_disponivel = shibata_val != float('inf') and shibata_val > 0
        nagumo_disponivel = nagumo_val != float('inf') and nagumo_val > 0
        
        # Determina o melhor preço do mercado
        if shibata_disponivel and nagumo_disponivel:
            is_shibata_melhor = shibata_val <= nagumo_val
        elif shibata_disponivel:
            is_shibata_melhor = True
        elif nagumo_disponivel:
            is_shibata_melhor = False
        else:
            is_shibata_melhor = False

        
        # --- Lógica de Estilo --- (Cor e Negrito)
        
        # 1. Cor (Prioridade: Verde se for menor que o preço de referência, senão Vermelho)
        shibata_color = "red"
        nagumo_color = "red"
        
        if preco_ref and shibata_disponivel and shibata_val < preco_ref:
            shibata_color = "green"
        if preco_ref and nagumo_disponivel and nagumo_val < preco_ref:
            nagumo_color = "green"
            
        # 2. Negrito (Para o melhor preço entre os dois mercados)
        shibata_weight = "bold" if is_shibata_melhor and shibata_disponivel else "normal"
        nagumo_weight = "bold" if not is_shibata_melhor and nagumo_disponivel else "normal"
        
        # Style Final (Combinando cor e peso da fonte)
        shibata_link_style = f"font-weight: {shibata_weight}; color: {shibata_color};"
        nagumo_link_style = f"font-weight: {nagumo_weight}; color: {nagumo_color};"
        
        # Strings de preço para os links (Unitário + Total)
        shibata_unit_str = item['shibata_preco_str']
        if shibata_disponivel and shibata_unit_str not in ["Preço indisponível", "N/D"]:
            shibata_total_display = item['shibata_total_str']
            shibata_preco_str_final = f"{shibata_unit_str} (R${shibata_total_display})"
        else:
            shibata_preco_str_final = "N/D"

        nagumo_unit_str = item['nagumo_preco_str']
        if nagumo_disponivel and nagumo_unit_str not in ["Preço indisponível", "N/D"]:
            nagumo_total_display = item['nagumo_total_str']
            nagumo_preco_str_final = f"{nagumo_unit_str} (R${nagumo_total_display})"
        else:
            nagumo_preco_str_final = "N/D"
            
        nome_original = item['nome_original_completo']
        
        # URL da Imagem
        img_src = item.get('imagem_principal', DEFAULT_IMAGE_URL)
        if not img_src:
             img_src = DEFAULT_IMAGE_URL

        # Bloco HTML
        st.markdown(f"""
<div class='comparison-item'>
    <img src="{img_src}" class='product-image' alt="{nome_original}" />
    <div class='price-badge'>
    <span style="font-weight: bold; font-size: 1.15em; line-height: 1.2;">{nome_original}</span>
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
  height: 24px;object-fit: cover;border: 1.5px solid white;" alt="Logo Nagumo"/> {nagumo_preco_str_final}
    </a>
</div>
""", unsafe_allow_html=True)

    st.markdown("<h5>Saída JSON (Estrutura Completa)</h5>", unsafe_allow_html=True)
    st.json(resultados_comparacao)

else:
    st.warning("Nenhum resultado para exibir. Verifique o arquivo JSON e as buscas.")
