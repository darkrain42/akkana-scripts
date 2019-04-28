#!/usr/bin/env python3

import ephem
from datetime import datetime
import xml.dom.minidom
import math
import sys
from pprint import pprint
import argparse


def nearest_time(targettime, t1, t2):
    '''Given a target datetime and two other datetimes,
       return the time closer to the target.
    '''
    d1 = abs(targettime - t1)
    d2 = abs(targettime - t2)
    if d1 <= d2:
        return d1
    return d2


def find_rise_set(observer, obj, d=None):
    '''Given an object (like Sun or Moon), find its rising and setting time
       closest to the given date d, either preceding or following it,
       for the observer's location.
       If date isn't specified, use the observer's date.
    '''
    if d:
        observer.date = d
    prevrise = observer.previous_rising(obj)
    nextrise = observer.next_rising(obj)
    prevset = observer.previous_setting(obj)
    nextset = observer.next_setting(obj)

    risetime = nearest_time(observer.date, prevrise, nextrise)
    observer.date = risetime
    obj.compute(observer)
    rise_az = obj.az
    settime = nearest_time(observer.date, prevset, nextset)
    observer.date = settime
    obj.compute(observer)
    set_az = obj.az

    return { 'rise': rise_az / ephem.degree,
             'set': set_az / ephem.degree }


def find_azimuths(observer):
    riseset = {}

    # Find sunrise and sunset:
    riseset['sun'] = find_rise_set(observer, ephem.Sun())

    # Now find the full moon closest to the date,
    # which may be the next full moon or the previous one.
    lastfull = ephem.previous_full_moon(observer.date)
    nextfull = ephem.next_full_moon(observer.date)
    now = ephem.now()
    if now - lastfull > nextfull - now:
        observer.date = nextfull
    else:
        observer.date = lastfull

    riseset['full moon'] = find_rise_set(observer, ephem.Moon())

    return riseset


def angle_between(wp1, wp2):
    '''Bearing from one waypoint to another.
       Waypoints are [name, lat, lon, ele]
    '''
    # https://www.movable-type.co.uk/scripts/latlong.html
    # https://stackoverflow.com/questions/3932502/calculate-angle-between-two-latitude-longitude-points
    lat1, lon1 = wp1[1], wp1[2]
    lat2, lon2 = wp2[1], wp2[2]
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) \
        - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (360. - math.atan2(y, x) / ephem.degree) % 360


def find_alignments(observer, waypoints, year=None):
    '''Find all the alignments with solstice/equinox sun/moon rise/set.
       Returns a dict: { 'vernal equinox': { 'moon': { 'rise': 94.17... } } }
       of azimuth angles in decimal degrees
    '''
    azimuths = {}

    if not year:
        year = datetime.now().year
    start_date = ephem.Date('1/1/%d' % year)

    observer.date = ephem.next_equinox(start_date)
    azimuths['vernal equinox'] = find_azimuths(observer)

    observer.date = ephem.next_solstice(observer.date)
    azimuths['summer solstice'] = find_azimuths(observer)

    observer.date = ephem.next_equinox(observer.date)
    azimuths['autumnal equinox'] = find_azimuths(observer)

    observer.date = ephem.next_solstice(observer.date)
    azimuths['winter solstice'] = find_azimuths(observer)

    # pprint(azimuths)

    # How many degrees is close enough?
    DEGREESLOP = 2.

    # Now go through all the angles between waypoints and see if
    # any of them correspond to any of the astronomical angles.
    matches = []
    for wp1 in waypoints:
        for wp2 in waypoints:
            if wp1 == wp2:
                continue
            angle = angle_between(wp1, wp2)

            # Does that angle match any of our astronomical ones?
            for season in azimuths:
                for body in azimuths[season]:
                    for event in azimuths[season][body]:
                        if abs(azimuths[season][body][event] - angle) < DEGREESLOP:
                            matches.append([wp1[0], wp2[0],
                                            '%s %s%s' % (season, body, event)])

    print("Matches:")
    pprint(matches)


def read_track_file_GPX(filename):
    """Read a GPX track file. Ignore tracks.
       Return a list of [name, lat, lon, ele] floats for waypoints.
    """

    dom = xml.dom.minidom.parse(filename)
    first_segment_name = None
    observer = None

    # Handle waypoints
    waypts = dom.getElementsByTagName("wpt")
    if not waypts:
        return []

    waypoints = []
    pointno = 0
    for pt in waypts:
        lat = float(pt.getAttribute("lat"))
        lon = float(pt.getAttribute("lon"))
        try:
            ele = float(get_DOM_text(pt, "ele"))
        except:
            ele = 500    # meters

        name = get_DOM_text(pt, "name")
        if not name:
            pointno += 1
            name = "Point %d" % pointno

        waypoints.append([ name, lat, lon, ele ])
        if name.lower() == "observer":
            observer = pt

    # pprint(waypoints)
    return observer, waypoints


def get_DOM_text(node, childname=None):
    '''Get the text out of a DOM node.
       Or, if childname is specified, get the text out of a child
       node with node name childname.
    '''
    if childname:
        nodes = node.getElementsByTagName(childname)
        # print "node has", len(nodes), childname, "children"
        if not nodes:
            return None
        node = nodes[0]
    if not node:
        return None
    n = node.childNodes
    if len(n) >= 1 and n[0].nodeType == n[0].TEXT_NODE:
        return n[0].data
    return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=""
        """Find alignments between latitude/longitude coordinate pairs
and the sun. moon, and other objects on special dates such as
solstices and equinoxes.

Observer location may be specified either with -o lat,lon,ele or by
naming one of the GPX waypoints 'Observer'; otherwise the first
waypoint in the first file will be taken as the observer location.

When specifying location on the command line, latitude and longitude
are in decimal degrees. Elevation is optional; it will be assumed to be
meters unless followed by the letter f,
e.g. -o 34.8086585,-103.2011914,1650f""",
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-o', '--observer', action="store", dest="observer",
                        help='Observer location (lat,lon[,ele])')
    parser.add_argument('gpxfiles', nargs='+', help='GPX files of waypoints')
    args = parser.parse_args(sys.argv[1:])

    if args.observer:
        floats = args.observer.split(',')
        lat = float(floats[0].strip())
        lon = float(floats[1].strip())
        if len(floats) > 2:
            if floats[2].endswith('f'):    # ends with f, convert feet to meters
                ele = float(floats[2][:-1].strip()) * 0.3048
            elif floats[2].endswith('m'):  # ends with m, already meters
                ele = float(floats[2][:-1].strip())
            else:                          # assume meters
                ele = float(floats[2].strip())
        else:
            ele = 0.
        observerPoint = [ 'Observer', lat, lon, ele ]
    else:
        observerPoint = None

    waypoints = []
    for filename in args.gpxfiles:
        obs, wp = read_track_file_GPX(filename)
        if wp:
            waypoints += wp
        else:
            print("No waypoints in", filename)
        if obs:
            observerPoint = obs

    if not waypoints:
        parser.print_help()
        sys.exit(1)

    if not observerPoint:
        print("First waypoint:", waypoints[0])
        observerPoint = waypoints[0]

    observer = ephem.Observer()
    # Observer will take degrees as a string, but if you pass it floats
    # it expects radians, though that's undocumented.
    observer.lat = observerPoint[1] * ephem.degree
    observer.lon = observerPoint[2] * ephem.degree
    if len(observerPoint) > 3:
        observer.elevation = observerPoint[3]
    else:
        observer.elevation = 500.0  # meters
    observer.name = "%s %f, %f, %f" % (observerPoint[0],
                                       observer.lon, observer.lat,
                                       observer.elevation)
    print(observer)
    print()

    find_alignments(observer, waypoints)