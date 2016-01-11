
# coding: utf-8

# 

# In[1]:

import optparse
import os
import sys
import re
import requests
import random

from unidecode import unidecode
import string
from windmill.authoring import WindmillTestClient
from windmill.conf import global_settings 
import urlparse
from copy import copy
import time

try:
    # Try importing for Python 3
    # pylint: disable-msg=F0401
    # pylint: disable-msg=E0611
    from urllib.request import HTTPCookieProcessor, Request, build_opener
    from urllib.parse import quote, unquote
    from http.cookiejar import MozillaCookieJar
except ImportError:
    # Fallback for Python 2
    from urllib2 import Request, build_opener, HTTPCookieProcessor
    from urllib import quote, unquote
    from cookielib import MozillaCookieJar

# Import BeautifulSoup -- try 4 first, fall back to older
try:
    from bs4 import BeautifulSoup
except ImportError:
    try:
        from BeautifulSoup import BeautifulSoup
    except ImportError:
        print('We need BeautifulSoup, sorry...')
        sys.exit(1)

# Support unicode in both Python 2 and 3. In Python 3, unicode is str.
if sys.version_info[0] == 3:
    unicode = str # pylint: disable-msg=W0622
    encode = lambda s: s # pylint: disable-msg=C0103
else:
    encode = lambda s: s.encode('utf-8') # pylint: disable-msg=C0103

def uniquelist(seq):
    seen = set()
    seen_add = seen.add
    return [ x for x in seq if not (x in seen or seen_add(x))]

def unique(a):
    """ return the list with duplicate elements removed """
    return list(set(a))

def uniquesets(a,b):
    return list(set(a) - set(b))

def intersect(a, b):
    """ return the intersection of two lists """
    return list(set(a) & set(b))

def union(a, b):
    """ return the union of two lists """
    return list(set(a) | set(b))

def LoadUserAgents(uafile):
    """
    uafile : string
        path to text file of user agents, one per line
    """
    uas = []
    with open(uafile, 'rb') as uaf:
        for ua in uaf.readlines():
            if ua:
                uas.append(ua.strip()[1:-1-1])
    random.shuffle(uas)
    return uas

class ScholarConf(object):
    """Helper class for global settings."""

    VERSION = '2.8'
    LOG_LEVEL = 1
    MAX_PAGE_RESULTS = 20 # Current maximum for per-page results
    SCHOLAR_SITE = 'http://scholar.google.com'
    SCHOLAR_CITATION_SITE = 'http://scholar.google.ca/citations'
    # ?user=5GTopjMAAAAJ&hl=en&oi=ao
    
    # USER_AGENT = 'Mozilla/5.0 (X11; U; FreeBSD i386; en-US; rv:1.9.2.9) Gecko/20100913 Firefox/3.6.9'
    # Let's update at this point (3/14):
    # USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64; rv:27.0) Gecko/20100101 Firefox/27.0'
    # USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_2) AppleWebKit/537.74.9 (KHTML, like Gecko) Version/7.0.2 Safari/537.74.9'
    # USER_AGENT = 'Opera/9.80 (X11; Linux i686; U; ru) Presto/2.8.131 Version/11.11'

    # load the user agents, in random order
    USER_AGENTS = LoadUserAgents(uafile="user_agent.txt")
    USER_AGENT = random.choice(USER_AGENTS)

    # If set, we will use this file to read/save cookies to enable
    # cookie use across sessions.
    COOKIE_JAR_FILE = None

class ScholarUtils(object):
    """A wrapper for various utensils that come in handy."""

    LOG_LEVELS = {'error': 1,
                  'warn':  2,
                  'info':  3,
                  'debug': 4}

    @staticmethod
    def ensure_int(arg, msg=None):
        try:
            return int(arg)
        except ValueError:
            raise FormatError(msg)

    @staticmethod
    def log(level, msg):
        if level not in ScholarUtils.LOG_LEVELS.keys():
            return
        if ScholarUtils.LOG_LEVELS[level] > ScholarConf.LOG_LEVEL:
            return
        sys.stderr.write('[%5s]  %s' % (level.upper(), msg + '\n'))
        sys.stderr.flush()

class ScholarArticleParser(object):
    """
    ScholarArticleParser can parse HTML document strings obtained from
    Google Scholar. This is a base class; concrete implementations
    adapting to tweaks made by Google over time follow below.
    """
    def __init__(self, site=None):
        self.soup = None
        self.article = None
        self.site = site or ScholarConf.SCHOLAR_CITATION_SITE
        self.year_re = re.compile(r'\b(?:20|19)\d{2}\b')

    def handle_article(self, art):
        """
        The parser invokes this callback on each article parsed
        successfully.  In this base class, the callback does nothing.
        """

    def handle_num_results(self, num_results):
        """
        The parser invokes this callback if it determines the overall
        number of results, as reported on the parsed results page. The
        base class implementation does nothing.
        """

    def parse(self, html):
        """
        This method initiates parsing of HTML content, cleans resulting
        content as needed, and notifies the parser instance of
        resulting instances via the handle_article callback.
        """
        self.soup = BeautifulSoup(html)

        # This parses any global, non-itemized attributes from the page.
        # self._parse_globals()

        # Now parse out listed articles:
        for div in self.soup.findAll(ScholarArticleParser._tag_results_checker):
            self._parse_article(div)
            self._clean_article()
            if self.article['title']:
                self.handle_article(self.article)

    def _clean_article(self):
        """
        This gets invoked after we have parsed an article, to do any
        needed cleanup/polishing before we hand off the resulting
        article.
        """
        if self.article['title']:
            self.article['title'] = self.article['title'].strip()


    def _parse_article(self, div):
        self.article = ScholarArticle()

        for tag in div:
            if not hasattr(tag, 'name'):
                continue

            if tag.name == 'div' and self._tag_has_class(tag, 'gs_rt') and \
                    tag.h3 and tag.h3.a:
                self.article['title'] = ''.join(tag.h3.a.findAll(text=True))
                self.article['url'] = self._path2url(tag.h3.a['href'])
                if self.article['url'].endswith('.pdf'):
                    self.article['url_pdf'] = self.article['url']

            if tag.name == 'font':
                for tag2 in tag:
                    if not hasattr(tag2, 'name'):
                        continue
                    if tag2.name == 'span' and \
                       self._tag_has_class(tag2, 'gs_fl'):
                        self._parse_links(tag2)

    def _parse_links(self, span):
        for tag in span:
            if not hasattr(tag, 'name'):
                continue
            if tag.name != 'a' or tag.get('href') is None:
                continue

            if tag.get('href').startswith('/scholar?cites'):
                if hasattr(tag, 'string') and tag.string.startswith('Cited by'):
                    self.article['num_citations'] = \
                        self._as_int(tag.string.split()[-1])

                # Weird Google Scholar behavior here: if the original
                # search query came with a number-of-results limit,
                # then this limit gets propagated to the URLs embedded
                # in the results page as well. Same applies to
                # versions URL in next if-block.
                self.article['url_citations'] = \
                    self._strip_url_arg('num', self._path2url(tag.get('href')))

                # We can also extract the cluster ID from the versions
                # URL. Note that we know that the string contains "?",
                # from the above if-statement.
                args = self.article['url_citations'].split('?', 1)[1]
                for arg in args.split('&'):
                    if arg.startswith('cites='):
                        self.article['cluster_id'] = arg[6:]

            if tag.get('href').startswith('/scholar?cluster'):
                if hasattr(tag, 'string') and tag.string.startswith('All '):
                    self.article['num_versions'] = \
                        self._as_int(tag.string.split()[1])
                self.article['url_versions'] = \
                    self._strip_url_arg('num', self._path2url(tag.get('href')))

            if tag.getText().startswith('Import'):
                self.article['url_citation'] = self._path2url(tag.get('href'))


    @staticmethod
    def _tag_has_class(tag, klass):
        """
        This predicate function checks whether a BeatifulSoup Tag instance
        has a class attribute.
        """
        res = tag.get('class') or []
        if type(res) != list:
            # BeautifulSoup 3 can return e.g. 'gs_md_wp gs_ttss',
            # so split -- conveniently produces a list in any case
            res = res.split()
        return klass in res

    @staticmethod
    def _tag_results_checker(tag):
        return tag.name == 'div' \
            and ScholarArticleParser._tag_has_class(tag, 'gsc_prf')

    @staticmethod
    def _as_int(obj):
        try:
            return int(obj)
        except ValueError:
            return None

    def _path2url(self, path):
        """Helper, returns full URL in case path isn't one."""
        if path.startswith('http://'):
            return path
        if not path.startswith('/'):
            path = '/' + path
        return self.site + path

    def _strip_url_arg(self, arg, url):
        """Helper, removes a URL-encoded argument, if present."""
        parts = url.split('?', 1)
        if len(parts) != 2:
            return url
        res = []
        for part in parts[1].split('&'):
            if not part.startswith(arg + '='):
                res.append(part)
        return parts[0] + '?' + '&'.join(res)

class ScholarQuerier(object):

    """
    ScholarQuerier instances can conduct a search on Google Scholar
    with subsequent parsing of the resulting HTML content.  The
    articles found are collected in the articles member, a list of
    ScholarArticle instances.
    """

    # Default URLs for visiting and submitting Settings pane, as of 3/14
    GET_SETTINGS_URL = ScholarConf.SCHOLAR_SITE + '/scholar_settings?'         + 'sciifh=1&hl=en&as_sdt=0,5'
    SET_SETTINGS_URL = ScholarConf.SCHOLAR_SITE + '/scholar_setprefs?'         + 'q='         + '&scisig=%(scisig)s'         + '&inststart=0'         + '&as_sdt=1,5'         + '&as_sdtp='         + '&num=%(num)s'         + '&scis=%(scis)s'         + '%(scisf)s'         + '&hl=en&lang=all&instq=&inst=569367360547434339&save='

    # Older URLs:
    # ScholarConf.SCHOLAR_SITE + '/scholar?q=%s&hl=en&btnG=Search&as_sdt=2001&as_sdtp=on

    class Parser(ScholarArticleParser):
        def __init__(self, querier):
            ScholarArticleParser.__init__(self)
            self.querier = querier

        def handle_num_results(self, num_results):
            if self.querier is not None and self.querier.query is not None:
                self.querier.query['num_results'] = num_results

        def handle_article(self, art):
            self.querier.add_article(art)

    def __init__(self):
        self.articles = []
        self.query = None
        self.cjar = MozillaCookieJar()

        # If we have a cookie file, load it:
        if ScholarConf.COOKIE_JAR_FILE and os.path.exists(ScholarConf.COOKIE_JAR_FILE):
            try:
                self.cjar.load(ScholarConf.COOKIE_JAR_FILE,
                               ignore_discard=True)
                ScholarUtils.log('info', 'loaded cookies file')
            except Exception as msg:
                ScholarUtils.log('warn', 'could not load cookies file: %s' % msg)
                self.cjar = MozillaCookieJar() # Just to be safe

        self.opener = build_opener(HTTPCookieProcessor(self.cjar))
        self.settings = None # Last settings object, if any

    def apply_settings(self, settings):
        """
        Applies settings as provided by a ScholarSettings instance.
        """
        if settings is None or not settings.is_configured():
            return True

        self.settings = settings

        # This is a bit of work. We need to actually retrieve the
        # contents of the Settings pane HTML in order to extract
        # hidden fields before we can compose the query for updating
        # the settings.
        html = self._get_http_response(url=self.GET_SETTINGS_URL,
                                       log_msg='dump of settings form HTML',
                                       err_msg='requesting settings failed')
        if html is None:
            return False

        # Now parse the required stuff out of the form. We require the
        # "scisig" token to make the upload of our settings acceptable
        # to Google.
        soup = BeautifulSoup(html)

        tag = soup.find(name='form', attrs={'id': 'gs_settings_form'})
        if tag is None:
            ScholarUtils.log('info', 'parsing settings failed: no form')
            return False

        tag = tag.find('input', attrs={'type':'hidden', 'name':'scisig'})
        if tag is None:
            ScholarUtils.log('info', 'parsing settings failed: scisig')
            return False

        urlargs = {'scisig': tag['value'],
                   'num': settings.per_page_results,
                   'scis': 'no',
                   'scisf': ''}

        if settings.citform != 0:
            urlargs['scis'] = 'yes'
            urlargs['scisf'] = '&scisf=%d' % settings.citform

        html = self._get_http_response(url=self.SET_SETTINGS_URL % urlargs,
                                       log_msg='dump of settings result HTML',
                                       err_msg='applying setttings failed')
        if html is None:
            return False

        ScholarUtils.log('info', 'settings applied')
        return True

    def send_query(self, query):
        """
        This method initiates a search query (a ScholarQuery instance)
        with subsequent parsing of the response.
        """
        self.clear_articles()
        self.query = query

        html = self._get_http_response(url=query.get_url(),
                                       log_msg='dump of query response HTML',
                                       err_msg='results retrieval failed')
        if html is None:
            return

        self.parse(html)

    def parse(self, html):
        """
        This method allows parsing of provided HTML content.
        """
        parser = self.Parser(self)
        parser.parse(html)

    def add_article(self, art):
        #self.get_citation_data(art)
        self.articles.append(art)

    def clear_articles(self):
        """Clears any existing articles stored from previous queries."""
        self.articles = []

    def save_cookies(self):
        """
        This stores the latest cookies we're using to disk, for reuse in a
        later session.
        """
        if ScholarConf.COOKIE_JAR_FILE is None:
            return False
        try:
            self.cjar.save(ScholarConf.COOKIE_JAR_FILE,
                           ignore_discard=True)
            ScholarUtils.log('info', 'saved cookies file')
            return True
        except Exception as msg:
            ScholarUtils.log('warn', 'could not save cookies file: %s' % msg)
            return False

    def _get_http_response(self, url, log_msg=None, err_msg=None):
        """
        Helper method, sends HTTP request and returns response payload.
        """
        if log_msg is None:
            log_msg = 'HTTP response data follow'
        if err_msg is None:
            err_msg = 'request failed'
        try:
            ScholarUtils.log('info', 'requesting %s' % unquote(url))
            ua = random.choice(ScholarConf.USER_AGENTS)

            """
            #r = requests.get('http://www.simpleproxy.info/browse.php?u=' + url)
            headers = {
                "Connection": "close",  # another way to cover tracks
                "User-Agent": ua}
            r = requests.get(url, headers=headers)
            html = r.html
            """
            """
            client = WindmillTestClient(__name__)
            client.open(url=url)
            client.waits()
            response = client.commands.getPageText()
            assert response['status']
            assert response['result']
            """

            req = Request(url=url, headers={'User-Agent': ua})
            hdl = self.opener.open(req)
            html = hdl.read()
            
            """
            ScholarUtils.log('debug', log_msg)
            ScholarUtils.log('debug', '>>>>' + '-'*68)
            ScholarUtils.log('debug', 'url: %s' % hdl.geturl())
            ScholarUtils.log('debug', 'result: %s' % hdl.getcode())
            ScholarUtils.log('debug', 'headers:\n' + str(hdl.info()))
            ScholarUtils.log('debug', 'data:\n' + html.decode('utf-8')) # For Python 3
            ScholarUtils.log('debug', '<<<<' + '-'*68)
            """

            return html
        except Exception as err:
            print ('info', err_msg + ': %s' % err)
            return None


def txt(querier, with_globals):
    if with_globals:
        # If we have any articles, check their attribute labels to get
        # the maximum length -- makes for nicer alignment.
        max_label_len = 0
        if len(querier.articles) > 0:
            items = sorted(list(querier.articles[0].attrs.values()),
                           key=lambda item: item[2])
            max_label_len = max([len(str(item[1])) for item in items])

        # Get items sorted in specified order:
        items = sorted(list(querier.query.attrs.values()), key=lambda item: item[2])
        # Find largest label length:
        max_label_len = max([len(str(item[1])) for item in items] + [max_label_len])
        fmt = '[G] %%%ds %%s' % max(0, max_label_len-4)
        for item in items:
            if item[0] is not None:
                print(fmt % (item[1], item[0]))
        if len(items) > 0:
            print

    articles = querier.articles
    for art in articles:
        print(encode(art.as_txt()) + '\n')


def _get_citation_info(author,html,journals=[]):
    soup = BeautifulSoup(html)
    name_div = soup.find(name='div', attrs={'id': 'gsc_prf_in'})
    if (name_div != None):
        name = unidecode(name_div.text)
        description = soup.findAll(name='div', attrs={'class': 'gsc_prf_il'})
        title = unidecode(description[0].text)
        email = ''
        institution = ''
        country = ''
        if len(description) > 2:
            # Retrieve email if verified
            fieldofstudy = description[1].text
            if (string.find(description[2].text,'Verified email at ') >= 0):
                email = description[2].text.replace('Verified email at ','')
                email = email.replace('- Homepage','')
                split_email = string.split(email,'.')
                institution = '.'.join(split_email[:-1])
                country = split_email[-1]
        else:
            fieldofstudy = description[1].text
        
        # Try to get a good approximate email
        email = description[2].text
        if (string.find(email,'Verified email at ') >= 0):
            email = email.replace('Verified email at ','')
            email = email.replace('- Homepage','')
        else:
            email = ''
        
        # Citation index
        citation_indices = soup.findAll(name='td', attrs={'class': 'gsc_rsb_std'})
        numberofcitations = float(citation_indices[0].text)
        hindex = float(citation_indices[2].text)
        i10index = float(citation_indices[4].text)
        
        # Is that person still active ?
        #   We can look at last publication..
        last_publication_date = soup.findAll(name='span', attrs={'class': 'gsc_a_h'})[1].text
        
        # List of co-authors
        coauthor_list = _get_coauthors(soup)
        
        # Approved journals
        number_of_approved_journals = _find_journal(html,journals)

        # Output structure
        info =  {'name': name,
                'title': title,
                'coauthors': coauthor_list,
                'numberofcitations': numberofcitations,
                'hindex': hindex,
                'i10index': i10index,
                'fieldofstudy': fieldofstudy,
                'email': email,
                'institution': institution,
                'country': country,
                'number_of_approved_journals': number_of_approved_journals}

        return info
    else:
        return None


# In[4]:

SCHOLAR_CITATION_PUBLICATION_QUERY_URL = ScholarConf.SCHOLAR_SITE + '/citations?'         + 'hl=%(hl)s'         + '&user=%(user)s'         + '&cstart=%(cstart)s'         + '&pagesize=%(pagesize)s'

def _get_coauthors_relationship(author,coauthors=None):
    coauthors_publication_count = {}
    cstart = 0
    end_of_publications = False
    while end_of_publications == False:
        urlargs = {'hl': 'en', 'user': author, 'cstart': cstart, 'pagesize': 100}
        url = SCHOLAR_CITATION_PUBLICATION_QUERY_URL % urlargs;
        querier = ScholarQuerier()
        html = querier._get_http_response(url)
        soup = BeautifulSoup(html)
        # Look for visible signs of having no articles left in our search
        eop_tag = html.find('There are no articles in this profile.')
        if eop_tag >= 0:
            # End the search if that's the case
            end_of_publications = True
        else:
            cstart = cstart + 100
            # If no list of authors were provided
            if coauthors == None:
                # We need to look through publications and them ourselves
                publications = soup.findAll(name='td', attrs={'class': 'gsc_a_t'})
                for pub in publications:
                    potential_coauthors = string.split(pub.find(name='div').text,',')
                    potential_coauthors =  [string.strip(unidecode(name),' ').lower().replace(' ','_') for name in potential_coauthors]
                    unique_coauthors = unique(potential_coauthors);
                    for uc in unique_coauthors:
                        if uc in coauthors_publication_count:
                            coauthors_publication_count[uc] = coauthors_publication_count[uc] + potential_coauthors.count(uc);
                        else:
                            coauthors_publication_count[uc] = 1;
            else:
                # Simply go through coauthors list and count
                for coauthor in coauthors:
                    full_name = [potential_name.lower() for potential_name in string.split(coauthor, ' ') if (len(potential_name) > 2)]
                    for name in full_name:
                        joint_publication = joint_publication + len([m.start() for m in re.finditer(name, html.lower())])
                    coauthors_publication_count = dict(coauthors_publication_count.items() + {coauthor: joint_publication})
    
    return coauthors_publication_count

def _get_coauthors(htmlsoup):
    coauthors_link = [tag.attrs.get('href') for tag in htmlsoup.findAll(name='a', attrs={'class': 'gsc_rsb_aa'})];
    google_coauthor_scholarid = [_get_url_arg(link)['user'] for link in coauthors_link]

    coauthors = {}
    for i in google_coauthor_scholarid:
        coauthors = dict(coauthors.items() + {i: {'ref':'', 'publication_count': 0}}.items())

    lookinpublication = 0
    if (lookinpublication == 1):
        # Find publication tag within HTML soup and extract potential names
        publication_coauthors = []
        publications = htmlsoup.findAll(name='td', attrs={'class': 'gsc_a_t'})
        for pub in publications:
            potential_coauthors = string.split(pub.find(name='div').text,',')
            potential_coauthors = [string.strip(unidecode(name),' ') for name in potential_coauthors]
            publication_coauthors = publication_coauthors + potential_coauthors

        # Count co-publication as metric of interest (giving credential to highest citation)
        copublication_count = {}
        for i in set(publication_coauthors):
            copublication_count = dict(copublication_count.items() + {i: publication_coauthors.count(i)}.items())

        # Try to extract GS-id from name and add to return structure
        search = {'hl': 'en', 'mauthors': '', 'view_op': 'search_authors'}
        for name in set(publication_coauthors):
            search['mauthors'] = name
            GS_id = _extract_scholarid(search)
            if (GS_id != None):
                if (GS_id in coauthors):
                    coauthors[GS_id]['ref'] = name
                    coauthors[GS_id]['publication_count'] = copublication_count[name]
                else:
                    coauthors = dict(coauthors.items() + {GS_id: {'ref': name, 'publication_count': copublication_count[name]}}.items())

    # Return dictionary
    return coauthors
    
def _get_url_arg(url):
    # Strip path from arguments
    url = url.replace('\\x3d','=')
    url = url.replace('\\x26','?')
    url = url.replace('&','?')
    url_split = url.split('?')
    # Get individual arg in array
    url_arg = dict()
    for arg in url_split:
        arg_split = arg.split('=')
        if len(arg_split) > 1:
            url_arg = dict(url_arg.items() + [arg.split('=') ])
    return url_arg


# Testing Co-Authorship functions
# args = {'user': '5GTopjMAAAAJ', 'sortby':' '};
# args = dict(default.items() + args.items())
# url = _build_scholarquery_url(args)
# querier = ScholarQuerier()
# html = querier._get_http_response(url)
# htmlsoup = BeautifulSoup(html)
#t = _get_coauthors(htmlsoup)




from bs4.element import Tag as HTMLTAG

SCHOLAR_QUERY_URL = ScholarConf.SCHOLAR_SITE + '/scholar?'         + 'start=%(start)s'         + '&q=%(q)s'         + '&hl=%(hl)s' 
        
def _build_scholarquery_url(args):
    urlargs = {'start': args['start'] or 0,
               'q': args['q'] or '',
               'hl': args['hl'] or 'en'}
    for key, val in urlargs.items():
            urlargs[key] = quote(str(val))
    return SCHOLAR_QUERY_URL % urlargs        
        
def _get_authors_from_publications(query):
    search = {'hl': 'en', 'q': query, 'start': 0}
    url = _build_scholarquery_url(search)
    querier = ScholarQuerier()
    html = querier._get_http_response(url)
    authors_id = [];
    if (html != None):
        htmlsoup = BeautifulSoup(html)
        publication_authors = htmlsoup.findAll(name='a', attrs={'href': re.compile(r'/citations\?user=*')})
        # Can we find links to authors ?
        for entry in publication_authors:
            scholarid = _get_url_arg(entry['href'])['user']
            authors_id = authors_id + [scholarid]
    return authors_id

        
def _gs_label_url(args):
    SCHOLAR_LABEL_URL = ScholarConf.SCHOLAR_SITE + '/citations?view_op=search_authors&hl=en&mauthors=label:' + '%(label)s' + '&after_author=%(after_author)s'
    urlargs = {'label': args['label'] or '',
               'after_author': args['after_author'] or ''}
    for key, val in urlargs.items():
            urlargs[key] = quote(str(val))
    return SCHOLAR_LABEL_URL % urlargs   

def _get_authors_from_label(label,after_author):
    search = {'label': label, 'after_author': after_author}
    url = _gs_label_url(search)
    querier = ScholarQuerier()
    html = querier._get_http_response(url)
    authors_id = [];
    if (html != None):
        htmlsoup = BeautifulSoup(html)
        publication_authors = htmlsoup.findAll(name='a', attrs={'href': re.compile(r'/citations\?user=*')})
        nextpage = htmlsoup.findAll(name='button', attrs={'class': 'gs_btnPR gs_in_ib gs_btn_half gs_btn_srt', 'aria-label':'Next'})
        if (len(nextpage) > 1):
            nextpage = nextpage[1]
        after_author = _get_url_arg(nextpage['onclick'])['after_author']
        # Can we find links to authors ?
        for entry in publication_authors:
            scholarid = _get_url_arg(entry['href'])['user']
            authors_id = authors_id + unique([scholarid])
    return {'authors_id': authors_id, 'nextpage':nextpage, 'after_author': after_author}

def _find_journal(html,journals):
    number_of_journals_found = 0
    html_lower = html.lower()
    for journal in journals:
        number_of_journals_found = number_of_journals_found + len([m.start() for m in re.finditer(journal, html_lower)])
    return number_of_journals_found

def _build_scholar_author_query_url(urlargs):
    return SCHOLAR_CITATION_PUBLICATION_QUERY_URL % urlargs


# In[14]:


GOOGLE_GEOCODE_URL = 'https://maps.googleapis.com/maps/api/geocode/'
GOOGLE_GEOCODE_QUERY_URL = GOOGLE_GEOCODE_URL + 'json?'         + 'address=%(address)s'

def _get_geocode_query_url(args):
    urlargs = {'address': args['address'] or ''}
    for key, val in urlargs.items():
            urlargs[key] = quote(str(val))
    return GOOGLE_GEOCODE_QUERY_URL % urlargs
    
def _get_coordinate_from_location(args):
    url = _get_geocode_query_url(args)
    html = querier._get_http_response(url)
    return dict(json.loads(html))

def _approximate_location_from_title(title):
    # Keep printable character
    pattern = re.compile('[\W_]+')
    title = pattern.sub(' ', title)
    return title.lower().replace('professor','').replace('director','').replace('associate','').strip()


# In[15]:

def _extract_localization(info):
    # Return structure
    localization = {'localization': None}
    query_response = {'status': 'ZERO_RESULTS'}
    # Insufficient information from title try email
    if info['email']:
        query_response = _get_coordinate_from_location({'address': info['email']})
    if query_response['status'] == 'ZERO_RESULTS':
        # Try to get an approximate location from title
        location = _approximate_location_from_title(info['title'])
        query_response = _get_coordinate_from_location({'address': location})
    if query_response['status'] == 'OK':
        # We got something to work with
        if len(query_response['results']) > 0:
            for response in query_response['results']:
                # Let's favor 'establishment' because they are more likely to be related to universities
                if (len(response['address_components'][0]['types']) > 0) :
                    if (response['address_components'][0]['types'][0] == 'establishment'):
                        long_name = response['address_components'][0]['long_name']
                        location = response['geometry']['location']
                        localization = {'localization': {'long_name': long_name, 'location': location}};
                        break
            if (localization['localization'] == None):
                # Just take the first one..
                long_name = query_response['results'][0]['address_components'][0]['long_name']
                location = query_response['results'][0]['geometry']['location']
                localization = {'localization': {'long_name': long_name, 'location': location}};
    return localization

SCHOLAR_AUTHOR_QUERY_URL = ScholarConf.SCHOLAR_SITE + '/citations?'         + 'hl=%(hl)s'         + '&mauthors=%(mauthors)s'         + '&view_op=%(view_op)s'
        
def _extract_scholarid(args):
    scholarid = None
    urlargs = {'hl': args['hl'] or 'en',
               'mauthors': args['mauthors'] or '',
               'view_op': args['view_op'] or 'search_authors'}
    for key, val in urlargs.items():
            urlargs[key] = quote(str(val))
    url = SCHOLAR_AUTHOR_QUERY_URL % urlargs
    querier = ScholarQuerier()
    html = querier._get_http_response(url)
    if html != None:
        soup = BeautifulSoup(html)
        name = soup.findAll(name='h3', attrs={'class': 'gsc_1usr_name'})
        if (name != None) & (len(name) == 1):
            link = name[0].children.next()['href']
            scholarid = _get_url_arg(link)['user']
    time.sleep(random.random()*10)
    return scholarid

