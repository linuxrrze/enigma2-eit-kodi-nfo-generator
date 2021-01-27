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

import os
import struct
import time
import io
import chardet

from datetime import datetime
from pprint import pprint
from inspect import getmembers

def dump(obj):
  '''return a printable representation of an object for debugging'''
  newobj=obj
  if '__dict__' in dir(obj):
    newobj=obj.__dict__
    if ' object at ' in str(obj) and not newobj.has_key('__type__'):
      newobj['__type__']=str(obj)
    for attr in newobj:
      newobj[attr]=dump(newobj[attr])
  return newobj

#from Components.config import config
#from Components.Language import language
#from EMCTasker import print
#from IsoFileSupport import IsoSupport
#from MetaSupport import getInfoFile

#def crc32(data):
#   poly = 0x4c11db7
#   crc = 0xffffffffL
#   for byte in data:
#       byte = ord(byte)
#       for bit in range(7,-1,-1):  # MSB to LSB
#           z32 = crc>>31    # top bit
#           crc = crc << 1
#           if ((byte>>bit)&1) ^ z32:
#               crc = crc ^ poly
#           crc = crc & 0xffffffffL
#   return crc

decoding_charSpecHR = {u'Ć': u'\u0106', u'æ': u'\u0107', u'®': u'\u017D', u'¾': u'\u017E', u'©': u'\u0160', u'¹': u'\u0161', u'Č': u'\u010C', u'è': u'\u010D', u'ð': u'\u0111'}

decoding_charSpecCZSK = {u'Ï'+u'C': u'Č',u'Ï'+u'E': u'Ě',u'Ï'+u'L': u'Ľ',u'Ï'+u'N': u'Ň',u'Ï'+u'R': u'Ř',u'Ï'+u'S': u'Š',u'Ï'+u'T': u'Ť',u'Ï'+u'Z': u'Ž',u'Ï'+u'c': u'č',u'Ï'+u'd': u'ď',u'Ï'+u'e': u'ě',u'Ï'+u'l': u'ľ', u'Ï'+u'n': u'ň',
u'Ï'+u'r': u'ř',u'Ï'+u's': u'š',u'Ï'+u't': u'ť',u'Ï'+u'z': u'ž',u'Ï'+u'D': u'Ď',u'Â'+u'A': u'Á',u'Â'+u'E': u'É',u'Â'+u'I': u'Í',u'Â'+u'O': u'Ó',u'Â'+u'U': u'Ú',u'Â'+u'a': u'á',u'Â'+u'e': u'é',u'Â'+u'i': u'í',u'Â'+u'o': u'ó',
u'Â'+u'u': u'ú',u'Â'+u'y': u'ý',u'Ã'+u'o': u'ô',u'Ã'+u'O': u'Ô',u'Ê'+u'u': u'ů',u'Ê'+u'U': u'Ů',u'È'+u'A': u'Ä',u'È'+u'E': u'Ë',u'È'+u'I': u'Ï',u'È'+u'O': u'Ö',u'È'+u'U': u'Ü',u'È'+u'Y': u'Ÿ',u'È'+u'a': u'ä',u'È'+u'e': u'ë',
u'È'+u'i': u'ï',u'È'+u'o': u'ö',u'È'+u'u': u'ü',u'È'+u'y': u'ÿ'}

def convertCharSpecHR(text):
    for i, j in decoding_charSpecHR.iteritems():
        text = text.replace(i, j)
    return text

def convertCharSpecCZSK(text):
    for i, j in decoding_charSpecCZSK.iteritems():
        text = text.replace(i, j)
    return text

def parseMJD(MJD):
    # Parse 16 bit unsigned int containing Modified Julian Date,
    # as per DVB-SI spec
    # returning year,month,day
    YY = int( (MJD - 15078.2) / 365.25 )
    MM = int( (MJD - 14956.1 - int(YY*365.25) ) / 30.6001 )
    D  = MJD - 14956 - int(YY*365.25) - int(MM * 30.6001)
    K=0
    if MM == 14 or MM == 15: K=1

    return (1900 + YY+K), (MM-1-K*12), D

def unBCD(byte):
    return (byte>>4)*10 + (byte & 0xf)


#from Tools.ISO639 import LanguageCodes
# -*- coding: iso-8859-2 -*-
LanguageCodes = { }
LanguageCodes["deu"] = LanguageCodes["ger"] = LanguageCodes["de"] = ("German", "Germanic")
LanguageCodes["fra"] = LanguageCodes["fre"] = LanguageCodes["fr"] = ("French", "Romance")


def language_iso639_2to3(alpha2):
    ret = alpha2
    if alpha2 in LanguageCodes:
        language = LanguageCodes[alpha2]
        for alpha, name in LanguageCodes.items():
            if name == language:
                if len(alpha) == 3:
                    return alpha
    return ret
#TEST
#print LanguageCodes["sv"]
#print language_iso639_2to3("sv")


# Eit File support class
# Description
# http://de.wikipedia.org/wiki/Event_Information_Table
class EitList():

	EIT_SHORT_EVENT_DESCRIPTOR = 0x4d
	EIT_EXTENDED_EVENT_DESCRIPOR = 0x4e

	def __init__(self, path=None):
		self.eit_file = None
		self.eit_mtime = 0

		#TODO
		# The dictionary implementation could be very slow
		self.eit = {}
		self.iso = None

		self.__newPath(path)
		self.__readEitFile()

	def __newPath(self, path):
		name = None
		if path:
			if self.eit_file != path:
				self.eit_file = path

	def __mk_int(self, s):
		return int(s) if s else 0

	def __toDate(self, d, t):
		if d and t:
			#TODO Is there another fast and safe way to get the datetime
			try:
				return datetime(int(d[0]), int(d[1]), int(d[2]), int(t[0]), int(t[1]))
			except ValueError:
				return None
		else:
			return None

	##############################################################################
	## Get Functions
	def getEitsid(self):
		return self.eit.get('service', "") #TODO

	def getEitTsId(self):
		return self.eit.get('transportstream', "") #TODO

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
		#TODO Is there another fast and safe way to get the length
		if len(length)>2:
			return self.__mk_int((length[0]*60 + length[1])*60 + length[2])
		elif len(length)>1:
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

		lang = language_iso639_2to3( "de" )

		if path and os.path.exists(path):
			mtime = os.path.getmtime(path)
			if self.eit_mtime == mtime:
				# File has not changed
				pass

			else:
				#print "EMC TEST count Eit " + str(path)

				# New path or file has changed
				self.eit_mtime = mtime

				# Read data from file
				# OE1.6 with Pyton 2.6
				#with open(self.eit_file, 'r') as file: lines = file.readlines()
				f = None
				try:
					f = open(path, 'rb')
					#lines = f.readlines()
					data = f.read()
				except Exception, e:
					print("[META] Exception in readEitFile: " + str(e))
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

					if running_status in [1,2]:
						self.eit['when'] = "NEXT"
					elif running_status in [3,4]:
						self.eit['when'] = "NOW"

					self.eit['startdate'] = date
					self.eit['starttime'] = time
					self.eit['duration'] = duration

					pos = pos + 12
					name_event_descriptor = []
					name_event_descriptor_multi = []
					name_event_codepage = None
					short_event_descriptor = []
					short_event_descriptor_multi = []
					short_event_codepage = None
					extended_event_descriptor = []
					extended_event_descriptor_multi = []
					extended_event_codepage = None
					component_descriptor = []
					content_descriptor = []
					linkage_descriptor = []
					parental_rating_descriptor = []
					endpos = len(data) - 1
					prev1_ISO_639_language_code = "x"
					prev2_ISO_639_language_code = "x"
					while pos < endpos:
						rec = ord(data[pos])
						if pos+1>=endpos:
							break
						length = ord(data[pos+1]) + 2
						if rec == 0x4D:
							descriptor_tag = ord(data[pos+1])
							descriptor_length = ord(data[pos+2])
							ISO_639_language_code = str(data[pos+2:pos+5]).upper()
							event_name_length = ord(data[pos+5])
							name_event_description = ""
							for i in range (pos+6,pos+6+event_name_length):
								if str(ord(data[i]))=="10" or int(str(ord(data[i])))>31:
									name_event_description += data[i]
							if not name_event_codepage:
								try:
									byte1 = str(ord(data[pos+6]))
								except:
									byte1 = ''
								if byte1=="1": name_event_codepage = 'iso-8859-5'
								elif byte1=="2": name_event_codepage = 'iso-8859-6'
								elif byte1=="3": name_event_codepage = 'iso-8859-7'
								elif byte1=="4": name_event_codepage = 'iso-8859-8'
								elif byte1=="5": name_event_codepage = 'iso-8859-9'
								elif byte1=="6": name_event_codepage = 'iso-8859-10'
								elif byte1=="7": name_event_codepage = 'iso-8859-11'
								elif byte1=="9": name_event_codepage = 'iso-8859-13'
								elif byte1=="10": name_event_codepage = 'iso-8859-14'
								elif byte1=="11": name_event_codepage = 'iso-8859-15'
								elif byte1=="21": name_event_codepage = 'utf-8'
								if name_event_codepage:
									print("[META] Found name_event encoding-type: " + name_event_codepage)
							short_event_description = ""
							if not short_event_codepage:
								try:
									byte1 = str(ord(data[pos+7+event_name_length]))
								except:
									byte1 = ''
								if byte1=="1": short_event_codepage = 'iso-8859-5'
								elif byte1=="2": short_event_codepage = 'iso-8859-6'
								elif byte1=="3": short_event_codepage = 'iso-8859-7'
								elif byte1=="4": short_event_codepage = 'iso-8859-8'
								elif byte1=="5": short_event_codepage = 'iso-8859-9'
								elif byte1=="6": short_event_codepage = 'iso-8859-10'
								elif byte1=="7": short_event_codepage = 'iso-8859-11'
								elif byte1=="9": short_event_codepage = 'iso-8859-13'
								elif byte1=="10": short_event_codepage = 'iso-8859-14'
								elif byte1=="11": short_event_codepage = 'iso-8859-15'
								elif byte1=="21": short_event_codepage = 'utf-8'
								if short_event_codepage:
									print("[META] Found short_event encoding-type: " + short_event_codepage)
							for i in range (pos+7+event_name_length,pos+length):
								if str(ord(data[i]))=="10" or int(str(ord(data[i])))>31:
									short_event_description += data[i]
							if ISO_639_language_code == lang:
								short_event_descriptor.append(short_event_description)
								name_event_descriptor.append(name_event_description)
							if (ISO_639_language_code == prev1_ISO_639_language_code) or (prev1_ISO_639_language_code == "x"):
								short_event_descriptor_multi.append(short_event_description)
								name_event_descriptor_multi.append(name_event_description)
							else:
								short_event_descriptor_multi.append("\n\n" + short_event_description)
								name_event_descriptor_multi.append(" " + name_event_description)
							prev1_ISO_639_language_code = ISO_639_language_code
						elif rec == 0x4E:
							ISO_639_language_code = ""
							for i in range (pos+3,pos+6):
								ISO_639_language_code += data[i]
							ISO_639_language_code = ISO_639_language_code.upper()
							extended_event_description = ""
							if not extended_event_codepage:
								try:
									byte1 = str(ord(data[pos+8]))
								except:
									byte1 = ''
								if byte1=="1": extended_event_codepage = 'iso-8859-5'
								elif byte1=="2": extended_event_codepage = 'iso-8859-6'
								elif byte1=="3": extended_event_codepage = 'iso-8859-7'
								elif byte1=="4": extended_event_codepage = 'iso-8859-8'
								elif byte1=="5": extended_event_codepage = 'iso-8859-9'
								elif byte1=="6": extended_event_codepage = 'iso-8859-10'
								elif byte1=="7": extended_event_codepage = 'iso-8859-11'
								elif byte1=="9": extended_event_codepage = 'iso-8859-13'
								elif byte1=="10": extended_event_codepage = 'iso-8859-14'
								elif byte1=="11": extended_event_codepage = 'iso-8859-15'
								elif byte1=="21": extended_event_codepage = 'utf-8'
								if extended_event_codepage:
									print("[META] Found extended_event encoding-type: " + extended_event_codepage)
							for i in range (pos+8,pos+length):
								if str(ord(data[i]))=="10" or int(str(ord(data[i])))>31:
									extended_event_description += data[i]
							if ISO_639_language_code == lang:
								extended_event_descriptor.append(extended_event_description)
							if (ISO_639_language_code == prev2_ISO_639_language_code) or (prev2_ISO_639_language_code == "x"):
								extended_event_descriptor_multi.append(extended_event_description)
							else:
								extended_event_descriptor_multi.append("\n\n" + extended_event_description)
							prev2_ISO_639_language_code = ISO_639_language_code
						elif rec == 0x50:
							component_descriptor.append(data[pos+8:pos+length])
						elif rec == 0x54:
							content_descriptor.append(data[pos+8:pos+length])
						elif rec == 0x4A:
							linkage_descriptor.append(data[pos+8:pos+length])
						elif rec == 0x55:
							parental_rating_descriptor.append(data[pos+2:pos+length])
						else:
#							print "unsupported descriptor: %x %x" %(rec, pos + 12)
#							print data[pos:pos+length]
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
						extended_event_codepage = short_event_codepage

					if name_event_descriptor:
						try:
							if name_event_codepage:
								if name_event_codepage != 'utf-8':
									name_event_descriptor = name_event_descriptor.decode(name_event_codepage).encode("utf-8")
								else:
									name_event_descriptor.decode('utf-8')
							else:
								encdata = chardet.detect(name_event_descriptor)
								enc = encdata['encoding'].lower()
								confidence = str(encdata['confidence'])
								print("[META] Detected name_event encoding-type: " + enc + " (" + confidence + ")")
								if enc == "utf-8":
									name_event_descriptor.decode(enc)
								else:
									name_event_descriptor = name_event_descriptor.decode(enc).encode('utf-8')
						except (UnicodeDecodeError, AttributeError), e:
							print("[META] Exception in readEitFile: " + str(e))
					self.eit['name'] = name_event_descriptor

					if short_event_descriptor:
						try:
							if short_event_codepage:
								if short_event_codepage != 'utf-8':
									short_event_descriptor = short_event_descriptor.decode(short_event_codepage).encode("utf-8")
								else:
									short_event_descriptor.decode('utf-8')
							else:
								encdata = chardet.detect(short_event_descriptor)
								enc = encdata['encoding'].lower()
								confidence = str(encdata['confidence'])
								print("[META] Detected short_event encoding-type: " + enc + " (" + confidence + ")")
								if enc == "utf-8":
									short_event_descriptor.decode(enc)
								else:
									short_event_descriptor = short_event_descriptor.decode(enc).encode('utf-8')
						except (UnicodeDecodeError, AttributeError), e:
							print("[META] Exception in readEitFile: " + str(e))
					self.eit['short_description'] = short_event_descriptor

					if extended_event_descriptor:
						try:
							if extended_event_codepage:
								if extended_event_codepage != 'utf-8':
									extended_event_descriptor = extended_event_descriptor.decode(extended_event_codepage).encode("utf-8")
								else:
									extended_event_descriptor.decode('utf-8')
							else:
								encdata = chardet.detect(extended_event_descriptor)
								enc = encdata['encoding'].lower()
								confidence = str(encdata['confidence'])
								print("[META] Detected extended_event encoding-type: " + enc + " (" + confidence + ")")
								if enc == "utf-8":
									extended_event_descriptor.decode(enc)
								else:
									extended_event_descriptor = extended_event_descriptor.decode(enc).encode('utf-8')
						except (UnicodeDecodeError, AttributeError), e:
							print("[META] Exception in readEitFile: " + str(e))

						# This will fix EIT data of RTL group with missing line breaks in extended event description
						import re
						extended_event_descriptor = re.sub('((?:Moderat(?:ion:|or(?:in){0,1})|Vorsitz: |Jur(?:isten|y): |G(?:\xC3\xA4|a)st(?:e){0,1}: |Mit (?:Staatsanwalt|Richter(?:in){0,1}|den Schadenregulierern) |Julia Leisch).*?[a-z]+)(\'{0,1}[0-9A-Z\'])', r'\1\n\n\2', extended_event_descriptor)
					self.eit['description'] = extended_event_descriptor

				else:
					# No date clear all
					self.eit = {}

		else:
			# No path or no file clear all
			self.eit = {}


def make_unicode(input):
    if type(input) != unicode:
        input =  input.decode('utf-8')
        return input
    else:
        return input

"""Module docstring.

Read Eit File and show the information.
"""
import sys
import getopt


def readeit(eitfile):
    eitlist=EitList(eitfile)
#    print "\n name: \n";
#    print eitlist.getEitName();
#    print "\n start: \n";
#    print eitlist.getEitStartDate();
#    print "\n desc: \n";
#    print eitlist.getEitDescription();
#    print "\n when: \n";
#    print eitlist.getEitWhen();
#    print "\n starttime: \n";
#    print eitlist.getEitStartTime();
#    print "\n duration: \n";
#    print eitlist.getEitDuration();
    nfoname = eitfile.replace(".eit", ".nfo")
    nfo = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>{0}</title>
  <plot>{1}</plot>
</movie>""".format(eitlist.getEitName(), eitlist.getEitDescription())
    #print nfo
    print nfoname

    with io.open(nfoname,'w',encoding='utf8') as f:
        f.write(make_unicode(nfo))






def main():
    # parse command line options
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help"])
    except getopt.error, msg:
        print msg
        print "for help use --help"
        sys.exit(2)
    # process options
    for o, a in opts:
        if o in ("-h", "--help"):
            print __doc__
            sys.exit(0)
    # process arguments
    for arg in args:
        for root, dirs, files in os.walk(arg):
            for file in files:
                if file.endswith(".eit"):
                    name = os.path.join(root, file)
                    print(name)
                    readeit(name) # process() is defined elsewhere
                    #break

if __name__ == "__main__":
    main()