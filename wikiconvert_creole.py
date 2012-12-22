#!/usr/bin/env python

"""
Usage:
    python googlecode2github/wikiconfig.py PROJID SRCDIR DSTDIR

where "PROJID" is the github project id, e.g. "trentm/python-markdown2",
"SRCDIR" is a Google Code project wiki Subversion working copy dir and
"DSTDIR" is the git clone dir of the git project's wiki.
"""

__version__ = "1.0.0"

import re
import sys
from os.path import *
from glob import glob
from pprint import pprint
import codecs
from hashlib import md5


def log(s):
    sys.stderr.write(s+"\n")

def convert_dir(proj_id, src_dir, dst_dir):
    if isfile(src_dir):
        convert_file(proj_id, src_dir, dst_dir)
    else:
        for f in glob(join(src_dir, "*.wiki")):
            convert_file(proj_id, f, dst_dir)
    
def convert_file(proj_id, src_path, dst_dir):
    src = codecs.open(src_path, 'r', 'utf-8').read()
    meta_lines = []
    body_lines = []
    lines = src.splitlines(False)
    for i, line in enumerate(lines):
        if line.startswith("#"):
            meta_lines.append(line)
        else:
            assert not line.strip(), "line isn't empty in file %s %r" % (src_path, line)
            # TODO is it actually mandtory that a blank line separate meta text from body text?
            body_lines = lines[i+1:]
            break
    meta = {}
    for line in meta_lines:
        k,v = line[1:].split(None, 1)
        meta[k] = v
    text = '\n'.join(body_lines)
    s_from_hash = {}

    # Pull out pre-blocks so we can restore them unmunged
    def sub_block(match,indent=True):
        pre = match.group(1)
        hash = md5(pre.encode('utf8')).hexdigest()
        s_from_hash[hash] = _indent(pre) if indent else pre
        return hash
        
    def sub_pre_block(match):
        return sub_block(match,indent=True)

    text = re.compile(r'^{{{(.*?)}}}', re.M|re.S).sub(sub_pre_block, text)

    #  Pull out `backtick` code quotes 
    #def sub_code(match)
     #   return sub_block(match,indent=False)
    text = re.compile(r'`(.*?)`', re.M|re.S).sub(r'##{{{\1}}}##', text) # monospace literal for Creole 
    
    # Headings - No conversion needed for Creole. 

    # Tables
    def sub_table_creole(m):
        rows = []
        for line in m.group(0).splitlines(False):
            if not line.strip():
                continue
            rows.append(list(c.strip() for c in line.split("||")[1:-1]))
        lines = []
        # Assume first row is a header (or should we assume the reverse?)
        if rows:
            lines.append('|='+'|='.join(rows[0])+'|')
            for row in rows[1:]:
                lines.append('|'+'|'.join(row)+'|')
            return '\n\n' + '\n'.join(lines)
    text = re.compile(r'\n(\n^\|\|(.*?\|\|)+$)+', re.M).sub(sub_table_creole, text)

    # Lists (doesn't handle nested lists - flattens structure).
    text = re.compile(r'^[ \t]+\*[ \t]+(.*?)$', re.M).sub(r'{^} \1', text) # temp marker to avoid bold processing
    text = re.compile(r'^[ \t]+#[ \t]+(.*?)$', re.M).sub(r'1. \1', text)

    # Italics, bold. - same for both Markdown & Creole
    # in*ter*bold: (?<=\w)(\*\w+?\*)(?=\w)
    text = re.compile(r'(?<![*\w])\*([^*]+?)\*(?![*\w])', re.S).sub(r'**\1**', text)
    text = re.compile(r'(?<![_\w])_([^_]+?)_(?![_\w])', re.S).sub(r'*\1*', text)

    # Swap our temporary bulllet marker back out
    text = text.replace('{^}','*')

    # wiki links. - Creole & Markdown are the same - no change required to conversion
    def sub_wikilink(m):
        gh_page_name = _gh_page_name_from_gc_page_name(m.group(1)).replace('-', ' ')
        if m.group(2):
            s = "[[%s|%s]]" % (gh_page_name, m.group(2))
            pass
        else:
            s = "[[%s]]" % gh_page_name
        hash = md5(s.encode('utf8')).hexdigest()
        s_from_hash[hash] = s
        return hash
    text = re.compile(r'\[((?:[A-Z][a-z]+)+)(?:\s+(.*?))?\]', re.S).sub(sub_wikilink, text)

    # Links
    def sub_link(m):
        # s = "[%s](%s)" % (m.group(2), m.group(1)) # Markdown
        s = "[[%s|%s]]" % (m.group(2), m.group(1)) # Creole
        hash = md5(s.encode('utf8')).hexdigest()
        s_from_hash[hash] = s
        return hash
    # NOTE: this only matches http & ftp links currently
    text = re.compile(r'(?<!\[)\[((?:http|ftp):[^\s]+)\s+(.*?)\](?!\])', re.S).sub(sub_link, text)

    # Auto-linking "issue \d+"
    # TODO: Construct Google Code -> Github issue lookup map
    text = re.compile(r'(?<!\[)(issue (\d+))(?!\])').sub(
        r'[\1](https://github.com/%s/issues#issue/\2)' % proj_id, text)

    # Restore hashed-out blocks.
    for hash, s in s_from_hash.items():
        if text == text.replace(hash,s):
            print 'Contained = ',text.find(hash)
            print 'Failed to replace %s with %s' % (hash,s)
        text = text.replace(hash, s)
 
    #  Prepend summary.(not sure whether h3 or italics is best option here)
    if "summary" in meta:
        text = ("//%s//\n\n" % meta["summary"]) + text

    # Project specific replacements for naming, mailing lists, & code
    text = text.replace('Google Refine','OpenRefine')
    text = text.replace(
                    'http://groups.google.com/group/google-refine',
                     'http://groups.google.com/group/openrefine')
    text = text.replace(
                        'code.google.com/p/google-refine/source/browse/trunk/',
                        'github.com/OpenRefine/OpenRefine/blob/master/')

    base = splitext(basename(src_path))[0]
    gh_page_name = _gh_page_name_from_gc_page_name(base)
#    dst_path = join(dst_dir, gh_page_name+".md")
    dst_path = join(dst_dir, gh_page_name+".creole")
    if not exists(dst_path) or codecs.open(dst_path, 'r', 'utf-8').read() != text:
        codecs.open(dst_path, 'w', 'utf-8').write(text)
        log("wrote '%s'" % dst_path)


#---- internal support stuff

def _indent(text):
    return '    ' + '\n    '.join(text.splitlines(False))

def _gh_page_name_from_gc_page_name(gc):
    """Github (gh) Wiki page name from Google Code (gc) Wiki page name."""
    if re.match(r'[A-Z][a-z]{2,}',gc):
        gh = re.sub(r'([A-Z][a-z]+)', r'-\1', gc)[1:]
    else:
        gh = gc
    return gh

#---- mainline

if __name__ == '__main__':
    convert_dir("OpenRefine/OpenRefine", "c:/users/tfmorris/tmp/grefine-wiki", "c:/users/tfmorris/tmp/orefine-wiki")
    if len(sys.argv) != 4:
        print __doc__
        sys.exit(1)
    convert_dir(sys.argv[1], sys.argv[2], sys.argv[3])
