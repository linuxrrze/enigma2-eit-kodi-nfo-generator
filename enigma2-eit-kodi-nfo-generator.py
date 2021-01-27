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
    if ' object at ' in str(obj) and '__type__' not in newobj:
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
#       for bit in range(7,-1,-1):  # MSB to LSB
#           z32 = crc>>31    # top bit
#           crc = crc << 1
#           if ((byte>>bit)&1) ^ z32:
#               crc = crc ^ poly
#           crc = crc & 0xffffffffL
#   return crc

decoding_charSpecHR = {'Ć': '\u0106', 'æ': '\u0107', '®': '\u017D', '¾': '\u017E', '©': '\u0160', '¹': '\u0161', 'Č': '\u010C', 'è': '\u010D', 'ð': '\u0111'}

decoding_charSpecCZSK = {'Ï'+'C': 'Č','Ï'+'E': 'Ě','Ï'+'L': 'Ľ','Ï'+'N': 'Ň','Ï'+'R': 'Ř','Ï'+'S': 'Š','Ï'+'T': 'Ť','Ï'+'Z': 'Ž','Ï'+'c': 'č','Ï'+'d': 'ď','Ï'+'e': 'ě','Ï'+'l': 'ľ', 'Ï'+'n': 'ň',
'Ï'+'r': 'ř','Ï'+'s': 'š','Ï'+'t': 'ť','Ï'+'z': 'ž','Ï'+'D': 'Ď','Â'+'A': 'Á','Â'+'E': 'É','Â'+'I': 'Í','Â'+'O': 'Ó','Â'+'U': 'Ú','Â'+'a': 'á','Â'+'e': 'é','Â'+'i': 'í','Â'+'o': 'ó',
'Â'+'u': 'ú','Â'+'y': 'ý','Ã'+'o': 'ô','Ã'+'O': 'Ô','Ê'+'u': 'ů','Ê'+'U': 'Ů','È'+'A': 'Ä','È'+'E': 'Ë','È'+'I': 'Ï','È'+'O': 'Ö','È'+'U': 'Ü','È'+'Y': 'Ÿ','È'+'a': 'ä','È'+'e': 'ë',
'È'+'i': 'ï','È'+'o': 'ö','È'+'u': 'ü','È'+'y': 'ÿ'}

def convertCharSpecHR(text):
    for i, j in decoding_charSpecHR.items():
        text = text.replace(i, j)
    return text

def convertCharSpecCZSK(text):
    for i, j in decoding_charSpecCZSK.items():
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
        for alpha, name in list(LanguageCodes.items()):
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
				except Exception as e:
					print(("[META] Exception in readEitFile: " + str(e)))
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
						rec = data[pos]
						if pos+1>=endpos:
							break
						length = data[pos+1] + 2
						if rec == 0x4D:
							descriptor_tag = data[pos+1]
							descriptor_length = data[pos+2]
							ISO_639_language_code = str(data[pos+2:pos+5]).upper()
							event_name_length = data[pos+5]
							name_event_description = ""
							for i in range (pos+6,pos+6+event_name_length):
								if str(data[i])=="10" or int(str(data[i]))>31:
									name_event_description += chr(data[i])
							if not name_event_codepage:
								try:
									byte1 = str(data[pos+6])
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
									print(("[META] Found name_event encoding-type: " + name_event_codepage))
							short_event_description = ""
							if not short_event_codepage:
								try:
									byte1 = str(data[pos+7+event_name_length])
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
									print(("[META] Found short_event encoding-type: " + short_event_codepage))
							for i in range (pos+7+event_name_length,pos+length):
								if str(data[i])=="10" or int(str(data[i]))>31:
									short_event_description += chr(data[i])
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
								ISO_639_language_code += chr(data[i])
							ISO_639_language_code = ISO_639_language_code.upper()
							extended_event_description = ""
							if not extended_event_codepage:
								try:
									byte1 = str(data[pos+8])
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
									print(("[META] Found extended_event encoding-type: " + extended_event_codepage))
							for i in range (pos+8,pos+length):
								if str(data[i])=="10" or int(str(data[i]))>31:
									extended_event_description += chr(data[i])
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
									name_event_descriptor = bytes(name_event_descriptor, 'utf-8').decode(name_event_codepage)
							else:
								encdata = chardet.detect(bytes(name_event_descriptor, utf-8))
								enc = encdata['encoding'].lower()
								confidence = str(encdata['confidence'])
								print(("[META] Detected name_event encoding-type: " + enc + " (" + confidence + ")"))
								if enc != "utf-8":
									name_event_descriptor = bytes(name_event_descriptor, 'uts-8').decode(enc)
						except (UnicodeDecodeError, AttributeError) as e:
							print(("[META] Exception in readEitFile: " + str(e)))
					self.eit['name'] = name_event_descriptor

					if short_event_descriptor:
						try:
							# if we read this as utf-8 incorrectly change it
							if short_event_codepage:
								if short_event_codepage != 'utf-8':
									short_event_descriptor = bytes(short_event_descriptor, 'utf-8').decode(short_event_codepage)
							else:
								encdata = chardet.detect(bytes(short_event_descriptor, 'utf-8'))
								enc = encdata['encoding'].lower()
								confidence = str(encdata['confidence'])
								print(("[META] Detected short_event encoding-type: " + enc + " (" + confidence + ")"))
								if enc != "utf-8":
									short_event_descriptor = bytes(short_event_descriptor, 'uts-8').decode(enc)
						except (UnicodeDecodeError, AttributeError) as e:
							print(("[META] Exception in readEitFile: " + str(e)))
					self.eit['short_description'] = short_event_descriptor

					if extended_event_descriptor:
						try:
							# if we read this as utf-8 incorrectly change it
							if extended_event_codepage:
								if extended_event_codepage != 'utf-8':
									extended_event_descriptor = bytes(extended_event_descriptor, 'utf-8').decode(extended_event_codepage)
							else:
								encdata = chardet.detect(bytes(extended_event_descriptor, 'utf-8'))
								enc = encdata['encoding'].lower()
								confidence = str(encdata['confidence'])
								print(("[META] Detected extended_event encoding-type: " + enc + " (" + confidence + ")"))
								if enc != "utf-8":
									extended_event_descriptor = bytes(extended_event_descriptor, 'utf-8').decode(enc)
						except (UnicodeDecodeError, AttributeError) as e:
							print(("[META] Exception in readEitFile: " + str(e)))

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
    if type(input) != str:
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
    print(nfoname)

    with io.open(nfoname,'w',encoding='utf8') as f:
        f.write(make_unicode(nfo))





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
                    readeit(name) # process() is defined elsewhere
                    #break

if __name__ == "__main__":
    main()