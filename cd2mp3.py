# -*- coding: utf8 -*-
""" Extracts tracks from an audio image following a CUE sheet and converts them with a pipeline. ffmpeg required! """

# Requires QAAC for HE-AAC output!

# TODO:
# - pass metadata to QAAC
# - optimize image decompression
import re, sys, os, glob, time
import codecs, subprocess, tempfile, datetime
import optparse
from ctypes import *

__version__ = ('1.22', '2020-01-21')


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

def print_timings(start, stop, size):
	print ("Done. %s time elapsed, %.2f Kb/s." % (datetime.timedelta(seconds=int(stop-start)), (size/int(stop-start))/1024.0))

# Associates CUE tags with MP3/OGG/MP4 ones
Tags = {
'mp3': {'TRACK':'TRCK', 'PERFORMER':'TPE1', 'TITLE':'TIT2'},
'ogg': {'TRACK':'TRACKNUMBER', 'PERFORMER':'Artist', 'TITLE':'Title'},
'm4a': {'TRACK':'trkn', 'PERFORMER':'ART', 'TITLE':'nam'}
}

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

def mmssff2bytes(mm, ss, ff):
	"Converts cue-sheet minutes/seconds/frames into an amount of bytes"
	bps = 2*44100*2 # bytes per second, stereo, 16-bit, 44.1 kHz
	return mm*60*bps + ss*bps + 2352*ff # 1 frame = 1/75 sec, 0-based = 2352 bytes

def parse_cuesheet(filename, titleparser=None):
	def unquote(s): return b'"' + s[1:-1].replace(b'"', b'\\"') + b'"'
	catalog = {}
	lastFILE, lastTRK = b'', -1
	indexes = []
	trkmeta =  b''

	for line in open(filename, 'rb'): # treated as binary, since we can't know encoding!
		r = re.search(b'TRACK\s+(\d{2})', line, re.I)
		if r:
			trkmeta = b' -metadata TRCK="%s"' % r.group(1)
			continue
		r = re.search(b'PERFORMER\s+(.+)', line, re.I)
		if r:
			trkmeta += b' -metadata TPE1=%s' % r.group(1)
			continue
		r = re.search(b'TITLE\s+(.+)', line, re.I)
		if r:
			lastFILE = r.group(1)
			trkmeta += b' -metadata TIT2=%s' % unquote(r.group(1))
			lastTRK += 1
			lastFILE = re.sub(b'[\r\n\"\:\?\*\/\\\]', b'', lastFILE)
			lastFILE = b'%02d %s' % (lastTRK, lastFILE)
			lastFILE = force_decode(lastFILE)
			if titleparser:
				lastFILE = titleparser(lastFILE)
		r = re.search(b'INDEX 01 (\d{2}):(\d{2}):(\d{2})', line, re.I)
		if r:
			mm, ss, ff = map( int, (r.group(1),r.group(2),r.group(3)) )
			indexes += [(mm,ss,ff)]
			catalog[lastTRK] = [lastFILE, indexes[-1], None, force_decode(trkmeta)] # {tracknum: [name, begin, duration, metadata] } 
	catalog['tracks'] = lastTRK
	indexes +=[(120,00,00)]
	track = 0
	for first, next in zip(indexes, indexes[1:]):
		track += 1
		p0 = mmssff2bytes(*first)
		p1 = mmssff2bytes(*next)
		catalog[track][1] = p0 # start byte in the stream
		catalog[track][2] = p1-p0 # length
	return catalog


def extract_tracks(image, cue=None, destparser=None, titleparser=None, format='mp3'):
	""" Extracts audio tracks from a compressed image following a cue sheet."""
	src = image
	
	if cue == None:
		for ext in ('.cue', '.ape.cue', '.flac.cue', '.wav.cue'):
			cue = os.path.splitext(src)[0] + ext
			if os.path.exists(cue):
				break
	
	src_s = GetDOSNameW(src)
	
	catalog = parse_cuesheet(GetDOSNameW(cue), titleparser)

	print ('Transcoding "%s" in %s' % (src, format.upper()))

	# Opens a PIPE to read FFmpeg RAW output
	proc = subprocess.Popen('ffmpeg -v quiet -i "%s" -f s16le -ar 44100 -' % src_s, stdout=subprocess.PIPE)

	StartTime = time.time()
	TotalBytes = 0

	if format in ('ogg', 'oga', 'vorbis', 'opus'):
		ext = '.oga'
	elif format in ('aac', 'he-aac', 'm4a', 'aacplus'):
		ext = '.m4a'
	else:
		ext = '.'+format
	
	for track in range(0, catalog['tracks']):
		track += 1
		if opts.track_list and track not in opts.track_list:
			todo = catalog[track][2]
			while todo > 0:
				buf = proc.stdout.read( min(176400,todo) )
				if not buf: break
				todo -= len(buf)
				TotalBytes += len(buf)
			continue
		if destparser:
			dest = destparser(src, catalog[track][0]+ext)
			try:
				os.makedirs( os.path.dirname(dest) )
			except WindowsError as err:
				if err.winerror == 183:
					pass
				else:
					raise err
		else:
			dest = catalog[track][0] + ext
			
		# FLAW: it decodes even if all tracks are done!
		if os.path.exists(dest):
			todo = catalog[track][2]
			while todo > 0:
				buf = proc.stdout.read( min(176400,todo) )
				if not buf: break
				todo -= len(buf)
				TotalBytes += len(buf)
			continue
		
		format = format.lower()

		dest_s = tempfile.mktemp(suffix=ext, dir=GetDOSNameW(os.path.dirname(dest)))
		
		opts.qswitch = '-aq'
		opts.extra = ''
		opts.use_qaac = False
		opts.sleep = 0.5
		
		if format == 'vorbis':
			opts.extra = '-acodec libvorbis'
		elif format == 'opus':
			opts.qswitch = '-ab'
			opts.extra = '-acodec opus -f ogg'
			if int(opts.quality) < 32000:
				opts.quality = '64000'
		elif format == 'wma':
			opts.qswitch = '-ab'
			opts.extra = '-acodec wmav2 -f asf -cutoff 18000'
		elif format in ('he-aac', 'aacplus'):
			opts.use_qaac = True
			opts.sleep = 1
			opts.qswitch = '-a'
			opts.extra = '-s'
			if format in ('he-aac', 'aacplus'):
				opts.extra += ' --he'
				if int(opts.quality) < 32:
					opts.quality = 64 # defaults ABR 64 kbit/s for HE-AAC
			if int(opts.quality) < 32:
				opts.quality = 128 # defaults ABR 128 kbit/s for AAC-LC

		print ('Track %d/%d: "%s"' % (track, len(catalog)-1, catalog[track][0]))

		if not opts.use_qaac:
			cmdline = 'ffmpeg -v error -f s16le -ar 44100 -ac 2 -i - %s %s %s %s %s "%s"' % (opts.qswitch, opts.quality, opts.extra, opts.cdmeta, catalog[track][3], dest_s)
			proc_out = subprocess.Popen(cmdline, stdin=subprocess.PIPE, stderr=None)
		else:
			proc_out = subprocess.Popen('qaac --threading --raw %s %s %s -o "%s" -' % (opts.qswitch, opts.quality, opts.extra, dest_s), stdin=subprocess.PIPE, stderr=None)

		todo = catalog[track][2]
		while todo > 0:
			buf = proc.stdout.read( min(176400,todo) )
			if not buf: break
			proc_out.stdin.write(buf)
			todo -= len(buf)
			TotalBytes += len(buf)
			sys.stdout.write('%d%% done\r' % (100-todo*100/catalog[track][2]))

		proc_out.stdin.close()
		time.sleep(opts.sleep) # Wait for FFmpeg to close the output handle
		proc_out.kill()
		done=0
		for i in range(5):
			if done: break
			time.sleep(opts.sleep) # Wait for FFmpeg to close the output handle
			try:
				os.rename(dest_s, u'\\\\?\\'+os.path.abspath(dest))
			except WindowsError:
				print('Error renaming from "%s" to "%s"!' % (dest_s, dest))
				pass
			done = 1
			
	
	proc.kill()
	StopTime = time.time()
	print_timings(StartTime, StopTime, TotalBytes)
		

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
	x = os.path.join( os.path.dirname(a1), a2 )
	if opts.dest_dir:
		x = mergepaths(x, opts.dest_dir, opts.preserve)
	return x


def force_decode(s, enc=['utf8', 'cp1252', 'mbcs']):
	for i in enc:
		try:
			return s.decode(i)
		except UnicodeDecodeError:
			pass



if __name__ == '__main__':
	par = optparse.OptionParser(usage="%prog [options] CDImage", description="Extracts audio tracks from a compressed Audio CD image following a CUE sheet.")
	par.add_option("-t", "--type", dest="format_type", help="selects an output format (default: mp3)", metavar="FORMAT", default="mp3")
	par.add_option("-q", "--quality", dest="quality", help="selects a compression quality (default: 6)", metavar="QUALITY", default="6")
	par.add_option("-d", "--destdir", dest="dest_dir", help="selects a destination directory (default=same of source)", metavar="DIR", default=None)
	par.add_option("-p", "--preserve", dest="preserve", help="preserves last N elements from source path (default=1)", metavar="N", type="int", default=1)
	# cdmeta like '-metadata TALB="Album" -metadata TDRL="1988" -metadata TPOS="disk#"'
	par.add_option("-m", "--meta", dest="cdmeta", help="adds common metadata for all the CD tracks", metavar="META", default='')
	par.add_option("-c", "--cue", dest="cue_sheet", help="specifies a CUE sheet (default: same name of the CD image)", metavar="CUE", default=None)
	par.add_option("-l", "--list", dest="track_list", help="specifies a list of tracks to extract (like: -l 1,3,5-9)", metavar="LIST", default=None)
	opts, args = par.parse_args()

	if len(args) < 1:
		print ("You must specify a compressed audio CD image to extract from!")
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
		"Template function callable by extract_tracks to carry additional parsing on track title string"
		return s

	def expdirs(base):
		if os.path.isfile(base) and os.path.splitext(base)[-1].lower() in ('.ape', '.flac', '.wav'):
			yield os.path.abspath(base) 
		for root, dirs, files in os.walk(base):
			for name in files:
				if os.path.splitext(name)[-1].lower() not in ('.ape', '.flac', '.wav'):
					continue
				yield os.path.abspath( os.path.join(root, name) )
		
	for dirn in expdirs(args[0]):
		extract_tracks(dirn, opts.cue_sheet, destparser=dparse, titleparser=tparse, format=opts.format_type)
