#! /usr/bin/python

# PhotoCountyBot
#
# Walk through [[Category:Wikipedia requested photographs in <state>]],
# looking for articles that can be reclassified into subcategories.
#
# Notes on sources for county information:
#
# Massachusetts: http://www.sec.state.ma.us/ele/elecct/cctidx.htm
# Pennsylvania: http://pennsylvania.hometownlocator.com/counties/
# Iowa: http://iowa.hometownlocator.com/counties/
# Maryland, Indiana, California?

import time
import re
import getopt, sys
import os

import county_map
import mwparserfromhell
import pywikibot
from pywikibot import pagegenerators

# These strings are used to find a starting category to crawl
# and a pattern to look for.  The location specified on the command
# line will be substituted into both.
#
startCat = 'Category:Wikipedia requested photographs in %s'

# This pattern matches photo request templates of the form
# {{image requested|in=Foobar}} (and which use *no* other parameters).
photoReqPatStr = (
    '{{(picreq'
    '|image request(?:ed)?'
    '|images? needed'
    '|photo'
    '|photoreq'
    '|photo(?:graph)? requested'
    '|picture needed'
    '|reqp'
    '|reqimage'
    '|req photograph'
    '|reqphoto(?:graph)?'
    '|requested photograph'
    '|needs image)'
    r'([^}]*)in[=|]%s}}'
)

photoReqPat = ''

global debug

class PhotoCountyBot(pywikibot.bot.Bot):
    def __init__(self, state, **kwargs):
        self.state = state
        super(PhotoCountyBot, self).__init__(**kwargs)

    def treat(self, page):
        process_page(self.site, page, self.state)


def main():
    global startCat
    global photoReqPat
    global debug
    debug = False
    state = False
    try:
        opts, args = getopt.getopt(
                        sys.argv[1:],
                        "dp:l:",
                        ["debug", "place=", "location="]
                        )
    except getopt.GetoptError, err:
        # print help information and exit:
        print str(err) # will print something like "option -a not recognized"
        sys.exit(2)
    for o, a in opts:
        if o in ('-d', '--debug'):
            debug = True
        if o in ('-p', '--place', '-l', '--location'):
            state = a

    if state:
        startCat = startCat % state
        photoReqPat = re.compile(photoReqPatStr % state, re.I)
    else:
        print "required argument 'location' missing"
        sys.exit(2)

    site = pywikibot.Site()
    cat = pywikibot.Category(site, startCat)
    gen = pagegenerators.CategorizedPageGenerator(cat)
    bot = PhotoCountyBot(state=state, generator=gen)
    bot.run()

def process_page(site, page, state):
    global photoReqPat
    global debug

    if page.isTalkPage():
        article = page.toggleTalkPage()
        talk = page
    else:
        article = page
        talk = page.toggleTalkPage()

    try:
        text = article.get()
    except KeyboardInterrupt:
        raise
    except:
        print "%s error thrown by %s" % (sys.exc_info()[0], article.title())
        return False

    newtext = False

    # Try finding a county by:
    #   - looking up the article title in the county map
    #   - looking for a county given explicitly in the article title
    #   - searching the text of the first paragraph for a related town

    # cm = county_map.county_map()
    # county = cm.lookup(article.title())
    county = lookup_county(article.title(), site)
    if not county:
        county = find_county_in_text(page.title(), state)
    if not county:
        county = guess_county(text, state)

    if county:
        talktext = talk.get()
        newtext = photoReqPat.sub(r'{{image requested|\2in=%s}}' % county, talktext)
        newtext = re.sub(r'{{image requested\|\|+', r'{{image requested|', newtext)
    else:
        print "couldn't guess at %s" % page.title()
        return False

    if not newtext:
        print "something friggin weird happened on %s" % article.title()
        return False
    elif newtext == talktext:
        print "nothing to do for %s" % page.title()
        return False
    else:
        log(page.title())
        log(newtext)
        if not debug:
            try:
                talk.put(newtext, 'moving to [[Category:Wikipedia requested photographs in %s]] by the [[User:PhotoCatBot|PhotoCat]]' % county)
                maybe_create_category(county, state, site)
                return True
            except pywikibot.LockedPage:
                return False

def guess_county(text, state):
    cm = county_map.county_map()

    # find the first paragraph in the text (skipping grafs that are
    # just templates or images)
    while re.match('\s*({{[^}]}}|\[\[[^]]?\]\])\n\s*', text, re.DOTALL):
        text = re.sub('^\s*({{[^}]}}|\[\[[^]]?\]\])\n\s*', '', text, re.DOTALL)
    grafs = re.split('\n\s*\n', text)
    try:
        intro = grafs[0]
    except IndexError:
        return None

    links = re.findall(r'\[\[(.*?)\]\]', intro)

    # look for [[Foo, Bar]] links and see if any of them are recognized towns
    for link in links:
        exactlink = link.split('|')[0]
        county = find_county_in_text(exactlink, state)
        if county:
            log("guess_county: found '{}' in link [[{}]]".format(county, exactlink))
            return county
        county = cm.lookup(exactlink)
        if county:
            log("guess_county: found '{}' from looking up link [[{}]]".format(county, exactlink))
            return county

def lookup_county(town, site):
    """Look up the county for a given town from its Wikipedia article.

    The 'town' argument should be the name of a Wikipedia
    article for a town or city.  lookup_county will load this
    article, look for {{Infobox settlement}} and will see if
    a county is named in one of the 'subdivision_name' parameters,
    and will return that county name if so.

    If no Wikipedia article exists for this town, or if the article
    does not have a matching infobox, or if the infobox does not
    mention a county, None is returned.
    """
    try:
        townpage = pywikibot.Page(site, town).get()
    except pywikibot.NoPage():
        return None

    w = mwparserfromhell.parse(townpage)
    for t in w.filter_templates():
        if t.name.strip_code() == 'Infobox settlement':
            # Find the subdivision_name parameters and
            # look for one that names a county
            params = [ p for p in t.params
                       if p.name.find('subdivision_name') > -1 ]
            for p in params:
                c = p.value.filter_wikilinks(matches='County,')
                if c:
                    return c[0].title

def find_county_in_text(text, state):
    m = re.search(' *([^,(]* County, %s)$' % state, text)
    if m:
        log("find_county_in_text: found {}".format(m.group(1)))
        return m.group(1)
    return False

def maybe_create_category(county, state, site):
    cat = 'Category:Wikipedia requested photographs in %s' % county
    catpage = pywikibot.Page(site, cat)
    try:
        text = catpage.get()
    except pywikibot.NoPage:
        catpage.put("""{{US image sources}}
{{howtoreqphotoin|%s}}
<br clear=all />

[[Category:Wikipedia requested photographs in %s|%s]]""" % (county, state, county))
        print 'created category [[%s]]' % cat

def log(msg):
    if debug:
        script = os.path.basename(__file__)
        print "{}: {} {}".format(script, time.asctime(), msg)

if __name__ == '__main__':
    try:
        main()
    finally:
        pywikibot.stopme()

