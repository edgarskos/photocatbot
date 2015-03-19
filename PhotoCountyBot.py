#! /usr/bin/python

# PhotoCountyBot
#
# Walk through [[Category:Wikipedia requested photographs in <state>]],
# looking for articles that can be reclassified into subcategories.

import wikipedia, catlib, pagegenerators
import time
import re
import getopt, sys
import county_map

# These strings are used to find a starting category to crawl
# and a pattern to look for.  The location specified on the command
# line will be substituted into both.
#
startCat = 'Category:Wikipedia requested photographs in %s'
photoReqPatStr = r'{{(reqphoto|photoreq|photo|picture|image *request|image *requested|reqimage|photo *needed)([^}]*)in[=|]%s}}'
photoReqPat = ''

global debug

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

    site = wikipedia.getSite()
    cat = catlib.Category(site, startCat)
    gen = pagegenerators.CategorizedPageGenerator(cat)
    for page in gen:
        if process_page(page, state):
            time.sleep(30)

def process_page(page, state):
    global photoReqPat
    global debug

    if (page.title().find("Talk:") == 0):
        talk = page
        article = wikipedia.Page(None, page.title().replace("Talk:","",1))
    else:
        article = page
        talk = wikipedia.Page(None, "Talk:" + page.title())

    try:
        text = article.get()
    except:
        print "%s error thrown by %s" % (sys.exc_info()[0], article.title())
        return False

    newtext = False

    # Try finding a county by:
    #   - looking up the article title in the county map
    #   - looking for a county given explicitly in the article title
    #   - searching the text of the first paragraph for a related town
    cm = county_map.county_map()
    county = cm.lookup(article.title())
    if not county:
        county = find_county_in_text(page.title(), state)
    if not county:
        county = guess_county(text, state)

    if county:
        talktext = talk.get()
        newtext = photoReqPat.sub(r'{{reqphoto|\2in=%s}}' % county, talktext)
        newtext = re.sub(r'{{reqphoto\|\|+', r'{{reqphoto|', newtext)
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
        if debug:
            print "Debug: %s" % page.title()
            print newtext
        else:
            try:
                talk.put(newtext, 'moving to [[Category:Wikipedia requested photographs in %s]] by the [[User:PhotoCatBot|PhotoCat]]' % county)
                maybe_create_category(county, state)
                return True
            except wikipedia.LockedPage:
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
            return county
        county = cm.lookup(exactlink)
        if county:
            return county

def find_county_in_text(text, state):
    m = re.search(' *([^,(]* County, %s)$' % state, text)
    if m:
        return m.group(1)
    return False

def maybe_create_category(county, state):
    cat = 'Category:Wikipedia requested photographs in %s' % county
    catpage = wikipedia.Page(None, cat)
    try:
        text = catpage.get()
    except wikipedia.NoPage:
        catpage.put("""{{US image sources}}
{{howtoreqphotoin|%s}}
<br clear=all />

[[Category:Wikipedia requested photographs in %s|%s]]""" % (county, state, county))
        print 'created category [[%s]]' % cat

try:
    main()
finally:
    wikipedia.stopme()

