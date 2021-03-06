# coding: utf-8

import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
from pathlib import Path
import time
from datetime import datetime
import sys


logger = logging.getLogger(__name__)
logging.basicConfig()
logger.setLevel(logging.INFO)

URL_BASE = 'http://www.marinetraffic.com'
ARQUIVO_PORTOS_BRASIL = './output/portos.csv'
ARQUIVO_PORTOS_INTERESSE = './input/portos_interesse.csv'
ARQUIVO_NAVIOS_EM_PORTOS = './output/navios_em_portos.csv'


def obtem_pagina(url, proxy = None):
    user_agent = {'User-agent': 'Mozilla/5.0'}
    return requests.get(url, headers = user_agent, proxies = proxy)

def cria_pasta(caminho_arquivo):
    pasta = caminho_arquivo.parent
    if not pasta.exists():
        pasta.mkdir(parents=True)

def data_coleta():
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M')

def converte_data(num):
    return time.strftime('%Y-%m-%d %H:%M', time.gmtime(num))

def salva_dataframe_csv(dataframe, caminho_arquivo):
    caminho_arquivo_acum = caminho_arquivo.replace('.csv', '_acumulado.csv')

    dataframe.to_csv(caminho_arquivo_acum, sep=';', index=False, mode='a', decimal=',')
    logger.info('Arquivo {} criado.'.format(caminho_arquivo_acum))

    dataframe.to_csv(caminho_arquivo, sep=';', index=False, mode='w', decimal=',')
    logger.info('Arquivo {} criado.'.format(caminho_arquivo))


# # Navios de interesse

'''
    Crawl dos navios de interesse.

    arquivo_csv - arquivo de saída.
    proxy - proxy se necessário.
'''
def crawl_navios_interesse(arquivo_csv = './output/navios_interesse.csv',
    navios_em_portos_csv=ARQUIVO_NAVIOS_EM_PORTOS,
    chegadas_esperadas_csv='./output/chegadas_esperadas.csv', proxy=None,
    limite = None):

    df_navios_em_portos =   pd.read_csv(ARQUIVO_NAVIOS_EM_PORTOS, sep=';')
    df_chegadas_esperadas = pd.read_csv('./output/chegadas_esperadas.csv', sep=';')

    urls = df_navios_em_portos.LinkNavio.append(df_chegadas_esperadas.LinkNavio).values


    navios = []
    navios_erro = []
    i_limite = 1
    for url in urls:
        # Controle de limite de navios a buscar.
        if limite and i_limite > limite:
                break
        i_limite += 1



        logger.info('Obtendo dados de navio em {}.'.format(url))

        r = obtem_pagina(url, proxy)

        if r.status_code == 200: # Código HTTP de OK.
            soup = BeautifulSoup(r.text, 'lxml')

            detalhes = []

            # Nome do navio
            nome = soup.find('h1', class_='font-200 no-margin').text
            detalhes.append(nome)

            # Tipo. Informação logo abaixo do nome no site.
            tipo = None
            div = soup.find('div', class_='group-ib vertical-offset-10')
            if div:
                tipo = div.text.strip()

            # Latitude e longitude.
            a_posicao = soup.find('a', class_='details_data_link')
            link_posicao =None
            latitude = None
            longitude = None
            if a_posicao:
                if a_posicao['href']:
                    link_posicao = URL_BASE+a_posicao['href']
                if a_posicao.text:
                    coord = a_posicao.text
                    coord = [i.strip() for i in coord.split('/')]
                    coord = [i.replace('°','').replace('.',',') for i in coord]
                    latitude, longitude = coord

            # Data (UTC) último sinal recebido.
            span = soup.find('span', text=re.compile('Position Received'))
            data_ultimo_sinal = None
            if span and span.parent and span.parent.strong and span.parent.strong.text:
                texto = span.parent.strong.text.strip()
                match = re.search(r'(\d\d\d\d-\d\d-\d\d\s\d\d:\d\d)', texto)
                if match:
                    data_ultimo_sinal = match.groups()[0]

            # Área geográfica.
            span = soup.find('span', text=re.compile('Area:'))
            area_geografica = None
            if span and span.parent and span.parent.strong and span.parent.strong.text:
                area_geografica = span.parent.strong.text.strip()



            # Restante das informações.
            div = soup.find('div', class_='row equal-height')
            div_infos = div.find_all('div', class_='col-xs-6')
            for div_ in div_infos:
                detalhes.extend([i.text for i in div_.find_all('b')])

            detalhes.extend([tipo, latitude, longitude,
                data_ultimo_sinal, area_geografica, link_posicao, url, data_coleta()])

            navios.append(detalhes)
        else:
            s = 'Erro código HTTP {} ao obter dados do navio {}.'.format(r.status_code, url)
            logger.error(s)
            navios_erro.append([s,url])

    logger.info('Total de navios sem erro / com erros: {} / {}'.format(len(navios),len(navios_erro)))

    df = pd.DataFrame(navios, columns= ['Nome', 'IMO', 'MMSI', 'Indicativo',
        'Bandeira', 'TipoAIS', 'Tonelagem', 'Porte', 'Comp_Larg', 'Ano',
        'Estado','Tipo', 'Latitude', 'Longitude', 'DataUltimoSinal',
        'AreaGeografica', 'LinkPosicaoNavio', 'LinkNavio','DataColeta'])

    df = df.replace('-',pd.np.nan)
    df.Porte = df.Porte.str.replace(' t','')
    df['Comprimento'] = df.Comp_Larg.str.extract(r'(\d{0,4}(?:[.,]\d{1,3})?)m', expand=False)
    df['Comprimento'] = df['Comprimento'].str.replace('.',',')
    df['Largura'] = df.Comp_Larg.str.extract(r'(\d{0,4}(?:[.,]\d{1,3})?)m$', expand=False)
    df['Largura'] = df['Largura'].str.replace('.',',')


    # Salva arquivo no diretório indicado.
    caminho_arquivo = Path(arquivo_csv)
    cria_pasta(caminho_arquivo)
    salva_dataframe_csv(df,caminho_arquivo.as_posix())

    df_erro = pd.DataFrame(navios_erro, columns=['Erro','URL'])
    salva_dataframe_csv(df_erro, './navios_erro.csv')



# # Portos brasileiros

# In[236]:

def crawl_portos_brasil(arquivo_csv='./output/portos.csv', proxy=None,
    limite = None):

    # Essa URL filtra os apenas os portos. Issue #22.
    url = 'https://www.marinetraffic.com/en/ais/index/ports/all/flag:BR/port_type:p/per_page:50'

    # Essa URL pega todos os portos, incluindo ancoradouros, marinas, etc. Issue #22.
    url = 'https://www.marinetraffic.com/en/ais/index/ports/all/flag:BR/per_page:50'

    tabela_portos = []

    i_limite = 1
    while True:

        logger.info('Capturar portos em: {}'.format(url))
        html_portos = obtem_pagina(url, proxy=proxy).text
        soup = BeautifulSoup(html_portos, 'lxml')

        # Tag <table> dos portos.
        table_portos = soup.find('table', class_='table table-hover text-left')

        # Percorrer todas as linhas da tabela.
        # A primeira linha é o cabeçalho, então iremos pulá-la.
        linhas = table_portos.find_all('tr')

        for linha in linhas[1:]:
            # Controle de limite de portos a buscar.
            if limite and i_limite > limite:
                    break
            i_limite += 1

            # Cada linha contém uma lista de células com os valores de interesse.
            celulas = linha.find_all('td')

            # Pular propagada que contém apenas uma célula <td>.
            if len(celulas) == 1: continue

            # Coluna da bandeira do país.
            col = celulas[0]
            pais = col.img.attrs['title']
            link_bandeira_pais = URL_BASE+col.img['src']

            # Coluna de link para o porto.
            col = celulas[1]
            link_porto = URL_BASE+col.a['href']
            nome_porto = col.text.strip().upper()

            # Coluna Codigo.
            col = celulas[2]
            codigo = col.text.strip()

            # Coluna Foto.
            col = celulas[3]
            link_fotos = URL_BASE+col.a['href']

            # Coluna Tipo
            col = celulas[4]
            tipo = col.text.strip()

            # Coluna link para mapa do porto.
            col = celulas[5]
            link_mapa_porto = URL_BASE+col.a['href']

            # Coluna Navios no porto.
            col = celulas[6]
            link_navios_porto = URL_BASE+col.a['href']

            # Coluna link partidas.
            col = celulas[7]
            link_partidas = URL_BASE+col.a['href']

            # Coluna link chegadas.
            col = celulas[8]
            link_chegadas = URL_BASE+col.a['href']

            # Coluna link chegadas esperadas.
            col = celulas[9]
            link_chegadas_esperadas = URL_BASE+col.a['href']

            # Coluna status da cobertura AIS.
            col = celulas[10]
            cobertura_ais = col.div['title']

            # Armazena os dados de cada porto na tabela de portos.
            dados = [pais, nome_porto,codigo, tipo, cobertura_ais, link_bandeira_pais, link_navios_porto,
                     link_chegadas_esperadas, link_chegadas, link_porto, link_fotos,
                     link_mapa_porto, data_coleta()]
            tabela_portos.append(dados)

        # Não há próxima página?
        next_disabled = soup.find('span', class_='next disabled')
        if next_disabled:
            logger.info('Fim da captura de portos.')

            break
        else:
            next_page = soup.find('span', class_='next')
            url = URL_BASE + next_page.a['href']

    cabecalho = ['Pais','Nome','Codigo','Tipo','CoberturaAIS','LinkBandeira','LinkNaviosPorto',
                 'LinkChegadasEsperadas','LinkChegadas','LinkPorto','LinkFotos',
                'LinkMapaPorto', 'DataColeta']
    df = pd.DataFrame(tabela_portos, columns=cabecalho)

    # Issue #3
    df['Id'] = df.LinkPorto.str.extract(r'ports/(\d+)/Brazil', expand=False)

    # Issue #5
    df_latlong = df.LinkMapaPorto.str.extract(
        'centerx:(?P<Longitude>-?\d{,3}\.?\d*)/' +
        'centery:(?P<Latitude>-?\d{,3}\.?\d*)',
        expand=True)
    df_latlong['Latitude'] = df_latlong.Latitude.str.replace('.', ',')
    df_latlong['Longitude'] = df_latlong.Longitude.str.replace('.', ',')
    df = df.join(df_latlong)


    # Issue #23.
    df = df.drop_duplicates(['Nome','Codigo']).sort_values('Nome')

    caminho_arquivo = Path(arquivo_csv)
    cria_pasta(caminho_arquivo)
    salva_dataframe_csv(df, caminho_arquivo.as_posix())

def crawl_navios_em_portos(arquivo_csv=ARQUIVO_NAVIOS_EM_PORTOS,
    arquivo_portos_interesse = ARQUIVO_PORTOS_INTERESSE,
    arquivo_portos_brasil = ARQUIVO_PORTOS_BRASIL, proxy=None):

    tabela_navios_porto = []

    path_arquivo_portos_interesse = Path(arquivo_portos_interesse)
    if not path_arquivo_portos_interesse.exists():
        logger.error('ARQUIVO DE PORTOS DE INTERESSE NÃO ENCONTRADO! ' \
            'ESSE ARQUIVO É CRIADO PELO USUÁRIO E DEVE CONTER A COLUNA ' \
            '"Nome": {}'.format(path_arquivo_portos_interesse.absolute().as_posix()))
        return
    path_arquivo_portos_brasil = Path(arquivo_portos_brasil)
    if not path_arquivo_portos_brasil.exists():
        logger.error('ARQUIVO DE PORTOS DO BRASIL NÃO ENCONTRADO. ' \
            'ESSE ARQUIVO É GERADO PELO CRAWLER DE PORTOS: {}'. \
            format(path_arquivo_portos_brasil.absolute().as_posix()))
        return

    df_portos_interesse = pd.read_csv(arquivo_portos_interesse, sep=';',
        encoding='latin-1', comment='#')
    df_portos = pd.read_csv(arquivo_portos_brasil, sep=';', encoding='latin-1')
    nome_portos_interesse = df_portos_interesse.Nome.values


    for nome_porto in nome_portos_interesse:
        porto = df_portos[df_portos.Nome==nome_porto.upper()]

        # Verifica se os porto de interesse está no arquivo de portos.
        # Caso não esteja, avisa o erro e pula para o próximo.
        if len(porto) == 0:
            logger.warn('PORTO DE INTERESSE "{}" CONFIGURADO NO ARQUVO "{}" '\
            'NÃO CONSTA NO ARQUIVO "{}"!'.format(nome_porto,
            path_arquivo_portos_interesse.absolute().as_posix(),
            path_arquivo_portos_brasil.absolute().as_posix()))
            continue

        url_navios_porto =  porto.LinkNaviosPorto.values[0]

        # Adiciona filtro para navios tanques.
        url_navios_porto += '/ship_type:8'

        # Issue #20
        url_navios_porto += '/per_page:50'

        while True:
            logger.info('Capturar navios no porto {}'.format(url_navios_porto))
            html_navios_porto = obtem_pagina(url_navios_porto, proxy=proxy).text
            soup = BeautifulSoup(html_navios_porto, 'lxml')
            # Tag <table> dos navios.
            table = soup.find('table', class_='table table-hover text-left')

            # Percorrer todas as linhas da tabela.
            # A primeira linha é o cabeçalho, então iremos pulá-la.
            linhas = table.find_all('tr')
            for linha in linhas[1:]:

                # Cada linha contém uma lista de células com os valores de interesse.
                celulas = linha.find_all('td')

                # Pular propagada que contém apenas uma célula <td>.
                if len(celulas) == 1: continue

                # Coluna Tipo.
                col = celulas[4]
                tipo = col.text.strip()

                # Se não for do tipo "tanker", pula para próximo navio.
                if tipo.lower().find('tanker') == -1: continue


                # Coluna da bandeira do país.
                col = celulas[0]
                pais = col.img.attrs['title']
                link_bandeira_pais = URL_BASE+col.img['src']


                # Coluna de link para o navio.
                col = celulas[1]
                link_navio = URL_BASE+col.a['href']
                nome_navio = col.text.strip()

                # Coluna Foto.
                col = celulas[2]
                link_fotos = URL_BASE+col.a['href']


                # Coluna Dimensões.
                col = celulas[5]
                dimensoes = col.text.strip()

                # Coluna Porte.
                col = celulas[6]
                porte = col.text.strip()

                # Coluna Data Ultimo Sinal.
                col = celulas[8]
                data_ultimo_sinal = converte_data(int(col.time.text.strip()))

                # Coluna Data Chegada.
                col = celulas[9]
                data_chegada = None
                if col.time:
                    data_chegada = converte_data(int(col.time.text.strip()))

                # Armazena os dados de cada navio na tabela de navios.
                dados = [nome_porto, nome_navio, tipo, pais, dimensoes, porte,
                    data_ultimo_sinal, data_chegada, link_navio,
                    link_bandeira_pais, link_fotos,data_coleta()]
                tabela_navios_porto.append(dados)

            # Não há próxima página?
            next_disabled = soup.find('span', class_='next disabled')
            if next_disabled:
                logger.info('Fim da captura de navios em portos para o porto {}.'.format(nome_porto))
                break
            elif soup.find('span', class_='next'):
                next_page = soup.find('span', class_='next')
                url_navios_porto = URL_BASE + next_page.a['href']
            else:
                logger.info('Fim da captura de navios em portos para o porto {}.'.format(nome_porto))
                break


    cabecalho = ['Porto', 'Nome','Tipo','Pais', 'Dimensoes', 'Porte',
        'DataUltimoSinal', 'DataChegada', 'LinkNavio', 'LinkBandeira',
        'LinkFotos','DataColeta']
    df = pd.DataFrame(tabela_navios_porto, columns=cabecalho)
    caminho_arquivo = Path(arquivo_csv)
    cria_pasta(caminho_arquivo)
    salva_dataframe_csv(df, caminho_arquivo.as_posix())

def crawl_chegadas_esperadas(arquivo_csv='./output/chegadas_esperadas.csv',
    arquivo_portos_interesse = ARQUIVO_PORTOS_INTERESSE,
    arquivo_portos_brasil = ARQUIVO_PORTOS_BRASIL, proxy=None):
    tabela_chegadas_esperadas = []

    path_arquivo_portos_interesse = Path(arquivo_portos_interesse)
    if not path_arquivo_portos_interesse.exists():
        logger.error('ARQUIVO DE PORTOS DE INTERESSE NÃO ENCONTRADO! ' \
            'ESSE ARQUIVO É CRIADO PELO USUÁRIO E DEVE CONTER A COLUNA ' \
            '"Nome": {}'.format(path_arquivo_portos_interesse.absolute().as_posix()))
        return
    path_arquivo_portos_brasil = Path(arquivo_portos_brasil)
    if not path_arquivo_portos_brasil.exists():
        logger.error('ARQUIVO DE PORTOS DO BRASIL NÃO ENCONTRADO. ' \
            'ESSE ARQUIVO É GERADO PELO CRAWLER DE PORTOS: {}'. \
            format(path_arquivo_portos_brasil.absolute().as_posix()))
        return


    df_portos_interesse = pd.read_csv(arquivo_portos_interesse, sep=';',
        encoding='latin-1', comment='#')
    df_portos = pd.read_csv(arquivo_portos_brasil, sep=';', encoding='latin-1')
    nome_portos_interesse = df_portos_interesse.Nome.values


    for nome_porto in nome_portos_interesse:
        porto = df_portos[df_portos.Nome==nome_porto.upper()]

        # Verifica se os porto de interesse está no arquivo de portos.
        # Caso não esteja, avisa o erro e pula para o próximo.
        if len(porto) == 0:
            logger.warn('PORTO DE INTERESSE "{}" CONFIGURADO NO ARQUVO "{}" '\
            'NÃO CONSTA NO ARQUIVO "{}"!'.format(nome_porto,
            path_arquivo_portos_interesse.absolute().as_posix(),
            path_arquivo_portos_brasil.absolute().as_posix()))
            continue


        url_chegadas_esperadas =   porto.LinkChegadasEsperadas.values[0]

        # Issue #20
        url_chegadas_esperadas += '/per_page:50'

        while True:
            logger.info('Capturar chegadas esperadas no porto {}'.format(url_chegadas_esperadas))
            html_navios_porto = obtem_pagina(url_chegadas_esperadas,proxy=proxy).text
            soup = BeautifulSoup(html_navios_porto, 'lxml')
            # Tag <table> dos navios.
            table = soup.find('table', class_='table table-hover text-left')

            # Percorrer todas as linhas da tabela.
            # A primeira linha é o cabeçalho, então iremos pulá-la.
            linhas = table.find_all('tr')

            primeira_linha_dados = True
            rowspan_porto_origem = False
            rowspan_eta_calculado = False

            for linha in linhas[1:]:

                # Cada linha contém uma lista de células com os valores de interesse.
                celulas = linha.find_all('td')

                # Pular linha de propagada que contém apenas uma célula <td>.
                if len(celulas) == 1: continue

                # Issue #9.
                # A primeira linha de dados tem a segunda célula com rowspan.
                # As demais linhas não tem essa célula, então os ínidices das células
                # precisam ser ajustados.
                idx_porto_origem = 1
                idx_nome_navio = 2
                idx_eta_informado = 3
                idx_eta_calculado = 4
                idx_chegada_atual = 5
                idx_posicao_navio = 6
                if primeira_linha_dados:
                    col = celulas[idx_porto_origem]
                    if col.has_attr('rowspan'):
                        rowspan_porto_origem = True
                    col = celulas[4]
                    if col.has_attr('rowspan'):
                        rowspan_eta_calculado = True
                    primeira_linha_dados = False
                else:
                    if rowspan_porto_origem:
                        idx_porto_origem = None
                        idx_nome_navio -= 1
                        idx_eta_informado -= 1
                        idx_eta_calculado -= 1
                        idx_chegada_atual -= 1
                        idx_posicao_navio -= 1
                    if rowspan_eta_calculado:
                        idx_eta_calculado = None
                        idx_chegada_atual -= 1
                        idx_posicao_navio -= 1


                # Coluna nome do porto de origem.
                nome_porto_origem = None
                if idx_porto_origem:
                    col = celulas[idx_porto_origem]
                    nome_porto_origem = col.text.strip()

                # Coluna nome  do navio.
                col = celulas[idx_nome_navio]
                nome_navio = col.a.text.strip()
                link_navio = URL_BASE+col.a['href'].strip()
                link_icone_tipo_navio = None
                if col.img:
                    link_icone_tipo_navio = URL_BASE+col.img['src']

                    # Se não for do tipo tanker (vi8.png), pula para próximo navio.
                    if link_icone_tipo_navio.find('vessel_types/vi8.png') == -1:
                        continue
                # Se não contiver imagem do tipo, pula para próximo navio.
                else:
                    continue

                # Coluna ETA Informado.
                eta_informado = None
                col = celulas[idx_eta_informado]
                if col.span:
                    if col.span.has_attr('data-time'):
                        valor_data = col.span['data-time']
                        if valor_data:
                            eta_informado = converte_data(int(valor_data))

                # Coluna ETA Calculado.
                eta_calculado = None
                if idx_eta_calculado:
                    col = celulas[idx_eta_calculado]
                    if col.span:
                        if col.span.has_attr('data-time'):
                            valor_data = col.span['data-time']
                            if valor_data:
                                eta_calculado = converte_data(int(valor_data))

                # Coluna Chegada Atual.
                data_chegada = None
                col = celulas[idx_chegada_atual]
                if col.span:
                    if col.span.has_attr('data-time'):
                        valor_data = col.span['data-time']
                        if valor_data:
                            data_chegada = converte_data(int(valor_data))

                # Link posição do navio
                link_posicao_navio = None
                col = celulas[idx_posicao_navio]
                if col.a:
                    link_posicao_navio = URL_BASE+col.a['href']


                # Armazena os dados de cada navio na tabela de navios.
                dados = [nome_porto, nome_porto_origem,nome_navio,
                    eta_informado, eta_calculado, data_chegada, link_navio,
                    link_icone_tipo_navio, link_posicao_navio, data_coleta()]
                tabela_chegadas_esperadas.append(dados)

            # Não há próxima página?
            next_disabled = soup.find('span', class_='next disabled')
            if next_disabled:
                logger.info('Fim da captura de chegadas esperadas para o ' \
                    'porto {}.'.format(nome_porto))
                break
            elif soup.find('span', class_='next'):
                next_page = soup.find('span', class_='next')
                url_chegadas_esperadas = URL_BASE + next_page.a['href']
            else:
                logger.info('Fim da captura de chegadas esperadas para o ' \
                    'porto {}.'.format(nome_porto))
                break

    cabecalho = ['Porto', 'PortoOrigem','Navio','ETAInformado','ETACalculado', 'DataChegada',
        'LinkNavio','LinkIconeTipoNavio', 'LinkPosicaoNavio', 'DataColeta']
    df = pd.DataFrame(tabela_chegadas_esperadas, columns=cabecalho)

    # Pegar latitude e longitude a partir do link da posição.
    df_latlong = df.LinkPosicaoNavio.str.extract('centerx:(?P<Longitude>-?\d{,3}\.?\d*)/centery:(?P<Latitude>-?\d{,3}\.?\d*)', expand=True)

    # Issue #5
    df_latlong['Latitude'] = df_latlong.Latitude.str.replace('.', ',')
    df_latlong['Longitude'] = df_latlong.Longitude.str.replace('.', ',')
    df = df.join(df_latlong)

    caminho_arquivo = Path(arquivo_csv)
    cria_pasta(caminho_arquivo)
    salva_dataframe_csv(df, caminho_arquivo.as_posix())


def __configurar_log():
    logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]  %(message)s")
    rootLogger = logging.getLogger()

    fileHandler = logging.FileHandler("marinetraffic.log")
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)
    logger.setLevel(logging.INFO)


if __name__ =='__main__':
    __configurar_log()

    proxies = None

    # Se não tiver qualquer argumento, usa o proxy ptbrs.
    if len(sys.argv) == 1:

        proxies = {
                'http': 'http://127.0.0.1:53128',
                'https': 'http://127.0.0.1:53128',
            }

    crawl_portos_brasil(proxy = proxies)
    crawl_navios_em_portos(proxy = proxies)
    crawl_chegadas_esperadas(proxy = proxies)
    crawl_navios_interesse(proxy = proxies)
