#!/usr/bin/env python
# encoding: utf-8
# Fetch Dublin Bus schedule information from dublinbus.ie
#
# Code is placed under MIT/X11 licence
# (c) 2010 Jean-Paul Bonnet and Jérémie Laval

#  Modified by Fergal Duffy

import re
import urllib2
import sys
import json
import time
import datetime
from pprint import pprint

#3rd party modules
from BeautifulSoup import BeautifulSoup

# Contains the existing Dublin Bus lines 
baseUrl = "http://www.dublinbus.ie/en/Your-Journey1/Timetables/All-Timetables/"
stopsUrl = "http://www.dublinbus.ie/Labs.EPiServer/GoogleMap/gmap_conf.aspx?custompageid=1219&routeNumber={0}&direction={1}&towards={2}"

# def main(testroutes=False):
#     availableLines = getAllRoutes()
#     reAirport = re.compile("Airport_Icon.png$|Airlink_Web_Logo.png$")
#     reAccessible = re.compile("Accessible_Icon.png$")
#     reMap = re.compile("'(.+)','(.+)','(.+)'")
#     done = []
#     for busData in availableLines:
#         print busData[0]
#         #If second link to timetable is there, skip it, it's dead.
#         if busData[0] in done:
#             continue
#         done.append(busData[0])
#         data = []
#         if testroutes and busData[0] not in testroutes:
#             continue
#         try:
#             #Try, and wait if error
#             timetable = getTimeTableFor(busData[1]) 
#             route_desc = soup.find("div",  id="route_description").string.replace('From ', '')
#             split_str = ""
#             for s in ["Towards "," to ","towards ","To "]:
#                 if s in route_desc:
#                     split_str = s
#                     break
#             road_end_points = [e.strip() for e in route_desc.split(split_str)]
#             fromPoint = road_end_points[0]
#             toPoint = road_end_points[1]
# 
#             icons = soup.find("div", attrs={ 'class' : 'timtable_icon' })
#             isAirport = icons.find("img", src=reAirport) != None
#             isAccessible = icons.find("img", src=reAccessible) != None
# 
#             #viewMaps = [reMap.search(div.a['onclick']) for div in soup.findAll('div', attrs={'class':'view_on_map'})]
#             data.append( 
#                 {'busNumber': busData[0],
#                     'route_desc': fromPoint if i == 0 else toPoint,
#                     'stops': stops,
#                     'to': toPoint if i == 0 else fromPoint,
#                     'mondayFriday': monday,
#                     'saturday': saturday,
#                     'sunday': sunday,
#                     'isAirport': isAirport,
#                     'isAccessible': isAccessible } )
#             print "Suceeded for bus no. %s dir %d" % (bus, i)
#         except:
#             print "For ", bus, ", error: ", sys.exc_info()[0]
#             raise
#             #continue

def test1(bus_num):
    for line in getAllRoutes():
        if line[0] in bus_num:
            #pprint(getTimeTableFor(line[1]))
            print "Got timetable for %s" % line[0]
            print
    
def main():
    curtime = datetime.datetime.now()
    jsonfile = 'stops_%s.json' % curtime.strftime("%Y-%m-%d")
    ttjsonfile = 'timetable_%s.json' % curtime.strftime("%Y-%m-%d")
    failed = []
    all_times = []
    for line in getAllRoutes():
        tt = get_timetable(line[1])#, json_f)
        if tt:
            all_times.append(tt)
            print "Got timetable for route no. %s" % line[0]
            #pprint(tt)
            print
        else:
            failed.append(line[0])
    print "Could not get timetable for route nos.: ", ', '.join(failed)
    with open(jsonfile, 'w') as json_f:
        json.dump([t['stops'] for t in all_times], json_f)
    with open(ttjsonfile, 'w') as ttjson_f:
        json.dump([t for t in all_times], ttjson_f)
        #pprint([t['stops'] for t in all_times])

def get_timetable(bus_id):
    '''
    Parse timetable html, and return timetable, (or False).
    Does not parse xpresso, nitelink, or airlink timetables (yet).
    '''
    soup = BeautifulSoup(get_timetable_html(bus_id))
    if is_xpresso(soup):
        return False
    elif is_airlink(soup):
        return False
    elif is_nitelink(soup):
        return False
    else:
        tt = get_normal_timetable(soup)
        if tt:
            return tt
        else:
            tt = get_multistop_timetable(soup)
            if tt:
                return tt
            else:
                print "Warning! unparseable route:", bus_id
                return False
        
def is_xpresso(soup):
    '''
    Determines if a route is xpresso, by having an 'x' in its route number, or
    having the xpresso logo on the page.
    '''
    c1 = 'x' in cleanup_strings([soup.find('div', id='timetable_top_left').string])[0]
    c2 = soup.findAll('img', src=re.compile(r".+Xpresso_Web_Logo.png"))
    return c1 or c2

def is_airlink(soup):
    '''
    Determines if a route is airlink, by checking for the airlink logo on the page
    '''
    return soup.findAll('img', src=re.compile(r".+Airlink_Web_Logo.png"))

def is_nitelink(soup):
    '''
    Determines if a route is nitelink by having an 'n' in its route number, or
    having the nitelink logo on the page.
    '''
    c1 = 'n' in cleanup_strings([soup.find('div', id='timetable_top_left').string])[0]
    c2 = soup.findAll('img', src=re.compile(r".+Nitelink.gif"))
    return c1 or c2

def get_normal_timetable(soup):#, json_file=None):
    '''
    Parse standard Dublin Bus timetables.
    Scrapes times and bus stop GPS locations from dublinbus.ie
    '''
    #Basic time format: \d\d:\d\d, which may repeat followed by a space
    time_pattern = r'^(\d\d:\d\d)'   
    #This sentence appears sometimes to pad out the timetable. Words can be seperated by spaces or newlines                                                                                         
    text_pattern = r'((then)|(After \d\d:\d\d))(\ about)?\ every\ \d{1,2}(-\d{1,2})?\ minutes(\ until\ \d{4})?'
    #In the timetable on days where no buses run
    no_service_pattern = r'No\ Service'
    last_bus_pattern = r'Last bus \d\d:\d\d'
    days = ['Monday-Friday', 'Saturday', 'Sunday']
    patterns = [time_pattern, 
                text_pattern,
                no_service_pattern,
                last_bus_pattern]
    #Get all divs of class "timetable sheet holder"
    #They will be in order: Mon, Sat, Sun, Mon, Sat, Sun.
    #By matching the text in the tags in these regions, we can extract the 
    #timetables.
    timetable_segments = soup.findAll('div', 'timetable_sheet_holder')
    #Get all NavigableString obejects, and clean up by removing spaces and newlines
    all_timetables = []
    for segment in timetable_segments:                                          
        raw_strings = segment.findAll(text=True)
        raw_strings = cleanup_strings(raw_strings)
        #Only keep those matching the regex
        timetable = []
        for string in raw_strings:
            for p in patterns:
                if re.search(p, string):
                    timetable.append(string)
        all_timetables.append(timetable)
    #Get route description:
    routes_html = soup.findAll("div", "timetables_title")
    descs = [' '.join(cleanup_strings(r.findAll(text=True))) for r in routes_html]
    #Rearrange into dict for output
    all_times = {}
    if all_timetables:
        all_stops = get_stop_locations(soup)
        all_times['stops'] = all_stops
        #stops_json = json.dumps(all_times['stops'])
        #print "JSON stops:", json.dumps(all_times['stops'])
        #if json_file:
        #    json.dump(all_times['stops'], json_file)
        all_times['dir1_times'] = dict(zip(days, all_timetables[:3]))
        all_times['dir1_desc'] = descs[0]
        if len(all_timetables) == 6:
            all_times['dir2_times'] = dict(zip(days, all_timetables[3:]))
            all_times['dir2_desc'] = descs[1]
        else:
            all_times['dir2_times'] = ''
            all_times['dir2_desc'] = ''
        return all_times
    elif not all_timetables:
        return False
        
def compare_times(t1, t2):
    '''
    Compare 2 time strings of the form XX:XX.
    Returns -1 if t1 < t2, 0 if t1 == t2, and +1 if t1 > t2
    '''
    h1, m1 = [int(t) for t in t1.split(':')]
    h2, m2 = [int(t) for t in t2.split(':')]
    if h1 > h2:
        return 1
    elif (h1 == h2) and (m1 > m2):
        return 1
    elif t1 == t2:
        return 0
    else:
        return -1

def get_multistop_timetable(soup):
    '''
    Parses dublin bus timetables where each row if times corresponds to a 
    different location, such as route 102.
    '''
    days = ['Monday-Friday', 'Saturday', 'Sunday']
    #Get all divs of class "timetable sheet holder"
    #They will be in order: Mon, Sat, Sun, Mon, Sat, Sun.
    #By matching the text in the tags in these regions, we can extract the 
    #timetables.
    timetable_segments = soup.findAll('div', 'timetable_sheet_holder_2')
    all_timetables = []
    for segment in timetable_segments: 
        #Row based timetables have html header rows contataining the 
        #locations and html time rows containing times
        header_rows = segment.findAll('div', 'vertical_display_item_3')
        time_rows = segment.findAll('div', 'vertical_display_item_4')
        headers = [cleanup_strings(r.findAll(text=True)) for r in header_rows]
        times = [cleanup_strings(r.findAll(text=True)) for r in time_rows]
        #Only keep those matching the regex
        timetable = {}
        for header, time_list in zip(headers, times):
            assert len(header) == 1
            header = header[0]
            if not header in timetable:
                timetable[header] = time_list
            else:
                timetable[header].extend(time_list)
        all_timetables.append(timetable)
    #Get route description:
    routes_html = soup.findAll("div", "timetables_title")
    descs = [' '.join(cleanup_strings(r.findAll(text=True))) for r in routes_html]
    #Rearrange into dict for output
    all_times = {}
    if all_timetables:
        all_stops = get_stop_locations(soup)
        all_times['stops'] = all_stops
        #stops_json = json.dumps(all_times['stops'])
        #print "JSON stops:", json.dumps(all_times['stops'])
        #if json_file:
        #    json.dump(all_times['stops'], json_file)
        all_times['dir1_times'] = dict(zip(days, all_timetables[:3]))
        all_times['dir1_desc'] = descs[0]
        if len(all_timetables) == 6:
            all_times['dir2_times'] = dict(zip(days, all_timetables[3:]))
            all_times['dir2_desc'] = descs[1]
        else:
            all_times['dir2_times'] = ''
            all_times['dir2_desc'] = ''
        return all_times
    elif not all_timetables:
        return False

def get_stop_locations(soup):
    '''
    Pass in a BeautifulSoup representation of the route site, and return
    bus stop locations.
    '''
    #We use the global stopsUrl link to get an xml document to parse for stop 
    #positions.
    #To get the values to sub into stopsUrl, we can pull them from the values
    #passed to the ShowMapDialog() link on the page
    divs = soup.findAll("div", "view_on_map")
    args_regex = r"ShowMapDialog\('(.+)','(.+)','(.+)','(.+)'\)"
    all_stops = []
    for div in divs:
        links = div.findAll('a',{'onclick':True})
        for link in links:
            # Find the <a> tag that has "onclick":"ShowMapDialog()" and extract 
            # the javascript arguments to get allow access to the bus stop 
            # locations through the stopsUrl
            attributes = link.attrs
            for attr_name, attr_value in attributes:
                if 'onclick' in attr_name and 'ShowMapDialog' in attr_value:
                    stop_details = {}#dict.fromkeys(['route', 'stops'])
                    match = re.search(args_regex, attr_value)
                    route, direction, terminus1, terminus2 = [g.strip() for g in match.groups()]
                    if direction == 'IO':
                        #Must have direction as I or O to get data...
                        direction = 'I'
                        stop_details['route'] = route
                        stop_details['terminus'] = terminus1
                        stop_details['stops'] = get_stop_latlngs(route, direction, terminus1)
                        all_stops.append(stop_details)
                    elif direction == 'OI':
                        direction = 'O'
                        stop_details['route'] = route
                        stop_details['terminus'] = terminus2
                        stop_details['stops'] =  get_stop_latlngs(route, direction, terminus2)
                        all_stops.append(stop_details)
                    else:
                        print "Error in stopsUrl values: got", 
                        route, direction, terminus1, terminus2
                    break
    return all_stops
    
        
def cleanup_strings(strings):
    '''
    Takes a list of strings and removes trailing/leading spaces and all
    newlines andcarriage returns, and returns what non-empty strings remain.
    Also removes html non-breaking spaces
    '''
    strings = [s.replace('\r\n', '').replace('\n','').replace('&nbsp;','').strip() for s in strings]
    return [s for s in strings if s]

# def firstTimeIsLarger(t1, t2):
#     #Pass in times in form 'hh:mm' True if first is equal to or larger
#     t1Pair = [int(a) for a in t1.split(':')]
#     t2Pair = [int(a) for a in t2.split(':')]
#     if t1Pair[0] > t2Pair[0]:
#         return True
#     elif t1Pair[0] == t2Pair and t1Pair[1] >= t2Pair [1]:
#         return True
#     else:
#         return False

def addMinutesToTime(time, minutes):
    #Time in format 'hh:mm'
    #freq in format 'mm'
    #minutes must be under 60
    #Dates do not rollover correctly: 23:50 + 20 will give 25:10
    t = [int(a) for a in time.split(':')]
    f = int(minutes)
    if f + t[1] < 60:
        hours, minutes = str(t[0]), str(f +t[1])
        if len(minutes) == 1:
            minutes = '0'+minutes
        if len(hours) == 1:
            hours = '0' +hours
        return hours+':'+minutes
    else:
        hours, minutes = str(t[0]+1), str((f+t[1])-60)
        if len(minutes) == 1:
            minutes = '0' + minutes
        if len(hours) == 1:
            hours = '0' +hours
        return hours+':'+ minutes

def get_timetable_html(busNumber, tries_left=3):
    '''
    Returns a handle to the HTML timetable page of a bus route.
    '''
    url = baseUrl + busNumber + '/'
    try:
        page = urllib2.urlopen(url)
    except URLError:
        if tries_left > 0:
            tries_left -= 1
            get_timetable_html(busnumber, tries_left)
        else:
            raise
    return page

def get_stop_latlngs(line, direction, terminus):
    '''
    Parse the xml page containing bus stop GPS locations.
    '''
    try:
        xml = urllib2.urlopen(stopsUrl.format(line, direction, terminus))
        soup = BeautifulSoup(xml)
        pois = soup.findAll('poi')
        return [(poi.gpoint.lat.string, poi.gpoint.lng.string) for poi in pois]
    except:
        print stopsUrl.format(line, direction, terminus)
        print "Not found"
    

def getAllRoutes():
    '''
    Returns all current bus numbers.
    Iterates through possible route listings pages, and uses getRoutes to
    scrape them.
    '''
    Lines = []
    i = 0
    while(True):
        i = i + 1
        try:
            Lines += getRoutes(i)  
        except:
            break
    return Lines

def getRoutes(page):
    '''
    Dublin bus lists bus available bus timetables on several webpages. This scrapes
    a specified listing page and returns the available routes.
    '''
    routes = []
    routes_url = "http://www.dublinbus.ie/en/Your-Journey1/Timetables/?searchtype=&searchquery=&filter=&currentIndex=" + str(page)
    html = urllib2.urlopen(routes_url)
    soup = BeautifulSoup(html)
    pattern = re.compile(".+/(.+)/$")
    tds = soup.findAll("td", { "class" : "RouteNumberColumn" })
    for td in tds:
        a = td.find(True)
        #Append the route name displayed on the page, and the last section of
        #of the link to the page containing the timetable.
        routes.append((a.contents[0].strip(), pattern.search(a['href']).group(1)))
    return routes
 
if __name__ == '__main__':
    if sys.argv[1:]:
        test1(sys.argv[1:])
    else:
        main()
