# -*- coding: utf-8 -*

"""utility functions"""

import os
import time
import logging
import select
import subprocess
import pickle
import glob
from datetime import datetime
from functools import update_wrapper
logger = logging.getLogger(__name__)


def decorator(d):
    "Make function d a decorator: d wraps a function fn."
    def _d(fn):
        return update_wrapper(d(fn), fn)
    update_wrapper(_d, d)
    return _d


def get_lockers(locker_pattern):
    """get a locker(s)"""
    # e.g. transfer script: transfer.14-08-18_12-17-55.sh.locker
    return glob.glob(locker_pattern)


def create_locker(locker):
    """create a locker"""
    logger.info('creating {0}'.format(locker))
    touch(locker)


def remove_locker(locker):
    """remove a locker"""
    logger.info('removing {0}'.format(locker))
    os.remove(locker)


def lockit(locker_pattern):
    """
    It creates a locker and prevent the same function from being run again
    before the previous one finishes

    locker_pattern should be composed of locker_path/locker_prefix, an example:
        locker_path/locker_prefix.%y-%m-%d_%H-%M-%S.locker
    """
    @decorator
    def dec(func):
        def deced(*args, **kwargs):
            lockers = get_lockers('{0}*.locker'.format(locker_pattern))
            if len(lockers) >= 1:
                logger.info('The previous {0} run hasn\'t completed yet with '
                            'the following locker(s) found: ({1}). '
                            'Nothing done.'.format(
                                func.__name__, ' '.join(lockers)))
                return
            else:
                now = datetime.now().strftime('%y-%m-%d_%H:%M:%S')
                locker = '{0}.{1}.locker'.format(locker_pattern, now)
                create_locker(locker)
                try:
                    res = func(*args, **kwargs)
                    return res
                except Exception, err:
                    logger.exception(err)
                finally:
                    # TIP: finally guarantees that even when sys.exit(1), the
                    # following block gets run
                    remove_locker(locker)
        return deced
    return dec


@decorator
def timeit(f):
    """time a function, used as decorator"""
    def new_f(*args, **kwargs):
        bt = time.time()
        r = f(*args, **kwargs)
        et = time.time()
        logger.info("time spent on {0}: {1:.2f}s".format(f.func_name, et - bt))
        return r
    return new_f


def backup_file(f):
    """
    Back up a file, old_file will be renamed to #old_file.n#, where n is a
    number incremented each time a backup takes place
    """
    if os.path.exists(f):
        dirname = os.path.dirname(f)
        basename = os.path.basename(f)
        count = 1
        rn_to = os.path.join(
            dirname, '#' + basename + '.{0}#'.format(count))
        while os.path.exists(rn_to):
            count += 1
            rn_to = os.path.join(
                dirname, '#' + basename + '.{0}#'.format(count))
        logger.info("BACKING UP {0} to {1}".format(f, rn_to))
        os.rename(f, rn_to)
        return rn_to


def touch(fname, times=None):
    """
    Similar to nix command, touch, to create an empty file, but also added some
    meta data to the touched file
    """
    with open(fname, 'a') as opf:
        opf.write('created: {0}\n'.format(unicode(datetime.now())))
        opf.write('location of code execution: {0}\n'.format(
            os.path.abspath('.')))
        os.utime(fname, times)


def cache_usable(cache_file, *ref_files):
    """check if cache is still usable"""
    f_cache_usable = True
    if os.path.exists(cache_file):
        logger.info('{0} exists'.format(cache_file))
        if cache_up_to_date(cache_file, *ref_files):
            logger.info('{0} is up to date. '
                        'reading outputs from cache'.format(cache_file))
        else:
            logger.info('{0} is outdated'.format(cache_file))
            f_cache_usable = False
    else:
        logger.info('{0} doesn\'t exist'.format(cache_file))
        f_cache_usable = False
    return f_cache_usable


def cache_up_to_date(cache_file, *ref_files):
    """check if cache is up-to-date"""
    # ctime: e.g. when renaming test.bk to test changes information in
    # inode
    for _ in ref_files:
        if (os.path.getmtime(cache_file) < os.path.getmtime(_) or
            os.path.getctime(cache_file) < os.path.getctime(_)):
            return False
    return True


def gen_sample_msg_id(sample):
    """
    used as an id to identify a particular sample for each logging message
    """
    return '{0} ({2}/{3}) of {1}'.format(
        sample.name, sample.series.name,
        sample.index, sample.series.num_passed_samples())


# def gen_sra_msg_id(sra):
#     sample = sra.sample
#     series = sample.series
#     return '{0} ({1}/{2}) of {3} ({4}/{5}) of {6}'.format(
#         sra.name, sra.index, sample.num_sras(),
#         sample.name, sample.index, series.num_passed_samples(),
#         series.name)

# used a better version of execute as defined in rsempipeline.py --2014-08-13
def execute(cmd, msg_id='', flag_file=None, debug=False):
    """
    This execute doesn't log all stdout, which could look funny, especially
    when it comes to tools like aspc and wget
    """
    logger.info('executing CMD: {0}'.format(cmd))
    if debug:                   # only print out cmd
        return
    try:
        returncode = subprocess.call(cmd, shell=True, executable="/bin/bash")
        if returncode != 0:
            logger.error(
                '{0}, started, but then failed with returncode: {1}. '
                'CMD "{2}"'.format(msg_id, returncode, cmd))
        else:
            logger.info('{0}, execution succeeded with returncode: {1}. '
                        'CMD "{2}"'.format(msg_id, returncode, cmd))
            if flag_file is not None:
                touch(flag_file)
        return returncode
    except OSError, err:
        logger.exception(
            '{0}, failed to start, raising OSError {1}. '
            'CMD: "{2}"'.format(msg_id, err, cmd))


def execute_log_stdout_stderr(cmd, msg_id='', flag_file=None, debug=False):
    """
    This execute logs all stdout and stderr, which could look funny, especially
    when it comes to tools like aspc and wget
    """
    logger.info(cmd)
    if debug:
        return
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, shell=True,
                                executable="/bin/bash")

        # stdout, stderr = [], []
        while True:
            reads = [proc.stdout.fileno(), proc.stderr.fileno()]
            ret = select.select(reads, [], [])

            for fd in ret[0]:
                if fd == proc.stdout.fileno():
                    read = proc.stdout.readline()
                    logger.info('stdout: ' + read.strip())
                    # stdout.append(read)
                if fd == proc.stderr.fileno():
                    read = proc.stderr.readline()
                    logger.info('stderr: ' + read.strip())
                    # stderr.append(read)

            if proc.poll() != None:
                break

        returncode = proc.returncode

        if returncode != 0:
            logger.error(
                '{0}, started, but then failed with returncode: {1}. '
                'CMD "{2}"'.format(msg_id, returncode, cmd))
        else:
            logger.info('{0}, execution succeeded with returncode: {1}. '
                        'CMD "{2}"'.format(msg_id, returncode, cmd))
            if flag_file is not None:
                touch(flag_file)
        return returncode
    except OSError, err:
        logger.exception(
            '{0}, failed to start, raising OSError {1}. '
            'CMD: "{2}"'.format(msg_id, err, cmd))


def gen_completion_stamp(key, stamp_dir):
    """
    @param key: the key to identify the type of stamp. e.g. FASTQ
    @param stamp_dir: where this stamp is to be created
    """
    return os.path.join(stamp_dir, '{0}.COMPLETE'.format(key))


def decide_num_jobs(sample_outdir, j_rsem=None):
    """
    decide num jobs: if j_rsem is specified in the command, use it, else based
    on num of sra files recorded in the pickle file, if not pickle, just return
    1
    """
    if j_rsem is not None:
        return j_rsem
    else:
        pickle_file = os.path.join(sample_outdir, 'orig_sras.pickle')
        if os.path.exists(pickle_file):
            with open(pickle_file) as inf: # a list of sras
                num_jobs = len(pickle.load(inf))
        else:                       # default to 1
            num_jobs = 1
    return num_jobs


def pretty_usage(num):
    """convert file size to a pretty human readable format"""
    # http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    for x in ['bytes', 'KB', 'MB', 'GB']:
        if num < 1024.0 and num > -1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0
    return "%3.1f %s" % (num, 'TB')


def ugly_usage(val):
    """convert human readable disk space to byte"""
    def err(val):
        raise ValueError(
            "Unreadable size: '{0}', make sure it's in the format "
            "of e.g. 1024 Byte|KB|MB|GB|TB (case insensitive)".format(val))
    sv = str(val).split()
    if len(sv) != 2:
        err(val)
    size = float(sv[0])
    unit = sv[1].lower()
    if unit == 'byte':
        return size
    elif unit == 'kb':
        return size * 2 ** 10
    elif unit == 'mb':
        return size * 2 ** 20
    elif unit == 'gb':
        return size * 2 ** 30
    elif unit == 'tb':
        return size * 2 ** 40
    else:
        err(val)


def is_empty_dir(dir_, output):
    """
    test if dir_ is an empty dir based on output. If it's an empty dir, then
    there should be only one item is the list (output)
    """
    return len([_ for _ in output if dir_ in _]) == 1