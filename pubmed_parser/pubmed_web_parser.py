import re
import requests
import time
from lxml import etree
from lxml import html
from unidecode import unidecode

__all__ = [
    'parse_xml_web',
    'parse_citation_web',
    'parse_outgoing_citation_web'
]


def load_xml(pmid, sleep=None):
    """
    Load XML file from given pmid from eutils site
    return a dictionary for given pmid and xml string from the site
    sleep: how much time we want to wait until requesting new xml
    """
    link = "http://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&id=%s" % str(pmid)
    page = requests.get(link)
    tree = html.fromstring(page.content)
    if sleep is not None:
        time.sleep(sleep)
    dict_xml = {'pmid': str(pmid), 'xml': etree.tostring(tree)} # turn xml to string (easier to save later on)
    return dict_xml


def get_author_string(tree):
    authors = tree.xpath('//authorlist//author')
    authors_text = []
    for a in authors:
        firstname = a.find('forename').text
        lastname = a.find('lastname').text
        fullname = firstname + ' ' + lastname
        authors_text.append(fullname)
    return '; '.join(authors_text)


def get_year_string(tree):
    year = ''.join(tree.xpath('//pubmeddata//history//pubmedpubdate[@pubstatus="medline"]/year/text()'))
    return year


def get_abstract_string(tree):
    abstract = unidecode(stringify_children(tree.xpath('//abstract')[0]))
    return abstract


def get_affiliation_string(tree):
    """
    Get all affiliation string
    """
    affiliation = '; '.join([a for a in tree.xpath('//affiliationinfo//affiliation/text()')])
    return affiliation


def parse_xml_tree(tree):
    """
    Giving tree, return simple parsed information from the tree
    """
    try:
        title = ' '.join(tree.xpath('//articletitle/text()'))
    except:
        title = ''

    try:
        abstract = get_abstract_string(tree)
    except:
        abstract = ''

    try:
        journal = ' '.join(tree.xpath('//article//title/text()')).strip()
    except:
        journal = ''

    try:
        year = get_year_string(tree)
    except:
        year = ''

    try:
        affiliation = get_affiliation_string(tree)
    except:
        affiliation = ''

    try:
        authors = get_author_string(tree)
    except:
        authors = ''

    dict_out = {'title': title,
                'abstract': abstract,
                'journal': journal,
                'affiliation': affiliation,
                'authors': authors,
                'year': year}
    return dict_out


def parse_xml_web(pmid, sleep=None, save_xml=False):
    """
    Give pmid, load and parse xml from Pubmed eutils
    if save_xml is True, save xml output in dictionary
    """
    dict_xml = load_xml(pmid, sleep=sleep)
    tree = etree.fromstring(dict_xml['xml'])
    dict_out = parse_xml_tree(tree)
    dict_out['pmid'] = dict_xml['pmid']
    if save_xml:
        dict_out['xml'] = dict_xml['xml']
    return dict_out


def extract_citations(tree):
    """
    Extract number of citations from given tree
    """
    citations_text = tree.xpath('//form/h2[@class="head"]/text()')[0]
    n_citations = re.sub("Is Cited by the Following ", "", citations_text).split(' ')[0]
    try:
        n_citations = int(n_citations)
    except:
        n_citations = 0
    return n_citations


def extract_pmc(citation):
    pmc_text = [c for c in citation.split('/') if c is not ''][-1]
    pmc = re.sub('PMC', '', pmc_text)
    return pmc


def convert_document_id(doc_id, id_type='PMC'):
    """
    Convert document id to dictionary of other id
    see: http://www.ncbi.nlm.nih.gov/pmc/tools/id-converter-api/ for more info
    """
    doc_id = str(doc_id)
    if id_type == 'PMC':
        doc_id = 'PMC%s' % doc_id
        pmc = doc_id
        convert_link = 'http://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?tool=my_tool&email=my_email@example.com&ids=%s' % doc_id
    elif id_type in ['PMID', 'DOI', 'OTHER']:
        convert_link = 'http://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?tool=my_tool&email=my_email@example.com&ids=%s' % doc_id
    else:
        raise ValueError('Give id_type from PMC or PMID or DOI or OTHER')

    convert_page = requests.get(convert_link)
    convert_tree = html.fromstring(convert_page.content)
    record = convert_tree.find('record').attrib
    if 'status' in record or 'pmcid' not in record:
        raise ValueError('Cannot convert given document id to PMC')
    if id_type in ['PMID', 'DOI', 'OTHER']:
        if 'pmcid' in record:
            pmc = record['pmcid']
        else:
            pmc = ''
    return {'pmc': pmc,
            'pmid': record['pmid'] if 'pmid' in record else '',
            'doi': record['doi'] if 'doi' in record else ''}


def parse_citation_web(doc_id, id_type='PMC'):
    """
    Parse citations from given document id

    Parameters
    ----------
    doc_id: str or int, document id
    id_type: str from ['PMC', 'PMID', 'DOI', 'OTHER']

    Returns
    -------
    dict_out: dict, contains following keys
        pmc: Pubmed Central ID
        pmid: Pubmed ID
        doi: DOI of the article
        n_citations: number of citations for given articles
        pmc_cited: list of PMCs that cite the given PMC
    """

    doc_id_dict = convert_document_id(doc_id, id_type=id_type)
    pmc = doc_id_dict['pmc']
    link = "http://www.ncbi.nlm.nih.gov/pmc/articles/%s/citedby/" % pmc
    page = requests.get(link)
    tree = html.fromstring(page.content)
    n_citations = extract_citations(tree)
    n_pages = int(n_citations/30) + 1

    pmc_cited_all = list() # all PMC cited
    citations = tree.xpath('//div[@class="rprt"]/div[@class="title"]/a/@href')[1::]
    pmc_cited = list(map(extract_pmc, citations))
    pmc_cited_all.extend(pmc_cited)
    if n_pages >= 2:
        for i in range(2, n_pages+1):
            link = "http://www.ncbi.nlm.nih.gov/pmc/articles/%s/citedby/?page=%s" % (pmc, str(i))
            page = requests.get(link)
            tree = html.fromstring(page.content)
            citations = tree.xpath('//div[@class="rprt"]/div[@class="title"]/a/@href')[1::]
            pmc_cited = list(map(extract_pmc, citations))
            pmc_cited_all.extend(pmc_cited)
    pmc_cited_all = [p for p in pmc_cited_all if p is not pmc]
    dict_out = {'n_citations': n_citations,
                'pmid': doc_id_dict['pmid'],
                'pmc': re.sub('PMC', '', doc_id_dict['pmc']),
                'doi': doc_id_dict['doi'],
                'pmc_cited': pmc_cited_all}
    return dict_out


def parse_outgoing_citation_web(doc_id, id_type='PMC'):
    """
    Load citations from NCBI eutils API for a given document,
    return a dictionary containing:
        n_citations: number of citations for that article
        doc_id: the document ID number
        id_type: the type of document ID provided (PMCID or PMID)
        pmid_cited: list of papers cited by the document as PMIDs
    """
    doc_id = str(doc_id)
    if id_type is 'PMC':
        db = 'pmc'
        linkname = 'pmc_refs_pubmed'
    elif id_type is 'PMID':
        db = 'pubmed'
        linkname = 'pubmed_pubmed_refs'
    else:
        raise ValueError('Unsupported id_type `%s`' % id_type)
    link = 'http://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=%s&linkname=%s&id=%s' % (db, linkname, doc_id)

    tree = etree.parse(link)
    pmid_cited_all = tree.xpath('/eLinkResult/LinkSet/LinkSetDb/Link/Id/text()')
    n_citations = len(pmid_cited_all)
    if not n_citations: # If there are no citations, likely a bad doc_id
        return None
    dict_out = {'n_citations': n_citations,
                'doc_id': doc_id,
                'id_type': id_type,
                'pmid_cited': pmid_cited_all}
    return dict_out
