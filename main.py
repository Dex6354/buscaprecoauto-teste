import streamlit as st
import requests
import unicodedata
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configurações para Shibata
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
LOGO_SHIBATA_URL = "https://rawcdn.githack.com/gymbr/precosmercados/main/logo-shibata.png" # Logo do Shibata
DEFAULT_IMAGE_URL = "https://rawcdn.githack.com/gymbr/precosmercados/main/sem-imagem.png" # Imagem padrão


# Funções utilitárias
def remover_acentos(texto):
    if not texto:
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower()

# --- Funções de Cálculo de Preço (Mantidas do seu arquivo) ---
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
    if q_rolos and m_rolos:
        preco_por_metro = preco_total / (q_rolos * m_rolos)
        return preco_por_metro, f"R$ {preco_por_metro:.3f}".replace('.', ',') + "/m"
    return None, None

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

# --- NOVA FUNÇÃO DE BUSCA POR PRODUTO_ID ---
def fetch_shibata_product_by_id(produto_id):
    """Busca um produto específico no Shibata pelo Produto_id."""
    if not produto_id:
        return None
    # Este é o endpoint para buscar um produto único pelo ID
    url = f"https://services.vipcommerce.com.br/api-admin/v1/org/{ORG_ID}/filial/1/centro_distribuicao/1/loja/produto/{produto_id}"
    try:
        response = requests.get(url, headers=HEADERS_SHIBATA, timeout=10)
        if response.status_code == 200:
            # A API retorna {'data': {'produto': {...}}}
            return response.json().get('data', {}).get('produto')
        else:
            st.error(f"Falha ao buscar Produto_id {produto_id}. Status: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Erro de conexão ao buscar Shibata: {e}")
        return None
    except Exception as e:
        st.error(f"Erro inesperado ao buscar Shibata: {e}")
        return None

# Configuração da página (Mantida do seu arquivo)
st.set_page_config(page_title="Preços Mercados", page_icon="🛒", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 0rem; }
        footer {visibility: hidden;}
        #MainMenu {visibility: hidden;}
        div, span, strong, small { font-size: 0.75rem !important; }
        img { max-width: 100px; height: auto; }
        .product-container {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .product-image {
            min-width: 80px;
            max-width: 80px;
            flex-shrink: 0;
        }
        .product-info {
            flex: 1 1 auto;
            min-width: 0; /* 👈 ESSENCIAL para permitir quebra */
            word-break: break-word;
            overflow-wrap: break-word;
        }
        hr.product-separator {
            border: none;
            border-top: 1px solid #eee;
            margin: 10px 0;
        }
        .info-cinza {
            color: gray;
            font-size: 0.8rem;
        }
       [data-testid="stColumn"] {
            overflow-y: auto;
            max-height: 90vh;
            padding: 10px;
            border: 1px solid #f0f2f6;
            border-radius: 8px;
            max-width: 480px;
            margin-left: auto;
            margin-right: auto;
            background: transparent;
            scrollbar-width: thin;
            scrollbar-color: gray transparent;  /* Firefox: thumb branco, track transparente */
        }
        [data-testid="stColumn"]::-webkit-scrollbar {
            width: 6px;
            background: transparent;
        }
        [data-testid="stColumn"]::-webkit-scrollbar-track {
            background: transparent; /* fundo transparente */
        }
        [data-testid="stColumn"]::-webkit-scrollbar-thumb {
            background-color: gray; /* barrinha branca translúcida */
            border-radius: 3px;
            border: 1px solid transparent;
        }
        [data-testid="stColumn"]::-webkit-scrollbar-thumb:hover {
            background-color: white; /* barrinha mais visível ao passar o mouse */
        }
        .block-container {
            padding-right: 47px !important;  /* Tamanho do espaco para rolagem */
        }
        input[type="text"] {
            font-size: 0.8rem !important;
        }
        .block-container { 
            padding-bottom: 15px !important; 
            margin-bottom: 15px !important; 
        } 
        [data-testid="stColumn"] { 
            margin-bottom: 20px; 
        } 
        header[data-testid="stHeader"] { 
            display: none; 
        } 
    </style>
""", unsafe_allow_html=True)

# --- ENTRADA MODIFICADA ---
st.markdown("<h6>🛒 Preços Mercados (Busca por ID)</h6>", unsafe_allow_html=True)
produto_id_input = st.text_input("🔎 Digite o Produto_id (Ex: 16286):", "16286").strip()


# --- LÓGICA PRINCIPAL MODIFICADA ---
if produto_id_input:
    # Cria a coluna/container
    col_shibata = st.container()

    with st.spinner(f"🔍 Buscando Produto_id {produto_id_input}..."):
        # 1. Busca o produto único
        produto_encontrado = fetch_shibata_product_by_id(produto_id_input)
        
        produtos_para_exibir = [] # Usamos uma lista para manter a lógica de loop de exibição

        if produto_encontrado:
            # 2. Processa o produto (lógica de cálculo de preço do seu arquivo)
            p = produto_encontrado
            
            if not p.get("disponivel", True):
                st.warning("Produto encontrado, mas está marcado como indisponível.")
                # Mesmo indisponível, vamos processar para exibir os dados

            preco = float(p.get('preco') or 0)
            em_oferta = p.get('em_oferta', False)
            oferta_info = p.get('oferta') or {}
            preco_oferta = oferta_info.get('preco_oferta')
            preco_total = float(preco_oferta) if em_oferta and preco_oferta else preco
            descricao = p.get('descricao', '')

            # Cálculo de preço por unidade/volume/peso
            preco_unidade_val, preco_unidade_str = calcular_preco_unidade(descricao, preco_total)
            preco_por_metro_val, preco_por_metro_str = calcular_precos_papel(descricao, preco_total)

            quantidade_dif = p.get('quantidade_unidade_diferente')
            unidade_sigla = p.get('unidade_sigla')
            preco_formatado_padrao = formatar_preco_unidade_personalizado(preco_total, quantidade_dif, unidade_sigla)

            if preco_unidade_val is None or preco_unidade_val == float('inf'):
                preco_unidade_val = preco_total
                preco_unidade_str = preco_formatado_padrao
                if not preco_unidade_str:
                    preco_unidade_str = f"R$ {preco_total:.2f}/un"

            # Atualiza os campos no objeto
            p['preco_unidade_val'] = preco_unidade_val
            p['preco_unidade_str'] = preco_unidade_str
            p['preco_por_metro_val'] = preco_por_metro_val if preco_por_metro_val else float('inf')
            
            # Adiciona à lista para exibição
            produtos_para_exibir.append(p)
        
        # 3. Lógica de exibição (Movida para dentro do 'col_shibata')
        with col_shibata:
            st.markdown(f"""
                <h5 style="display: flex; align-items: center; justify-content: center;">
                    <img src="{LOGO_SHIBATA_URL}" width="80" alt="Shibata" style="margin-right:8px; background-color: white; border-radius: 4px; padding: 3px;"/>
                </h5>
            """, unsafe_allow_html=True)
            
            total_encontrado = len(produtos_para_exibir)
            st.markdown(f"<small>🔎 {total_encontrado} produto(s) encontrado(s).</small>", unsafe_allow_html=True)

            if not produtos_para_exibir:
                st.warning(f"Nenhum produto encontrado com o ID: {produto_id_input}")

            # O loop agora roda 0 ou 1 vez, mantendo sua lógica de exibição
            for p in produtos_para_exibir:
                preco = float(p.get('preco') or 0)
                descricao = p.get('descricao', '')
                imagem = p.get('imagem', '')
                id_item = p.get('id', 'N/A') # Este é o ID interno (Ex: 235813)

                em_oferta = p.get('em_oferta', False)
                oferta_info = p.get('oferta') or {}
                preco_oferta = oferta_info.get('preco_oferta')
                preco_antigo = oferta_info.get('preco_antigo')

                imagem_url = f"https://produto-assets-vipcommerce-com-br.br-se1.magaluobjects.com/500x500/{imagem}" if imagem else DEFAULT_IMAGE_URL
                preco_total = float(preco_oferta) if em_oferta and preco_oferta else preco

                preco_info_extra = ""
                
                # ---- LÓGICA DE PREÇO UNITÁRIO (AJUSTADA) ----
                # Usamos o nome e descrição do *próprio produto* para decidir o que exibir
                nome_produto_proc = remover_acentos(f"{p.get('nome', '')} {descricao}")

                if 'papel toalha' in nome_produto_proc:
                    total_folhas, preco_por_folha = calcular_preco_papel_toalha(descricao, preco_total)
                    if preco_por_folha:
                        preco_info_extra += f"<div style='color:gray; font-size:0.75em;'>R$ {preco_por_folha:.3f}/folha ({total_folhas} folhas)</div>"
                elif 'papel higienico' in nome_produto_proc:
                    preco_por_metro_val, preco_por_metro_str = calcular_precos_papel(descricao, preco_total)
                    if preco_por_metro_str:
                        preco_info_extra += f"<div style='color:gray; font-size:0.75em;'>{preco_por_metro_str}</div>"

                if not preco_info_extra:
                    _, preco_por_unidade_str = calcular_preco_unidade(descricao, preco_total)
                    if preco_por_unidade_str:
                        preco_info_extra += f"<div style='color:gray; font-size:0.75em;'>{preco_por_unidade_str}</div>"

                if 'ovo' in nome_produto_proc:
                    match_ovo = re.search(r'(\d+)\s*(unidades|un|ovos|c/|com)', descricao.lower())
                    if match_ovo:
                        qtd_ovos = int(match_ovo.group(1))
                        if qtd_ovos > 0:
                            preco_por_ovo = preco_total / qtd_ovos
                            preco_info_extra += f"<div style='color:gray; font-size:0.75em;'>R$ {preco_por_ovo:.2f}/unidade</div>"
                    if re.search(r'1\s*d[uú]zia', descricao.lower()):
                        preco_por_unidade_duzia = preco_total / 12
                        preco_info_extra += f"<div style='color:gray; font-size:0.75em;'>R$ {preco_por_unidade_duzia:.2f}/unidade (dúzia)</div>"
                # ---- FIM DA LÓGICA DE PREÇO UNITÁRIO ----

                # Preço (com ou sem oferta)
                preco_antigo_html = ""
                if em_oferta and preco_oferta and preco_antigo:
                    preco_oferta_val = float(preco_oferta)
                    preco_antigo_val = float(preco_antigo)
                    desconto = round(100 * (preco_antigo_val - preco_oferta_val) / preco_antigo_val)
                    preco_html = f"""
                        <span style='font-weight: bold; font-size: 1rem;'>R$ {preco_oferta_val:.2f}</span>
                        <span style='color: red; font-weight: bold; font-size: 0.7rem;'> ({desconto}% OFF)</span>
                    """
                    preco_antigo_html = f"<span style='text-decoration: line-through; color: gray; font-size: 0.75rem;'>R$ {preco_antigo_val:.2f}</span>"
                else:
                    preco_html = f"<span style='font-weight: bold; font-size: 1rem;'>R$ {preco:.2f}</span>"


                # --- BLOCO "TODOS OS CAMPOS" (Mantido 100% do seu arquivo) ---
                campos_excluidos = [
                    'id', 'descricao', 'nome', 'preco', 'preco_unidade_val', 'preco_unidade_str',
                    'preco_por_metro_val', 'preco_por_folha_val', 'em_oferta', 'oferta', 'imagem',
                    'quantidade_unidade_diferente', 'unidade_sigla', 'disponivel'
                ]

                campos_adicionais_html = ""
                for key, value in p.items():
                    if key not in campos_excluidos and value is not None:
                        if isinstance(value, dict):
                            detail = ', '.join(f'{k}: {v}' for k, v in value.items() if v is not None)
                            if detail:
                                campos_adicionais_html += f"<div>**{key.capitalize()}**: {detail}</div>"
                        elif isinstance(value, list):
                            campos_adicionais_html += f"<div>**{key.capitalize()}**: [Lista com {len(value)} item(ns)]</div>"
                        else:
                            campos_adicionais_html += f"<div>**{key.capitalize()}**: {value}</div>"
                
                # O ID que estávamos usando para buscar (Ex: 16286)
                # A API retorna esse ID como 'produto_id'
                produto_id_api = p.get('produto_id', 'N/A') 

                # Se não houver campos adicionais, exibe uma mensagem
                if not campos_adicionais_html:
                     campos_adicionais_html = "<div>Nenhum campo adicional encontrado na resposta da API além dos já exibidos.</div>"

                # Estrutura de exibição completa
                st.markdown(f"""
                    <div class="product-container">
                        <div class="product-image">
                            <img src="{imagem_url}" alt="{p.get('nome', 'Produto')}" style="max-width: 100%; height: auto; border-radius: 4px;">
                        </div>
                        <div class="product-info">
                            <strong>{p.get('nome', 'N/A')}</strong><br>
                            <span class='info-cinza'>{descricao}</span><br>
                            {preco_html}
                            {preco_antigo_html}
                            {preco_info_extra}

                            <div style="margin-top: 5px; border-top: 1px dashed #eee; padding-top: 5px; font-size: 0.7em;">
                                <div style="font-weight: bold; color: #333;">TODOS OS CAMPOS DO OBJETO (Possíveis):</div>
                                <div>**ID (Interno)**: {id_item}</div>
                                <div>**Produto_id (da URL)**: {produto_id_api}</div>
                                {campos_adicionais_html}
                            </div>
                        </div>
                    </div>
                    <hr class="product-separator">
                """, unsafe_allow_html=True)
