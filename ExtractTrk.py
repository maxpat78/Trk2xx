# -*- coding: mbcs -*-
import re, sys, os, optparse, tempfile, glob
from ctypes import *
import codecs


__version__ = ('1.11', '2012-10-20')


def GetDOSNameW(pathname):
	"Retrieves the short DOS name from a long one"
	UNC, src = u'\\\\?\\', pathname
	if len(src) > 255:
		src = UNC+os.path.abspath(src)
	dst = c_wchar_p(256*'\0')
	if not windll.kernel32.GetShortPathNameW(src, dst, 256):
		return None
	if UNC in dst.value:
		return dst.value[4:]
	else:
		return dst.value


""" Other interesting ID3 TAG to specify on command line with -metadata:
    "TALB": "album",
    "TBPM": "bpm",
    "TCMP": "compilation", # iTunes extension
    "TCOM": "composer",
    "TCOP": "copyright",
    "TENC": "encodedby",
    "TEXT": "lyricist",
    "TLEN": "length",
    "TMED": "media",
    "TMOO": "mood",
    "TIT2": "title",
    "TIT3": "version",
    "TPE1": "artist",
    "TPE2": "performer", 
    "TPE3": "conductor",
    "TPE4": "arranger",
    "TPOS": "discnumber",
    "TPUB": "organization",
    "TRCK": "tracknumber",
    "TOLY": "author",
    "TSO2": "albumartistsort", # iTunes extension
    "TSOA": "albumsort",
    "TSOC": "composersort", # iTunes extension
    "TSOP": "artistsort",
    "TSOT": "titlesort",
    "TSRC": "isrc",
    "TSST": "discsubtitle",
"""


def mmssff2ms(mm, ss, ff):
	"Converts cue-sheet minutes/seconds/frames into milliseconds"
	return mm*60000 + ss*1000 + int(round(ff/75.0*1000)) # 1 frame = 1/75 sec, 0-based


def ms2hhmmssms(ms):
	"Converts milliseconds into hours, minutes, seconds, milliseconds"
	hh = ms/3600000
	mm = (ms%3600000) / 60000
	ss = (ms-hh*3600000-mm*60000)/1000
	ms = ms - hh*3600000- mm*60000 - ss*1000
	return '%02d:%02d:%02d.%03d' % (hh,mm,ss,ms)

	
def parse_cuesheet(filename, titleparser=None):
	def unquote(s): return '"' + s[1:-1].replace('"', '\\"') + '"'
	catalog = {}
	lastFILE, lastTRK = '', -1
	indexes = []
	trkmeta =  ''
	for line in open(filename):
		r = re.search('TRACK\s+(\d{2})', line, re.I)
		if r:
			trkmeta = ' -metadata TRCK="%s"' % r.group(1)
			continue
		r = re.search('PERFORMER\s+(.+)', line, re.I)
		if r:
			trkmeta += ' -metadata TPE1=%s' % r.group(1)
			continue
		r = re.search('TITLE\s+(.+)', line, re.I)
		if r:
			lastFILE = r.group(1)
			trkmeta += ' -metadata TIT2=%s' % unquote(r.group(1))
			lastTRK += 1
			lastFILE = lastFILE.translate(None, '":?*/\\')
			lastFILE = '%02d %s' % (lastTRK, lastFILE)
			if titleparser:
				lastFILE = titleparser(lastFILE)
		r = re.search('INDEX 01 (\d{2}):(\d{2}):(\d{2})', line, re.I)
		if r:
			mm, ss, ff = map( int, (r.group(1),r.group(2),r.group(3)) )
			indexes += [mmssff2ms(mm,ss,ff)]
			catalog[lastTRK] = [lastFILE, indexes[-1], None, trkmeta] # {tracknum: [name, begin, duration, metadata] } 
	catalog['tracks'] = lastTRK
	indexes +=[5940000]
	track = 0
	for first, next in zip(indexes, indexes[1:]):
		track += 1
		catalog[track][1] = ms2hhmmssms( catalog[track][1] )
		catalog[track][2] = ms2hhmmssms( next-first )
	return catalog


def extract_tracks(image, cue=None, destparser=None, titleparser=None, format='mp3'):
	""" Extracts audio tracks from a compressed image following a cue sheet."""
	src = unicode(image)
	
	if cue == None:
		for ext in ('.cue', '.ape.cue', '.flac.cue', '.wav.cue'):
			cue = os.path.splitext(src)[0] + ext
			if os.path.exists(cue):
				break
	
	src_s = GetDOSNameW(src)
	
	catalog = parse_cuesheet(cue, titleparser)

	# Since ffmpeg is imprecise with compressed formats on durations containing frames, we first convert into WAV
	newimage = tempfile.mktemp(suffix='.wav')
	
	for track in range(0, catalog['tracks']):
		track += 1
		if opts.track_list and track not in opts.track_list:
			continue
		if destparser:
			dest = destparser(src, catalog[track][0])
			try:
				os.makedirs( os.path.dirname(dest) )
			except WindowsError as err:
				if err.winerror == 183:
					pass
				else:
					raise err
		else:
			dest = catalog[track][0]+'.' + format
			
		if os.path.exists(dest):
			continue
			
		# Since ffmpeg is imprecise with compressed formats on durations containing frames, we first convert into WAV
		# (obviously, if we have some tracks to convert *only* !)
		#~ print 'DEBUG: %d:dest=',len(dest),dest
		if not os.path.exists(newimage):
			#~ print 'DEBUG: ffmpeg -i "%s" "%s"' % (src_s, newimage)
			os.system( 'ffmpeg -i "%s" "%s"' % (src_s, newimage))
			
		dest_s = tempfile.mktemp(suffix='.'+format, dir=GetDOSNameW(os.path.dirname(dest)))
		if '.ogg' in dest_s.lower():
			cmd = u'ffmpeg -i "%s" -ss %s -t %s -aq %s %s %s -acodec libvorbis -threads 2 "%s"'
		elif '.oga' in dest_s.lower():
			cmd = u'ffmpeg -i "%s" -ab %s -vn -f ogg -acodec opus -threads 2 -map_metadata 0:g:0 "%s"'
		else:
			cmd = u'ffmpeg -i "%s" -ss %s -t %s -aq %s %s %s "%s"'
		#~ print 'DEBUG:', cmd
		os.system(cmd % (newimage, catalog[track][1], catalog[track][2], opts.quality, opts.cdmeta, catalog[track][3], dest_s))
		os.rename(dest_s, u'\\\\?\\'+os.path.abspath(dest))
		
	if os.path.exists(newimage):
		os.remove(newimage)


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
	x = os.path.join( os.path.dirname(a1), a2+'.'+opts.format_type )
	if opts.dest_dir:
		x = mergepaths(x, opts.dest_dir, opts.preserve)
	return x


if __name__ == '__main__':
	par = optparse.OptionParser(usage="%prog [options] CDImage", description="Extracts audio tracks from a compressed Audio CD image following a CUE sheet.")
	par.add_option("-t", "--type", dest="format_type", help="select an output format (default: mp3)", metavar="FORMAT", default="mp3")
	par.add_option("-q", "--quality", dest="quality", help="select a compression quality (default: 6)", metavar="QUALITY", default="6")
	par.add_option("-d", "--destdir", dest="dest_dir", help="select a destination directory (default=same of source)", metavar="DIR", default=None)
	par.add_option("-p", "--preserve", dest="preserve", help="preserves last N elements from source path (default=1)", metavar="N", type="int", default=1)
	# cdmeta like '-metadata TALB="Album" -metadata TDRL="1988" -metadata TPOS="disk#"'
	par.add_option("-m", "--meta", dest="cdmeta", help="adds common metadata for all the CD tracks", metavar="META", default='')
	par.add_option("-c", "--cue", dest="cue_sheet", help="specify a CUE sheet (default: same name of the CD image)", metavar="CUE", default=None)
	par.add_option("-l", "--list", dest="track_list", help="specify a list of tracks to extract (like: -l 1,3,5-9)", metavar="LIST", default=None)
	opts, args = par.parse_args()

	if len(args) < 1:
		print "You must specify a compressed audio CD image to extract from!"
		par.print_help()
		sys.exit(1)

	if opts.track_list:
		tmp = []
		for x in opts.track_list.split(','):
			if '-' in x:
				x = x.split('-')
				tmp += range(int(x[0]), int(x[1])+1)
			else:
				tmp += [int(x)]
		opts.track_list = tmp
		
	def tparse(s):
		return s.replace("Tchaikovsky ", "")

	def expdirs(base):
		if os.path.isfile(base) and os.path.splitext(base)[-1].lower() in ('.ape', '.flac', '.wav'):
			yield os.path.abspath(base) 
		for root, dirs, files in os.walk(unicode(base)):
			for name in files:
				if os.path.splitext(name)[-1].lower() not in ('.ape', '.flac', '.wav'):
					continue
				yield os.path.abspath( os.path.join(root, name) )
		
	for dirn in expdirs(args[0]):
		extract_tracks(dirn, opts.cue_sheet, destparser=dparse, titleparser=tparse, format=opts.format_type)
