import tempfile
import re
import subprocess

MTP_SCHEME = 'mtp:'

def read_entries_from_mtp_file(file_id, filename):
    with tempfile.NamedTemporaryFile(suffix=filename) as fd:
        subprocess.check_call(['mtp-getfile', file_id, fd.name])
        entries_from_qif = qif.parse_qif(fd)
    logging.debug('Read %s entries from %s', len(entries_from_qif), filename)
    return entries_from_qif


def get_mtp_files():
    '''list all files on MTP device and return a tuple (file_id, filename) for each file'''

    # using mtp-tools instead of pymtp because I could not get pymtp to work (always got segmentation fault!)
    out = subprocess.check_output('mtp-files 2>&1', shell=True)
    last_file_id = None
    for line in out.splitlines():
        cols = line.strip().split(':', 1)
        if len(cols) == 2:
            key, val = cols
            if key.lower() == 'file id':
                last_file_id = val.strip()
            elif key.lower() == 'filename':
                filename = val.strip()
                yield (last_file_id, filename)


def read_entries_from_mtp(pattern, imported):
    entries = []
    regex = re.compile(pattern)
    for file_id, filename in get_mtp_files():
        if regex.match(filename):
            logging.debug('Found matching file on MTP device: "%s" (ID: %s)', filename, file_id)
            if filename in imported:
                logging.info('Skipping %s (already imported)', filename)
            else:
                entries.extend(read_entries_from_mtp_file(file_id, filename))
                imported.add(filename)
    return entries
