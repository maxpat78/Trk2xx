# -*- coding: mbcs -*-
""" TRK2MP3 converte "sul posto" tutti i file FLAC (o APE o WAV) trovati all'interno della cartella specificata
e delle relative sotto-cartelle. Richiede FFMPEG. """
import sys, os, shutil, tempfile, optparse
from ctypes import *
import codecs

__version__ = (1.12, "2012-10-20")


def GetDOSNameW(pathname):
	"Retrieves the short DOS name from a long one"
	UNC, src = u'\\\\?\\', pathname
	if len(src) > 255 and UNC not in src:
		src = UNC+os.path.abspath(src)
	dst = c_wchar_p(256*'\0')
	if not windll.kernel32.GetShortPathNameW(src, dst, 256):
		return None
	if UNC in dst.value:
		return dst.value[4:]
	else:
		return dst.value


par = optparse.OptionParser(usage="%prog [options] dir1 [dir2...]", description="Converts lossless audio files found in one or more folders into lossy ones.")
par.add_option("-t", "--type", dest="format_type", help="select an output format (default: MP3)", metavar="FORMAT", default=u"mp3")
par.add_option("-q", "--quality", dest="quality", help="select a compression quality (default: 6)", metavar="QUALITY", default="6")
par.add_option("-d", "--destdir", dest="dest_dir", help="select a destination directory (default=same of source)", metavar="DIR", default=None)
par.add_option("-p", "--preserve", dest="preserve", help="preserves last N elements from source path (default=1)", metavar="N", type="int", default=1)
opts, args = par.parse_args()

if len(args) < 1:
	print "You must specify one or more folders with WAV, FLAC or APE files to convert!"
	par.print_help()
	sys.exit(1)


"""
C:/A0/A1/A2/F.x + X:/B0/B1	-->		X:/B0/B1/F.x if preserve == 1
										-->		X:/B0/B1/A2/F.x if preserve == 2
										-->		X:/B0/B1/A1/A2/F.x if preserve == 3, ecc.
"""
def mergepaths(srcpathname, destdir, preserve=1):
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
		file(s,'w')
		name = GetDOSNameW(s)
		os.remove(s)
	else:
		name = GetDOSNameW(s)
	return name
	
	
for dir in args:
	if not os.path.isdir(dir):
		print "WARNING: '%s' is not a valid folder." % dir
		continue
	for root, dirs, files in os.walk(unicode(dir)):
		for name in files:
			if os.path.splitext(name)[-1].lower() not in ('.flac', '.ape', '.wav'):
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
					print dst,
					raise err
					
			dst_s = GenDOSName(dst)
			print dst

			#~ if os.path.exists(path2UNC(dst)):
			# Broken os.path.exists with longest/UNICODE pathnames?
			if GetDOSNameW(dst):
				continue
				
			# Since ffmpeg can't handle long pathnames, encodes from short name to short name, then renames to long one
			if '.ogg' in dst_s.lower():
				cmd = 'ffmpeg -i "%s" -aq %s -vn -acodec libvorbis -threads 2 -map_metadata 0:g:0 "%s"'
			elif '.oga' in dst_s.lower():
				cmd = 'ffmpeg -i "%s" -ab %s -vn -f ogg -acodec opus -threads 2 -map_metadata 0:g:0 "%s"'
			else:
				cmd = 'ffmpeg -i "%s" -aq %s -vn -threads 2 -map_metadata 0:g:0 "%s"'
			
			os.system(cmd % (src_s, opts.quality, dst_s))
			os.rename(dst_s, dst)
