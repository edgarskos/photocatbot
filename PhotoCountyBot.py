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

import argparse
import os
import re
import sys
import time

import county_map
import mwparserfromhell as mw
import pywikibot
from pywikibot import pagegenerators

# These strings are used to find a starting category to crawl
# and a pattern to look for.  The location specified on the command
# line will be substituted into both.
#
startCat = 'Category:Wikipedia requested photographs in %s'

debug = False

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

def lookup_county(town):
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
        townpage = pywikibot.Page(pywikibot.Site(), town).get()
    except pywikibot.NoPage():
        return None

    w = mw.parse(townpage)
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

def maybe_create_category(county, state):
    cat = 'Category:Wikipedia requested photographs in %s' % county
    catpage = pywikibot.Page(pywikibot.Site(), cat)
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

def canonical_name(template):
    """Returns the canonical name of the template in mediawiki node
    'template', after following any redirects.
    """
    page = pywikibot.Page(pywikibot.Site(), 'Template:' + unicode(template.name))
    while page.isRedirectPage():
        page = page.getRedirectTarget()
    return page.title()

def is_photo_request(node):
    """Returns True if the specified mediawiki node represents a template
    that is or redirects to {{image requested}}.
    """
    if isinstance(node, mw.nodes.Template):
        return canonical_name(node) == 'Template:Image requested'
    return False


class PhotoCountyBot(pywikibot.bot.Bot):
    def __init__(self, state, **kwargs):
        self.state = state
        super(PhotoCountyBot, self).__init__(**kwargs)

    def treat(self, page):
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
            return

        newtext = False

        # Try finding a county by:
        #   - looking up the article title in the county map
        #   - looking for a county given explicitly in the article title
        #   - searching the text of the first paragraph for a related town

        # cm = county_map.county_map()
        # county = cm.lookup(article.title())
        county = lookup_county(article.title())
        if not county:
            county = find_county_in_text(page.title(), self.state)
        if not county:
            county = guess_county(text, self.state)

        if not county:
            print "couldn't guess at %s" % page.title()
            return

        # Find an {{image requested}} template and update it with
        # the desired location.
        oldtext = talk.get()
        parsed = mw.parse(oldtext)
        tmpls = parsed.filter_templates(matches=is_photo_request)
        if tmpls:
            tmpls[0].add('in', county)
        else:
            # insert a new {{image requested}} template after any
            # templates at the start of the article.
            for n in parsed.nodes:
                if isinstance(n, mw.nodes.Template):
                    continue
                parsed.insert_before(n, "\n")
                parsed.insert_before(n, mw.nodes.Template(
                    'image requested', ['in=' + county] ))
                break
        newtext = parsed.__unicode__()

        if not newtext:
            print "something friggin weird happened on %s" % article.title()
            return

        log(page.title())
        try:
            self.userPut(
                page, oldtext, newtext, botflag=True,
                comment='moving to [[Category:Wikipedia requested photographs in %s]] by the [[User:PhotoCatBot|PhotoCat]]' % county)
            #maybe_create_category(county, self.state, self.site)
        except pywikibot.LockedPage:
            return False


def main(argv):
    global startCat
    global debug

    debug = False
    state = False

    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', '-d',
                        help='enable debugging output',
                        action='store_true')
    parser.add_argument('--place', '-p', '--location', '-l',
                        help='specify location to start (required)',
                        required=True)

    args = parser.parse_args(argv[1:])
    debug = args.debug
    startCat = startCat % args.place

    site = pywikibot.Site()
    cat = pywikibot.Category(site, startCat)
    gen = pagegenerators.CategorizedPageGenerator(cat)
    bot = PhotoCountyBot(state=args.place, generator=gen)
    bot.run()


if __name__ == '__main__':
    try:
        main(sys.argv)
    finally:
        pywikibot.stopme()

