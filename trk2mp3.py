# -*- coding: cp1252 -*-
""" In place conversion of all lossless audio files found in a directory tree. ffmpeg required! """
import sys, os, shutil, tempfile, optparse
from ctypes import *
import codecs

__version__ = (1.19, "2019-09-26") # python3 compatible


def GetDOSNameW(pathname):
	"Retrieves the short DOS name from a long one, using Win32 API"
	UNC, src = u'\\\\?\\', pathname
	if len(src) > 255 and UNC not in src:
		src = UNC+os.path.abspath(src)
	dst = c_wchar_p(256*' ')
	dw = windll.kernel32.GetShortPathNameW(src, dst, 256)
	if not dw:
		return None
	if UNC in dst.value:
		return dst.value[4:dw]
	else:
		return dst.value[:dw]


par = optparse.OptionParser(usage="%prog [options] dir1 [dir2...]", description="Converts lossless audio files found in one or more directories into lossy ones.")
par.add_option("-t", "--type", dest="format_type", help="selects an output format (default: MP3)", metavar="FORMAT", default=u"mp3")
par.add_option("-q", "--quality", dest="quality", help="selects a compression quality (default: 6)", metavar="QUALITY", default="6")
par.add_option("-d", "--destdir", dest="dest_dir", help="selects a destination directory (default=same of source)", metavar="DIR", default=None)
par.add_option("-p", "--preserve", dest="preserve", help="preserves last N elements from source path (default=1, file name only)", metavar="N", type="int", default=1)
opts, args = par.parse_args()

if len(args) < 1:
	print ("You must specify one or more dirs with WAV, FLAC, APE, M4A, ALAC, WV or\nAIF files to convert!\n")
	par.print_help()
	sys.exit(1)


"""
C:/A0/A1/A2/F.x + X:/B0/B1	-->		X:/B0/B1/F.x 		if preserve == 1
							-->		X:/B0/B1/A2/F.x 	if preserve == 2
							-->		X:/B0/B1/A1/A2/F.x 	if preserve == 3, etc. """
def mergepaths(srcpathname, destdir, preserve=1):
	"Merges the source pathname with destination path, eventually preserving source directories"
	srcpathname = srcpathname.replace('\\', '/')
	L = srcpathname.split('/')
	if ':' in L[0]:
		del L[0]
	if preserve > len(L)-1:
		preserve = len(L)-1
	elif preserve < 1:
		preserve = 1
	dest = os.path.join( destdir, '\\'.join(L[-preserve:]) )
	return dest


def dparse(a1, a2):
	x = os.path.join( os.path.dirname(a1), os.path.splitext(os.path.basename(a1))[0]+'.'+opts.format_type )
	if opts.dest_dir:
		x = mergepaths(x, opts.dest_dir, opts.preserve)
	return x


def GenDOSName(s):
	UNC = u'\\\\?\\'
	if len(s) > 255:
		s = UNC+os.path.abspath(s)
	if not os.path.exists(s):
		open(s, 'w')
		name = GetDOSNameW(s)
		os.remove(s)
	else:
		name = GetDOSNameW(s)
	return name


for dir in args:
	if not os.path.isdir(dir):
		print ("WARNING: '%s' is not a valid folder." % dir)
		continue
	for root, dirs, files in os.walk(dir):
		for name in files:
			# Assumes a few extensions as lossless input audio sources
			if os.path.splitext(name)[-1].lower() not in ('.flac', '.ape', '.wav', '.m4a', '.alac', '.wv', '.aif'):
				continue
			src = os.path.abspath( os.path.join(root, name) )
			src_s = GetDOSNameW(src)
			dst = dparse(src, opts.dest_dir)

			try:
				os.makedirs( os.path.dirname(dst) )
			except WindowsError as err:
				if err.winerror == 183:
					pass
				else:
					print (dst,)
					raise err

			dst_s = GenDOSName(dst)

			#~ if os.path.exists(path2UNC(dst)):
			# Broken os.path.exists with longer/UNICODE pathnames?
			if GetDOSNameW(dst):
				continue

			# Since ffmpeg can't handle long pathnames, encodes from short name to short name, then renames to long one
			if '.ogg' in dst_s.lower():
				cmd = 'ffmpeg -i "%s" -aq %s -vn -acodec libvorbis -map_metadata 0:g:0 "%s"'
			elif '.oga' in dst_s.lower():
				if int(opts.quality) < 32000:
					opts.quality = '64000'
				cmd = 'ffmpeg -i "%s" -ab %s -vn -f ogg -acodec opus -map_metadata 0:g:0 "%s"'
			elif '.wma' in dst_s.lower():
				cmd = 'ffmpeg -i "%s" -ab %s -vn -cutoff 18000 -acodec wmav2 -map_metadata 0:g:0 "%s"'
			elif '.m4a' in dst_s.lower():
				cmd = 'ffmpeg -i "%s" -ab %s -vn -acodec aac -map_metadata 0:g:0 "%s"'
			else:
				cmd = 'ffmpeg -i "%s" -aq %s -vn -map_metadata 0:g:0 "%s"'

			print (cmd % (src_s, opts.quality, dst_s))
			os.system(cmd % (src_s, opts.quality, dst_s))
			#~ os.rename(dst_s, '\\\\?\\'+dst) # broken with relative dest folders?
			os.rename(dst_s, dst)
