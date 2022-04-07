#!/usr/bin/python
# encoding: utf-8
#
# EitSupport
# Copyright (C) 2011 betonme
# Copyright (C) 2016 Wolfgang Fahl
# Copyright (C) 2018 Marco Hald
#
# This EITParser is based on:
# https://github.com/betonme/e2openplugin-EnhancedMovieCenter/blob/master/src/EitSupport.py
#
# In case of reuse of this source code please do not remove this copyright.
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   For more information on the GNU General Public License see:
#   <http://www.gnu.org/licenses/>.
#

# More information about the basic format can be found here:
#   https://www.etsi.org/deliver/etsi_en/300400_300499/300468/01.16.01_60/en_300468v011601p.pdf
#   "ETSI EN 300 468" v1.16.1 (2019-08)

import os
import struct
import sys
import getopt

from datetime import datetime

# s. Annex A - Table A.3: Character coding tables
char_coding_table = {
    1: 'iso-8859-5',
    2: 'iso-8859-6',
    3: 'iso-8859-7',
    4: 'iso-8859-8',
    5: 'iso-8859-9',
    6: 'iso-8859-10',
    7: 'iso-8859-11',
    9: 'iso-8859-13',
    10: 'iso-8859-14',
    11: 'iso-8859-15',
    12: 'iso-8859-15',
    13: 'iso-8859-15',
    14: 'iso-8859-15',
    16: 'FIXME: Refering to Table A.4',
    17: 'FIXME: ISO/IEC 10636',
    18: 'FIXME: KSX1001-2004',
    19: 'FIXME: GB-2312-1980',
    20: 'FIXME: Big5',
    21: 'utf-8',
    31: 'FIXME: next byte is encoding_type_id'
}


def decode_byte_string(data):
    codepage = None
    string = ""
    if len(data) > 0:
        encoding = data[0]
        if (encoding in char_coding_table):
            codepage = char_coding_table[encoding]
            string = bytes(data[1:]).decode(codepage)
        else:
            string = str(data)
    return(string, codepage)


def parseMJD(MJD):
    # Parse 16 bit unsigned int containing Modified Julian Date,
    # as per DVB-SI spec
    # returning year,month,day
    YY = int((MJD - 15078.2) / 365.25)
    MM = int((MJD - 14956.1 - int(YY*365.25)) / 30.6001)
    D = MJD - 14956 - int(YY*365.25) - int(MM * 30.6001)
    K = 0
    if MM == 14 or MM == 15:
        K = 1

    return (1900 + YY+K), (MM-1-K*12), D


def unBCD(byte):
    return (byte >> 4) * 10 + (byte & 0xf)


# Eit File support class
# Description
# http://de.wikipedia.org/wiki/Event_Information_Table
class EitList():

    def __init__(self, path=None):
        self.eit_file = None
        self.eit_mtime = 0

        # TODO
        # The dictionary implementation could be very slow
        self.eit = {}
        self.iso = None

        self.__newPath(path)
        self.__readEitFile()

    def __newPath(self, path):
        if path:
            if self.eit_file != path:
                self.eit_file = path

    def __mk_int(self, s):
        return int(s) if s else 0

    def __toDate(self, d, t):
        if d and t:
            # TODO Is there another fast and safe way to get the datetime
            try:
                return datetime(int(d[0]), int(d[1]), int(d[2]), int(t[0]), int(t[1]))
            except ValueError:
                return None
        else:
            return None

    ##############################################################################
    ## Get Functions
    def getEitsid(self):
        return self.eit.get('service', "")  # TODO

    def getEitTsId(self):
        return self.eit.get('transportstream', "")  # TODO

    def getEitWhen(self):
        return self.eit.get('when', "")

    def getEitStartDate(self):
        return self.eit.get('startdate', "")

    def getEitStartTime(self):
        return self.eit.get('starttime', "")

    def getEitDuration(self):
        return self.eit.get('duration', "")

    def getEitName(self):
        return self.eit.get('name', "").strip()

    def getEitDescription(self):
        return self.eit.get('description', "").strip()

    def getEitShortDescription(self):
        return self.eit.get('short_description', "").strip()

    def getEitExtendedDescription(self):
        return self.getEitDescription()

    def getEitLengthInSeconds(self):
        length = self.eit.get('duration', "")
        # TODO Is there another fast and safe way to get the length
        if len(length) > 2:
            return self.__mk_int((length[0]*60 + length[1])*60 + length[2])
        elif len(length) > 1:
            return self.__mk_int(length[0]*60 + length[1])
        else:
            return self.__mk_int(length)

    def getEitDate(self):
        return self.__toDate(self.getEitStartDate(), self.getEitStartTime())

    ##############################################################################
    ## File IO Functions
    def __readEitFile(self):
        data = ""
        path = self.eit_file

        if path and os.path.exists(path):
            mtime = os.path.getmtime(path)
            if self.eit_mtime == mtime:
                # File has not changed
                pass

            else:
                # New path or file has changed
                self.eit_mtime = mtime

                # Read data from file
                f = None
                try:
                    f = open(path, 'rb')
                    # lines = f.readlines()
                    data = f.read()
                except Exception as e:
                    print(("DEBUG: [META] Exception in readEitFile: " + str(e)))
                finally:
                    if f is not None:
                        f.close()

                # Parse the data
                if data and 12 <= len(data):
                    # go through events
                    pos = 0
                    e = struct.unpack(">HHBBBBBBH", data[pos:pos+12])
                    event_id = e[0]
                    date     = parseMJD(e[1])                         # Y, M, D
                    time     = unBCD(e[2]), unBCD(e[3]), unBCD(e[4])  # HH, MM, SS
                    duration = unBCD(e[5]), unBCD(e[6]), unBCD(e[7])  # HH, MM, SS
                    running_status  = (e[8] & 0xe000) >> 13
                    free_CA_mode    = e[8] & 0x1000
                    descriptors_len = e[8] & 0x0fff

                    if running_status in [1, 2]:
                        self.eit['when'] = "NEXT"
                    elif running_status in [3, 4]:
                        self.eit['when'] = "NOW"

                    self.eit['startdate'] = date
                    self.eit['starttime'] = time
                    self.eit['duration'] = duration

                    pos = pos + 12
                    name_event_descriptor = []
                    name_event_descriptor_multi = []
                    short_event_descriptor = []
                    short_event_descriptor_multi = []
                    extended_event_descriptor = []
                    extended_event_descriptor_multi = []
                    component_descriptor = []
                    content_descriptor = []
                    linkage_descriptor = []
                    parental_rating_descriptor = []
                    pdc_descriptor = []
                    endpos = len(data) - 1
                    while pos < endpos:
                        rec = descriptor_tag = data[pos]
                        descriptor_length = data[pos+1]
                        print("DEBUG: 0x%02x found" % rec)
                        print("DEBUG: 0x%02x - descriptor_tag: 0x%02x" % (rec, descriptor_tag))
                        print("DEBUG: 0x%02x - descriptor_length: %2d" % (rec, descriptor_length))
                        if pos + 1 >= endpos:
                            break
                        length = data[pos+1] + 2
                        # 0x4D = 'short_event_descriptor'
                        # details s. "6.2.37 Short event descriptor"
                        if rec == 0x4D:
                            print("DEBUG: 0x%02x - Short event descriptor" % rec)
                            ISO_639_language_code = str(data[pos+2:pos+5]).upper()
                            print("DEBUG: 0x%02x - ISO_639_language_code: (%s)'" % (rec, ISO_639_language_code))
                            event_name_length = data[pos+5]
                            print("DEBUG: 0x%02x - event_name_length: (%d)'" % (rec, event_name_length))
                            text_length = data[pos+6+event_name_length]
                            print("DEBUG: 0x%02x - text_length: (%d)'" % (rec, text_length))
                            name_event_description = ""

                            # read 'event_name_char':
                            name_event_description, codepage = decode_byte_string(data[pos+6:pos+6+event_name_length])
                            print("DEBUG: 0x%02x - event_name_char: '%s'(%d, %s)'" % (rec, name_event_description, len(name_event_description), codepage))

                            # read 'text_char':
                            short_event_description, codepage = decode_byte_string(data[pos+7+event_name_length:pos+7+event_name_length+text_length])
                            print("DEBUG: 0x%02x - event_text_char: '%s'(%d, %s)'" % (rec, short_event_description, len(short_event_description), codepage))

                            short_event_descriptor.append(short_event_description)
                            name_event_descriptor.append(name_event_description)
                        # 0x4E = 'extended_event_descriptor'
                        # details s. "6.2.15 Extended event descriptor"
                        elif rec == 0x4E:
                            print("DEBUG: 0x%02x - Extended event descriptor" % rec)
                            ISO_639_language_code = str(data[pos+3:pos+6]).upper()
                            print("DEBUG: 0x%02x - ISO_639_language_code: (%s)'" % (rec, ISO_639_language_code))
                            length_of_items = data[pos+6]
                            print("DEBUG: 0x%02x - length_of_items: (%d)'" % (rec, length_of_items))
                            text_length = data[pos+7+length_of_items]
                            print("DEBUG: 0x%02x - text_length: (%d)'" % (rec, text_length))
                            extended_event_description = ""

                            extended_event_description, codepage = decode_byte_string(data[pos+8:pos+8+text_length])
                            print("DEBUG: 0x%02x - extended_event_description: '%s'(%d, %s)'" % (rec, extended_event_description, len(extended_event_description), codepage))

                            extended_event_descriptor.append(extended_event_description)
                        # 0x50 = 'component_descriptor'
                        # details s. "6.2.8 Component descriptor"
                        elif rec == 0x50:
                            print("DEBUG: 0x%02x - Component descriptor" % rec)
                            stream_content = data[pos+2]
                            stream_content_ext = stream_content >> 4
                            stream_content = stream_content & 0xf
                            print("DEBUG: 0x%02x - stream_content/_ext 0x%01x/0x%01x" % (rec, stream_content, stream_content_ext))
                            component_type = data[pos+3]
                            component_tag = data[pos+4]
                            print("DEBUG: 0x%02x - component type/tag 0x%02x/0x%02x" % (rec, component_type, component_tag))
                            ISO_639_language_code = str(data[pos+5:pos+8]).upper()
                            print("DEBUG: 0x%02x - ISO_639_language_code: (%s)'" % (rec, ISO_639_language_code))
                            print("DEBUG: 0x%02x - '%s'" % (rec, data[pos+8:pos+length]))
                            text_char = data[pos+8:pos+length]
                            print("DEBUG: 0x%02x - text_char: '%s'(%d)'" % (rec, text_char, len(text_char)))
                            component_descriptor.append(data[pos+8:pos+length])
                        # 0x54 = 'content_descriptor '
                        # details s. "6.2.9 Content descriptor"
                        elif rec == 0x54:
                            print("DEBUG: 0x%02x - Content descriptor" % rec)
                            for i in range(0, descriptor_length >> 1):
                                content_nibble_level_1 = data[pos+2+i*2]
                                content_nibble_level_2 = content_nibble_level_1 & 0xf
                                content_nibble_level_1 = content_nibble_level_1 >> 4
                                user_byte = data[pos+2+i*2+1]
                            print("DEBUG: 0x%02x - content_nibble_level_1/2 0x%01x 0x%01x user_byte 0x%02x" % (rec, content_nibble_level_1, content_nibble_level_2, user_byte))
                            content_descriptor.append(data[pos+8:pos+length])
                        # 0x4A = 'linkage_descriptor '
                        # details s. "6.2.19 Linkage descriptor"
                        elif rec == 0x4A:
                            print("DEBUG: 0x%02x - Linkage descriptor" % rec)
                            # FIXME: No test data - maybe low/big endian?
                            transport_stream_id = (data[pos+2] << 8) + data[pos+3]
                            original_network_id = (data[pos+4] << 8) + data[pos+5]
                            service_id = (data[pos+6] << 8) + data[pos+7]
                            print("DEBUG: 0x%02x - transport/original/service_id 0x%04x 0x%04x 0x%04x" % (rec, transport_stream_id, original_network_id, service_id))
                            linkage_type = data[pos+8]
                            print("DEBUG: 0x%02x - linkage_type 0x%02x" % (rec, linkage_type))
                            linkage_descriptor.append(data[pos+8:pos+length])
                        # 0x55 = 'parental_rating_descriptor '
                        # details s. "6.2.28 Parental rating descriptor"
                        elif rec == 0x55:
                            print("DEBUG: 0x%02x - Parental rating descriptor" % rec)
                            parental_rating_descriptor.append(data[pos+2:pos+length])
                        # 0x69 = 'PDC_descriptor'
                        # details s. "6.2.30 PDC descriptor"
                        elif rec == 0x69:
                            print("DEBUG: 0x%02x - PDC descriptor" % rec)
                            # FIXME: No test data
                            pdc_descriptor.append(data[pos+2:pos+length])
                        else:
                            print("DEBUG: 0x%02x - Unknown descriptor" % rec)
                            print(data[pos:pos+length])
                            pass
                        pos += length

                    if name_event_descriptor:
                        name_event_descriptor = "".join(name_event_descriptor)
                    else:
                        name_event_descriptor = ("".join(name_event_descriptor_multi)).strip()

                    if short_event_descriptor:
                        short_event_descriptor = "".join(short_event_descriptor)
                    else:
                        short_event_descriptor = ("".join(short_event_descriptor_multi)).strip()

                    if extended_event_descriptor:
                        extended_event_descriptor = "".join(extended_event_descriptor)
                    else:
                        extended_event_descriptor = ("".join(extended_event_descriptor_multi)).strip()

                    if not(extended_event_descriptor):
                        extended_event_descriptor = short_event_descriptor

                    self.eit['name'] = name_event_descriptor
                    self.eit['short_description'] = short_event_descriptor
                    self.eit['description'] = extended_event_descriptor

                else:
                    # No date clear all
                    self.eit = {}

        else:
            # No path or no file clear all
            self.eit = {}


def make_unicode(input):
    if type(input) != str:
        input = input.decode('utf-8')
        return input
    else:
        return input


"""Module docstring.

Read Eit File and show the information.
"""


def readeit(eitfile):
    eitlist = EitList(eitfile)
    # print("\n name: \n");
    # print(eitlist.getEitName());
    # print("\n start: \n");
    # print(eitlist.getEitStartDate());
    # print("\n desc: \n");
    # print(eitlist.getEitDescription());
    # print("\n when: \n");
    # print(eitlist.getEitWhen());
    # print("\n starttime: \n");
    # print(eitlist.getEitStartTime());
    # print("\n duration: \n");
    # print(eitlist.getEitDuration());
    nfoname = eitfile.replace(".eit", ".nfo")
    nfo = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>{0}</title>
  <plot>{1}</plot>
</movie>""".format(eitlist.getEitName(), eitlist.getEitDescription())
    print(nfo)
    print(nfoname)

    #with io.open(nfoname, 'w', encoding='utf8') as f:
    #    f.write(make_unicode(nfo))


def main():
    # parse command line options
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help"])
    except getopt.error as msg:
        print(msg)
        print("for help use --help")
        sys.exit(2)
    # process options
    for o, a in opts:
        if o in ("-h", "--help"):
            print("Usage: python3 enigma2-eit-kodi-nfo-generator.py <dir-name1> <dir-name2> ...")
            sys.exit(0)
    # process arguments
    for arg in args:
        for root, dirs, files in os.walk(arg):
            for file in files:
                if file.endswith(".eit"):
                    name = os.path.join(root, file)
                    print(name)
                    readeit(name)  # process() is defined elsewhere
                    # break


if __name__ == "__main__":
    main()
