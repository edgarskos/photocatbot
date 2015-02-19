#! /usr/bin/env python

import getopt
import re
import sys
import time

import pywikibot
from pywikibot import pagegenerators

import mwparserfromhell

# PhotoCatFixer fixes photo categories on a single article.

# TODO:
#
#   * get location hints from other WikiProject templates
#      {{WikiProject Africa}}
#      {{WikiProject Australia}}
#      {{WikiProject Canada}}
#      {{WikiProject Caribbean}}
#      {{WikiProject Central America}}
#      {{WikiProject Football}}
#      {{WikiProject Micronesia}}
#      {{WikiProject Military History|...|British=y}}
#      {{WikiProject South America}}
#      {{WikiProject Southeast Asia}}
#      {{WikiProject Trains}}
#      {{WikiProject Melanesia}}
#   * guess county locations for U.S. states
#   * use canonical template names
#   * preserve "date" and "of" params on image requests

# Location names found in WikiProject United States, and
# the photo category names they translate to
WPUS_locations = {
    'AR': 'Arkansas',
    'AZ': 'Arizona',
    'CO': 'Colorado',
    'DE': 'Delaware',
    'DC': 'Washington, D.C.',
    'ID': 'Idaho',
    'IN': 'Indiana',
    'KY': 'Kentucky',
    'LA': 'Louisiana',
    'MA': 'Massachusetts',
    'MS': 'Mississippi',
    'NC': 'North Carolina',
    'ND': 'North Dakota',
    'NE': 'Nebraska',
    'NH': 'New Hampshire',
    'NM': 'New Mexico',
    'OH': 'Ohio',
    'RI': 'Rhode Island',
    'SC': 'South Carolina',
    'TX': 'Texas',
    'UT': 'Utah',
    'VT': 'Vermont',
    'WA': 'Washington',
    'WV': 'West Virginia',
    'WY': 'Wyoming',
    'Austin':            'Austin, Texas',
    'Boston':            'Boston, Massachusetts',
    'Cape Cod':          'Massachusetts',
    'Charlotte':         'Charlotte, North Carolina',
    'Cincinnati':        'Cincinnati, Ohio',
    'Coal-fields':       'Kentucky',
    'Durham':            'Durham, North Carolina',
    'EasternWashington': 'Washington',
    'EastWa':            'Washington',
    'Indianapolis':      'Indianapolis, Indiana',
    'Louisville':        'Louisville, Kentucky',
    'Lowell':            'Middlesex County, Massachusetts',
    'Metro':             'Washington, D.C.',
    'NOLA':              'New Orleans, Louisiana',
    'NHMTN':             'New Hampshire',
    'Ohiotownships':     'Ohio',
    'Omaha':             'Omaha, Nebraska',
    'Samoa':             'American Samoa',
    'SCMB':              'Myrtle Beach, South Carolina',
    'SATF':              'Bexar County, Texas',
    'Seattle':           'Seattle, Washington',
    'Shreveport':        'Shreveport, Louisiana',
    'Yellowstone':       'Yellowstone National Park',
    'Youngstown':        'Youngstown, Ohio',
    }

def canonical_name(site, template):
    """Return the canonical name of this template, after following any redirects."""
    page = pywikibot.Page(site, 'Template:' + unicode(template.name))
    while page.isRedirectPage():
        page = page.getRedirectTarget()
    return page.title()

def is_photo_request(site, template):
    return canonical_name(site, template) == 'Template:Image requested'

class PhotoCatFixer:

    # This pattern matches location-oriented WikiProjects.
    wikiLocationPat = re.compile(
        '(WikiProject|Project|WP)[ _]?'
        '(Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut'
        '|Delaware|Florida|Georgia \(U\.S\. state\)|Hawaii|Idaho|Illinois'
        '|Indiana|Iowa|Kansas|Kentucky|Louisiana|Louisville|Maine|Maryland'
        '|Mexico|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska'
        '|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina'
        '|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island'
        '|South Carolina|South Dakota|Tennessee|Texas|Utah|Virginia|Washington'
        '|West Virginia|Wisconsin|Wyoming'
        '|Afghanistan|Africa|Argentina|Australia|Bangladesh|Belgium|Bolivia|Bulgaria'
        '|Cambodia|Canada|Chile|Cornwall|Croatia|Cuba|Cyprus|Devon|Egypt'
        '|England|Finland|France|Ghana|Greece|Haiti|Hungary|Iceland|India|Indonesia'
        '|Iraq|Iran|Israel|Italy|Japan|Korea|Kuwait|Lebanon|Lithuania|London'
        '|Mongolia|Montenegro|New Zealand|Nigeria|Norway|Nottinghamshire|Oman|Ottawa|Pakistan'
        '|Poland|Portugal|Romania|Russia|Sheffield|Slovakia|Somalia|Spain|Sri Lanka|Surrey'
        '|Sweden|Syria|Taiwan|Tibet|Turkey|Vancouver|Venezuela|Vietnam|Yorkshire)'
        r'\s*(\||$)')

    # location_map, subject_map, and custom_map tell PhotoCatBot how to specify
    # photo requests for an article, based on what other WikiProject templates
    # are already present:
    #   - subject_map: specifies e.g. {{image requested|ships}} for {{WikiProject Ships}}
    #   - location_map: specifies e.g. {{image requested|in=China}} for {{WPCHINA}}
    #   - custom-map: adds e.g. 'needs-photo=yes' to the {{BirdTalk}} template
    #
    # The key of each map is the complete name of a talk page template, e.g.
    # {{TelevisionWikiProject}}, {{Visual arts}}, {{WPMILHIST}}.
    #
    # The value of subject_map is the 'subject' parameter to the
    # {{image requested}} template, e.g. {{image requested|ships}},
    # {{image requested|military history}}
    #
    # The value of location_map is an 'in' parameter to {{image requested}}.
    #
    # The value of custom_map is the name of the parameter for that template
    # that is used to add a photo request, e.g. {{BirdTalk|needs-photo=yes}}
    #
    subject_map = {
        'WikiProject Albums':           'albums',
        'WikiProject Alternative music': 'music',
        'WikiProject Agriculture':      'agricultural topics',
        'WikiProject Amateur radio':    'amateur radio' ,
        'WikiProject Anglicanism':      'religious subjects',
        'WikiProject Architecture':     'architecture',
        'WikiProject Aquarium Fishes':  'fish',
        'WikiProject Automobiles':      'cars',
        'WikiProject Basketball':       'basketball',
        'WikiProject Beer':             'beer',
        'WikiProject Board and table games': 'games',
        'WikiProject Brands':           'brands',
        'WikiProject Bridges':          'bridges',
        'WikiProject British crime':    'law and crime topics',
        'WikiProject British TV shows': 'television programs',
        'WikiProject Battlestar Galactica': 'television programs',
        'WikiProject Boxing':           'boxing',
        'WikiProject Buddhism':         'religious subjects',
        'WikiProject Business':         'business & economic topics',
        'WikiProject Catholicism':      'religious subjects',
        'WikiProject Chemicals':        'chemical compounds',
        'WikiProject Christianity':     'religious subjects',
        'WikiProject Christian music':  'music',
        'WikiProject Classical music':  'music',
        'WikiProject College football': 'American football people',
        'WikiProject Computing':        'computing equipment',
        'WikiProject Country Music':    'music',
        'WikiProject Companies':        'business & economic topics',
        'WikiProject Cricket':          'cricket',
        'WikiProject Crime':            'law and crime topics',
        'WikiProject Criminal Biography': 'law and crime topics',
        'WikiProject Cycling':          'cycling people',
        'WikiProject Discographies':    'albums',
        'WikiProject E-theatre':        'performing arts',
        'WikiProject Earthquakes':      'earthquakes',
        'WikiProject Economics':        'business & economic topics',
        'WikiProject Electronics':      'electronics',
        'WikiProject Environment':      'environmental topics',
        'WikiProject Fashion':          'fashion',
        'WikiProject Fencing':          'sports and games',
        'WikiProject Football':         'association football people',
        'WikiProject Figure Skating':   'performing arts',
        'WikiProject Fisheries and Fishing': 'fisheries and fishing',
        'WikiProject Formula One':      'cars',
        'WikiProject Fungi':            'fungi',
        'WikiProject Gemology and Jewelry': 'jewelry',
        'WikiProject Geology':          'geology',
        'WikiProject Guitarists':       'musicians',
        'WikiProject Gymnastics':       'gymnastics',
        'WikiProject Horse racing':     'equestrians',
        'WikiProject Hospitals':        'hospitals',
        'WikiProject International relations': 'political topics',
        'WikiProject Jazz':             'music',
        'WikiProject Judaism':          'religious subjects',
        'WikiProject Languages':        'languages',
        'WikiProject Libraries':        'libraries',
        'WikiProject Law':              'law and crime topics',
        'WikiProject Law Enforcement':  'law and crime topics',
        'WikiProject Lost':             'television programs',
        'WikiProject Magazines':        'publications',
        'WikiProject Medicine':         'medical subjects',
        'WikiProject Metal':            'music',
        'WikiProject Museums':          'museums',
        'WikiProject Music of the United Kingdom': 'music',
        'WikiProject Musical Instruments': 'musical instruments',
        'WikiProject Military history': 'military history',
        'WikiProject Mythology':        'mythology subjects',
        'WikiProject Neopaganism':      'religious subjects',
        'WikiProject Newspapers':       'publications',
        'WikiProject Olympics':         'sports and games',
        'WikiProject Opera':            'music',
        'WikiProject Organized Labour': 'political topics',
        'WikiProject Photography':      'photography',
        'WikiProject Physics':          'physics subjects',
        'WikiProject Pinball':          'games',
        'WikiProject Politics':         'political topics',
        'WikiProject Pop music':        'music',
        'WikiProject Pritzker-GLAM':    'military history',
        'WikiProject Professional wrestling': 'professional wrestling performers',
        'WikiProject Punk music':       'music',
        'WikiProject R&B and Soul Music': 'music', 
        'WikiProject Religion':         'religious subjects',
        'WikiProject Rivers':           'rivers and waterfalls',
        'WikiProject Rock music':       'music',
        'WikiProject Role-playing games': 'games',
        'WikiProject Rugby league':     'rugby league people',
        'WikiProject Rugby union':      'rugby union people',
        'WikiProject Saints':           'Saints',
        'WikiProject Schools':          'schools',
        'WikiProject Scouting':         'Scouting and Guiding',
        'WikiProject Severe weather':   'earth science subjects',
        'WikiProject Sexuality':        'sexuality subjects',
        'WikiProject Ships':            'ships',
        'WikiProject Shipwrecks':       'ships',
        'WikiProject Shopping Centers': 'shopping centers',
        'WikiProject Songs':            'music',
        'WikiProject Spiders':          'arthropods',
        'WikiProject Spirits':          'food and drink',
        'WikiProject Terrorism':        'political topics',
        'WikiProject Textile Arts':     'textiles and fabrics',
        'WikiProject Theatre':          'performing arts',
        'WikiProject Trucks':           'trucks',
        'WikiProject Toys':             'toys',
        'WikiProject Universities':     'schools',
        'WikiProject Viruses':          'Viruses',
        'WikiProject Visual arts':      'art',
        'WikiProject Zoo':              'zoos',
        }

    location_map = {
        'WikiProject Burma (Myanmar)':    'Burma',
        'WikiProject Central Asia':       'Asia',
        'WikiProject Chicago':            'Chicago, Illinois',
        'WikiProject Cleveland':          'Cleveland, Ohio',
        'WikiProject Education in the United Kingdom': 'the United Kingdom',
        'WikiProject Houston':            'Houston, Texas',
        'WikiProject Micronesia':         'the Federated States of Micronesia',
        'WikiProject Music of the United Kingdom': 'the United Kingdom',
        'WikiProject Netherlands':        'the Netherlands',
        'WikiProject Philippine History': 'the Philippines',
        'WikiProject Philippines':        'the Philippines',
        'WikiProject Tambayan Philippines': 'the Philippines',
        'WikiProject U.S. Congress':      'Washington, D.C.',
        'WikiProject UK Roads':           'the United Kingdom',
        'WikiProject United Kingdom':     'the United Kingdom',
        }
    
    custom_map = {
        'WikiProject Amphibians and Reptiles':   'needs-photo',
        'WikiProject Amusement Parks':           'imageneeded',
        'WikiProject Anatomy':                   'needs-photo',
        'WikiProject Animals':                   'needs-photo',
        'WikiProject Animation':                 'needs-image',
        'WikiProject Anime and manga':           'needs-image',
        'WikiProject Armenia':                   'needs-photo',
        'WikiProject Arthropods':                'needs-photo',
        'WikiProject Astronomy':                 'needs-image',
        'WikiProject Atlanta':                   'imageneeded',
        'WikiProject Aviation':                  'Imageneeded',
        'WikiProject Baseball':                  'image',
        'WikiProject Biography':                 'needs-photo',
        'WikiProject Biology':                   'needs-photo',
        'WikiProject Birds':                     'needs-photo',
        'WikiProject Books':                     'needs-infobox-cover',
        'WikiProject Brazil':                    'needs-photo',
        'WikiProject Canada':                    'needs-photo',
        'WikiProject Cats':                      'needs-photo',
        'WikiProject Chemistry':                 'needs-picture',
        "WikiProject Children's literature":     'needs-infobox-cover',
        'WikiProject China':                     'image-needed',
        'WikiProject Comics':                    'photo',

        'WikiProject Dance':                     'needs-image',
        'WikiProject Denmark':                   'imageneeded',
        'WikiProject Ecuador':                   'imageneeded',
        'WikiProject Electronic music':          'needs-photo',
        'WikiProject Energy':                    'needs-photo',
        'WikiProject Engineering':               'imageneeded',
        'WikiProject Film':                      'needs-image',
        'WikiProject Firearms':                  'needs-image',
        'WikiProject Fishes':                    'imageneeded',
        'WikiProject Food and drink':            'needs-photo',
        'WikiProject Games':                     'needs-photo',
        'WikiProject Gastropods':                'needs-photo',
        'WikiProject Genetics':                  'imageneeded',
        'WikiProject Georgia (U.S. state)':      'imageneeded',
        'WikiProject Germany':                   'imageneeded',
        'WikiProject Heraldry and vexillology':  'imageneeded',
        'WikiProject Hong Kong':                 'image-needed',
        'WikiProject Ice Hockey':                'needs-photo',
        'WikiProject Industrial design':         'needs-image',
        'WikiProject Insects':                   'needs-photo',
        'WikiProject Internet culture':          'needs-photo',
        'WikiProject Ireland':                   'image-needed',
        'WikiProject Latter Day Saint movement': 'needs-photo',
        'WikiProject Lepidoptera':               'needs-photo',
        'WikiProject Mammals':                   'needs-photo',
        'WikiProject Mauritius':                 'image-needed',
        'WikiProject Micro':                     'needs-photo',
        'WikiProject Moldova':                   'imageneeded',
        'WikiProject Motorcycling':              'image-needed',
        'WikiProject Mountains':                 'needs-photo',
        'WikiProject Musical Theatre':           'imageneeded',
        'WikiProject New York City':             'image-needed',
        'WikiProject Nickelodeon':               'needs-image',
        'WikiProject National Football League':  'needs-image',
        'WikiProject Novels':                    'needs-infobox-cover',
        'WikiProject Plants':                    'needs-photo',
        'WikiProject Politics of the United Kingdom': 'needs-picture',
        'WikiProject Primates':                  'needs-photo',
        'WikiProject Russia':                    'imageneeded',
        'WikiProject Singapore':                 'imagerequest',
        'WikiProject Skyscrapers':               'imageneeded',
        'WikiProject Software':                  'needs-image',
        'WikiProject Soil':                      'needs-photo',
        'WikiProject South Africa':              'image-needed',
        'WikiProject Spaceflight':               'needs-image',
        'WikiProject Star Trek':                 'needs-picture',
        'WikiProject Swimming':                  'needs-photo',
        'WikiProject Television':                'needs-image',
        'WikiProject Trains':                    'imageneeded',
        'WikiProject U2':                        'needs-photo',
        'WikiProject Video games':               'screenshot',
        'WikiProject Wales':                     'imageneeded',
        'WikiProject Wine':                      'needs-photo',
        }

    def __init__(self, site, article, debug=False):
        self._site = site
        self._article = (article.toggleTalkPage()
                         if article.isTalkPage()
                         else article)
        self._article_text = None
        self._article_talk = None
        self._debug = debug

    def article_text(self):
        """Return the text of this article."""
        if not self._article_text:
            self._article_text = self._article.get()
        return self._article_text

    def article_talk(self):
        """Return the (parsed) text of this article's talk page."""
        if not self._article_talk:
            self._article_talk = self._article.toggleTalkPage().get()
        return self._article_talk

    def handle_article(self):
        """Update any categories on this article that need updating."""
        try:
            if self.needs_update():
                self.fix_category()
        except pywikibot.InvalidTitle as e:
            self.log('ERROR', e)

    def needs_update(self):
        """Returns True if the article's talk page includes any
        {{image requested}} templates that lack any unnamed parameter
        and lack an 'in' parameter."""
        self._parsed_text = mwparserfromhell.parse(self.article_talk())
        for tmpl in self._parsed_text.filter_templates():
            if (is_photo_request(self._site, tmpl)
                and not tmpl.has(1)
                and not tmpl.has('in')):
                return True
        return False

    def fix_category(self):
        text = self.article_talk()
        newtext = self.fix_photo_request()

        if not newtext:
            self.log('EMPTY')
        elif newtext == text:
            self.log('UNCHANGED')
        else:
            self.log('MODIFIED')
            if self._debug:
                pywikibot.showDiff(text, newtext)
            else:
                try:
                    self._article.toggleTalkPage().put(newtext, PhotoCatBot.editComment)
                    time.sleep(30)
                except pywikibot.LockedPage:
                    pass

    def fix_photo_request(self):
        image_request_tmpl = None
        locations = { }
        subjects = { }
        changed_banners = False   # set to True when WikiProject banners are updated

        # Find the image request template, so we may easily add to it.
        template_list = self._parsed_text.filter_templates()
        for t in template_list:
            if is_photo_request(self._site, t):
                image_request_tmpl = t

        # visit each template in the text and examine it for clues:
        #   * location clues from state highways WikiProjects
        #   * location clues from location_map templates
        #   * subject matter clues from subject_map templates
        for t in template_list:

            for loc in self.guess_locations(t):
                locations[loc] = True

            # Look up this template in the location map, subject map etc.
            # by its canonical name.
            #
            template_name = canonical_name(self._site, t)
            if template_name.startswith('Template:'):
                template_name = template_name[9:]

            if PhotoCatFixer.subject_map.has_key(template_name):
                subj_name = PhotoCatFixer.subject_map[template_name]
                subjects[subj_name] = True

            if PhotoCatFixer.custom_map.has_key(template_name):
                # This WikiProject template has its own image request parameter,
                # which must be set to 'yes'.
                photo_param = PhotoCatFixer.custom_map[template_name]
                t.add(photo_param, 'yes')
                changed_banners = True

        # Remove any redundant locations we may have added.
        # TODO: generalize this.
        #
        if locations.has_key('Australia'):
            for loc in ('Australian Capital Territory', 'New South Wales',
                        'Northern Territory', 'Queensland', 'South Australia',
                        'Tasmania', 'Western Australia', 'Victoria'):
                if locations.has_key(loc):
                    del locations['Australia']
                    break

        if locations.has_key('Canada'):
            for loc in ('Alberta', 'British Columbia', 'Manitoba', 'New Brunswick',
                        'Newfoundland and Labrador', 'Northwest Territories',
                        'Nova Scotia', 'Ontario', 'Quebec', 'Saskatchewan',
                        'Nunavut', 'Prince Edward Island', 'the Yukon'):
                if locations.has_key(loc):
                    del locations['Canada']
                    break

        # Delete any country location if we have both "Country" and
        # "County, Country".
        for loc in locations.keys():
            m = re.match(r'.*, ([^,]*)$', loc)
            if m:
                country = m.group(1)
                if locations.has_key(country):
                    del locations[country]

        if locations or subjects:
            # Update the image request template with the values from
            # 'subjects' and 'locations'
            if not image_request_tmpl.name.matches('image requested'):
                image_request_tmpl.name = 'image requested'
            i = 1
            for subj in subjects.keys():
                # work around a parser bug with empty template params
                # https://github.com/earwig/mwparserfromhell/issues/51
                try:
                    if image_request_tmpl.get(i) == '':
                        image_request_tmpl.remove(i)
                except ValueError:
                    pass
                image_request_tmpl.add(i, subj)
                i += 1
            i = 1
            for loc in locations.keys():
                in_param = "in" if i == 1 else "in{}".format(i)
                image_request_tmpl.add(in_param, loc)
                i += 1

        # Last: if we modified some banners, and the image_request_tmpl
        # template is left without any locations or subjects
        # or 'of' param, it may be removed.
        if changed_banners \
            and not image_request_tmpl.has(1) \
            and not image_request_tmpl.has('in') \
            and not image_request_tmpl.has('of'):
            self._parsed_text.remove(image_request_tmpl)

        return unicode(self._parsed_text)

    def guess_locations(self, template):
        locations = []
        template_name = canonical_name(self._site, template)

        if template_name.startswith('Template:'):
            template_name = template_name[9:]

        # wikiLocationPat has the regional category name embedded
        # in the template name, so we use a special regex for it
        m = PhotoCatFixer.wikiLocationPat.match(template_name)
        if m:
            locations.append(m.group(2))

        # {{U.S. Roads WikiProject|state=AL|state1=MO|state3=TX|...}}
        if template_name == 'U.S. Roads WikiProject':
            # TODO: scan the params and add state names
            pass

        # Check the location_map, subject_map and custom_map
        if PhotoCatFixer.location_map.has_key(template_name):
            locations.append(PhotoCatFixer.location_map[template_name])

        # WikiProject United States has locations embedded as parameters
        if template_name == 'WikiProject United States':
            # if {{WikiProject United States|...|ST=yes}} then add ST
            default_loc = 'the United States'
            for loc_param in WPUS_locations.keys():
                if template.has(loc_param):
                    locations.append(WPUS_locations[loc_param])
                    default_loc = None
            if default_loc:
                locations.append(default_loc)

        return locations

    def log(self, result, errmsg=''):
        print u"{}: {} [[Talk:{}]] {}".format(
            time.asctime(),
            result,
            self._article.title(),
            errmsg)

class PhotoCatBot:
    # class constants

    startCategory = 'Category:Wikipedia requested photographs'
    editComment = ('cleanup for the [[User:Twp/Drafts/WikiProject Photo'
                   ' Requests|Photo Request WikiProject]], by the'
                   ' [[User:PhotoCatBot|PhotoCat]]')

    # This pattern matches unqualified photo request templates.
    # TODO: instead, replace any template for which
    #       tmpl.is_photo_request() is true.
    photoReplacePattern = re.compile(
        '{{(PicRequest'
        '|image ?req'
        '|image request(ed)?'
        '|images? needed'
        '|photo'
        '|photo ?req'
        '|photo(graph)? requested'
        '|reqp'
        '|req ?image'
        '|request image'
        '|req[ -]?photo'
        '|request photo'
        '|requested picture'
        '|needimages'
        '|needs image)'
        r'\s*\|?[^{}]*}}',
        re.I)

    def main(self):
        debug = False
        try:
            opts, args = getopt.getopt(sys.argv[1:], 'dc:', ['debug', 'category'])
        except getopt.GetoptError, err:
            # print help information and exit:
            print str(err) # will print something like "option -a not recognized"
            sys.exit(2)
        for o, a in opts:
            if o in ('-d', '--debug'):
                debug = True
            if o in ('-c', '--cat', '--category'):
                startCat = o

        site = pywikibot.getSite()
        cat = pywikibot.Category(site, PhotoCatBot.startCategory)

        if args:
            for title in args:
                page = pywikibot.Page(site, title.decode('utf-8'))
                photo_fixer = PhotoCatFixer(site, page, debug)
                photo_fixer.handle_article()
        else:
            gen = pagegenerators.CategorizedPageGenerator(cat)
            for page in gen:
                photo_fixer = PhotoCatFixer(site, page, debug)
                photo_fixer.handle_article()

def main():
    try:
        bot = PhotoCatBot()
        bot.main()
    finally:
        pywikibot.stopme()

if __name__ == '__main__':
    main()
