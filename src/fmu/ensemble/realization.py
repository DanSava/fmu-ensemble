# -*- coding: utf-8 -*-
"""Implementation of realization classes

A realization is a set of results from one subsurface model
realization. A realization can be either defined from
its output files from the FMU run on the file system,
it can be computed from other realizations, or it can be
an archived realization.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import re
import glob
import json
import pandas as pd

import ert.ecl
from fmu import config

fmux = config.etc.Interaction()
logger = fmux.basiclogger(__name__)

if not fmux.testsetup():
    raise SystemExit()


class ScratchRealization(object):
    r"""A representation of results still present on disk

    ScratchRealization's point to the filesystem for their
    contents.

    A realization must at least contain a STATUS file.
    Additionally, jobs.json and parameters.txt will be attempted
    loaded by default.

    The realization is defined by the pointers to the filesystem.
    When asked for, this object will return data from the
    filesystem (or from cache if already computed).

    The files dataframe is the central filesystem pointer
    repository for the object. It will at least contain
    the columns
    * FULLPATH absolute path to a file
    * FILETYPE filename extension (after last dot)
    * LOCALPATH relative filename inside realization diretory
    * BASENAME filename only. No path. Includes extension

    This dataframe is available as a read-only property from the object

    Args:
        path (str): absolute or relative path to a directory
            containing a realizations files.
        realidxregexp: a compiled regular expression which
            is used to determine the realization index (integer)
            from the path. First match is the index.
            Default: realization-(\d+)
    """
    def __init__(self, path,
                 realidxregexp=re.compile(r'.*realization-(\d+)')):
        self._origpath = path

        self.files = pd.DataFrame(columns=['FULLPATH', 'FILETYPE',
                                           'LOCALPATH', 'BASENAME'])
        self._eclsum = None  # Placeholder for caching

        self.keyvaluedata = {} # dict of dicts with any kind of data.

        abspath = os.path.abspath(path)
        realidxmatch = re.match(realidxregexp, abspath)
        if realidxmatch:
            self.index = int(realidxmatch.group(1))
        else:
            logger.warn('Realization %s not valid, skipping',
                        abspath)
            raise ValueError

        # Now look for a minimal subset of files
        if os.path.exists(os.path.join(abspath, 'STATUS')):
            filerow = {'LOCALPATH': 'STATUS',
                       'FILETYPE': 'STATUS',
                       'FULLPATH': os.path.join(abspath, 'STATUS'),
                       'BASENAME': 'STATUS'}
            self.files = self.files.append(filerow, ignore_index=True)
        else:
            logger.warn("Invalid realization, no STATUS file, %s",
                        abspath)
            raise ValueError

        if os.path.exists(os.path.join(abspath, 'jobs.json')):
            filerow = {'LOCALPATH': 'jobs.json',
                       'FILETYPE': 'json',
                       'FULLPATH': os.path.join(abspath, 'jobs.json'),
                       'BASENAME': 'jobs.json'}
            self.files = self.files.append(filerow, ignore_index=True)

        self.from_txt('parameters.txt')

    def from_txt(self, localpath, convert_numeric=True,
                 force_reread=False):
        """Parse a txt file with
        <key> <value>
        in each line.

        The txt file will be internalized in a dict and will be
        stored if the object is archived. Recommended file
        extension is 'txt'.
        
        Common usage is internalization of parameters.txt which
        happens by default, but this can be used for all txt files.

        The parsed data is returned as a dict. At the ensemble level
        the same function returns a dataframe.

        There is no get'er for the constructed data, access the 
        class variable keyvaluedata directly, or rerun this function.
        (except for parameters.txt, for which there is a property
        called 'parameters')

        Args:
            localpath: path local the realization to the txt file
            convert_numeric: defaults to True, will try to parse
                all values as integers, if not, then floats, and
                strings as the last resort.
            force_reread: Force reread from file system. If
                False, repeated calls to this function will
                returned cached results.

        Returns:
            dict with the parsed values. Values will be returned as
                integers, floats or strings. If convert_numeric
                is False, all values are strings.
        """
        fullpath = os.path.join(self._origpath, localpath)
        if not os.path.exists(fullpath):
            raise IOError("File not found: " + localpath)
        else:
            if fullpath in self.files['FULLPATH'].values and force_reread == False:
                return self.keyvaluedata[localpath]
            elif fullpath not in self.files['FULLPATH'].values:
                filerow = {'LOCALPATH': localpath,
                           'FILETYPE': localpath.split('.')[-1],
                           'FULLPATH': fullpath,
                           'BASENAME': os.path.split(localpath)[-1]}
                self.files = self.files.append(filerow, ignore_index=True)
            keyvalues = pd.read_table(fullpath, sep=r'\s+',
                                      index_col=0, dtype=str,
                                      header=None)[1].to_dict()
            if convert_numeric:
                for key in keyvalues:
                    keyvalues[key] = parse_number(keyvalues[key])
            self.keyvaluedata[localpath] = keyvalues
            return keyvalues

    def get_status(self):
        """Collects the contents of the STATUS files and return
        as a dataframe, with information from jobs.json added if
        available.

        Each row in the dataframe is a finished FORWARD_MODEL
        The STATUS files are parsed and information is extracted.
        Job duration is calculated, but jobs above 24 hours
        get incorrect durations.

        Returns:
            A dataframe with information from the STATUS files.
            Each row represents one job in one of the realizations.
        """
        from datetime import datetime, date, time
        statusfile = os.path.join(self._origpath, 'STATUS')
        if not os.path.exists(statusfile):
            # This should not happen as long as __init__ requires STATUS
            # to be present.
            return pd.DataFrame()  # will be empty
        status = pd.read_table(statusfile, sep=r'\s+', skiprows=1,
                               header=None,
                               names=['FORWARD_MODEL', 'colon',
                                      'STARTTIME', 'dots', 'ENDTIME'],
                               engine='python')
        # Delete potential unwanted row
        status = status[~ ((status.FORWARD_MODEL == 'LSF') &
                           (status.colon == 'JOBID:'))]
        status.reset_index(inplace=True)
        del status['colon']
        del status['dots']
        # Index the jobs, this makes it possible to match with jobs.json:
        status['JOBINDEX'] = status.index.astype(int)
        # Calculate duration. Only Python 3.6 has time.fromisoformat().
        # Warning: Unpandaic code..
        durations = []
        for _, jobrow in status.iterrows():
            hms = map(int, jobrow['STARTTIME'].split(':'))
            start = datetime.combine(date.today(),
                                     time(hour=hms[0], minute=hms[1],
                                          second=hms[2]))
            hms = map(int, jobrow['ENDTIME'].split(':'))
            end = datetime.combine(date.today(),
                                   time(hour=hms[0], minute=hms[1],
                                        second=hms[2]))
            # This works also when we have crossed 00:00:00.
            # Jobs > 24 h will be wrong.
            durations.append((end - start).seconds)
        status['DURATION'] = durations

        # Augment data from jobs.json if that file is available:
        jsonfilename = os.path.join(self._origpath, 'jobs.json')
        if jsonfilename and os.path.exists(jsonfilename):
            try:
                jobsinfo = json.load(open(jsonfilename))
                jobsinfodf = pd.DataFrame(jobsinfo['jobList'])
                jobsinfodf['JOBINDEX'] = jobsinfodf.index.astype(int)
                # Outer merge means that we will also have jobs from
                # jobs.json that has not started (failed or perhaps
                # the jobs are still running on the cluster)
                status = status.merge(jobsinfodf, how='outer',
                                      on='JOBINDEX')
            except ValueError:
                logger.warn("Parsing file %s failed, skipping",
                            jsonfilename)
        status.sort_values(['JOBINDEX'], ascending=True,
                           inplace=True)
        return status

    def find_files(self, paths, metadata=None):
        """Discover realization files. The files dataframe
        will be updated.

        Certain functionality requires up-front file discovery,
        e.g. ensemble archiving and ensemble arithmetic.

        CSV files for single use does not have to be discovered.

        Args:
            paths: str or list of str with filenames (will be globbed)
                that are relative to the realization directory.
            metadata: dict with metadata to assign for the discovered
                files. The keys will be columns, and its values will be
                assigned as column values for the discovered files.
        """
        if isinstance(paths, str):
            paths = [paths]
        for searchpath in paths:
            globs = glob.glob(os.path.join(self._origpath, searchpath))
            for match in globs:
                filerow = {'LOCALPATH': os.path.relpath(match, self._origpath),
                           'FILETYPE': match.split('.')[-1],
                           'FULLPATH': match,
                           'BASENAME': os.path.basename(match)}
                # Delete this row if it already exists, determined by FULLPATH
                if match in self.files.FULLPATH.values:
                    self.files = self.files[self.files.FULLPATH != match]
                if metadata:
                    filerow.update(metadata)
                # Issue: Solve when file is discovered multiple times.
                self.files = self.files.append(filerow, ignore_index=True)

    def get_csv(self, filename):
        """Load a CSV file as a DataFrame

        Filename is relative to realization root.

        Returns:
            dataframe: The CSV file loaded. Empty dataframe
                if file is not present.
        """
        absfilename = os.path.join(self._origpath, filename)
        if os.path.exists(absfilename):
            return pd.read_csv(absfilename)
        return pd.DataFrame()

    @property
    def parameters(self):
        """Access the data obtained from parameters.tx2t

        Returns:
            dict with data from parameters.txt
        """
        return self.keyvaluedata['parameters.txt']

    def get_eclsum(self):
        """
        Fetch the Eclipse Summary file from the realization
        and return as a libecl EclSum object

        Unless the UNSMRY file has been discovered, it will
        pick the file from the glob eclipse/model/*UNSMRY

        Warning: If you have multiple UNSMRY files and have not
        performed explicit discovery, this function will
        not help you (yet).

        Returns:
           EclSum: object representing the summary file
        """
        if self._eclsum:  # Return cached object if available
            return self._eclsum

        unsmry_file_row = self.files[self.files.FILETYPE == 'UNSMRY']
        unsmry_filename = None
        if len(unsmry_file_row) == 1:
            unsmry_filename = unsmry_file_row.FULLPATH.values[0]
        else:
            unsmry_fileguess = os.path.join(self._origpath, 'eclipse/model',
                                            '*.UNSMRY')
            unsmry_filename = glob.glob(unsmry_fileguess)[0]
        if not os.path.exists(unsmry_filename):
            return None
        # Cache result
        self._eclsum = ert.ecl.EclSum(unsmry_filename)
        return self._eclsum

    def get_smry(self, time_index=None, column_keys=None):
        """Return the Eclipse summary data from the realization

        Convenience wrapper for ert.ecl.EclSum.pandas_frame()

        Args:
            time_index: list of DateTime if interpolation is wanted
               default is None, which returns the raw Eclipse report times
            column_keys: list of column key wildcards.

        Returns:
            DataFrame with summary keys as columns and dates as indices
        """
        return self.get_eclsum().pandas_frame(time_index, column_keys)

    def get_smryvalues(self, props_wildcard=None):
        """
        Fetch selected vectors from Eclipse Summary data.

        Args:
            props_wildcard : string or list of strings with vector
                wildcards
        Returns:
            a dataframe with values. Raw times from UNSMRY.
            Empty dataframe if no summary file data available
        """
        if not self._eclsum:  # check if it is cached
            self.get_eclsum()

        if not self._eclsum:
            return pd.DataFrame()

        if not props_wildcard:
            props_wildcard = [None]
        if isinstance(props_wildcard, str):
            props_wildcard = [props_wildcard]
        props = set()
        for prop in props_wildcard:
            props = props.union(set(self._eclsum.keys(prop)))
        if 'numpy_vector' in dir(self._eclsum):
            data = {prop: self._eclsum.numpy_vector(prop, report_only=False)
                    for prop in props}
        else:  # get_values() is deprecated in newer libecl
            data = {prop: self._eclsum.get_values(prop, report_only=False) for
                    prop in props}
        dates = self._eclsum.get_dates(report_only=False)
        return pd.DataFrame(data=data, index=dates)

    def __repr__(self):
        """Represent the realization. Show only the last part of the path"""
        pathsummary = self._origpath[-50:]
        return "<Realization, index={}, path=...{}>".format(self.index,
                                                            pathsummary)


def parse_number(value):
    """Try to parse the string first as an integer, then as float,
    if both fails, return the original string.

    Caveats: Know your Python numbers:
    https://stackoverflow.com/questions/379906/how-do-i-parse-a-string-to-a-float-or-int-in-python

    Beware, this is a minefield.

    Returns:
        int, float or string
    """
    if isinstance(value, int):
        return value
    elif isinstance(value, float):
        if int(value) == value:
            return int(value)
        return value
    else:  # noqa
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return value


class VirtualRealization(object):
    """A computed or archived realization.

    Computed or archived, one cannot assume to have access to the file
    system containing original data.

    Datatables that in a ScratchRealization was available through the
    files dataframe, is now available as dataframes in a dict accessed
    by the localpath in the files dataframe from ScratchRealization-

    """
    def __init__(self, description=None, origpath=None):
        self._description = ''
        self._origpath = None

        if origpath:
            self._origpath = origpath
        if description:
            self._description = description

    def get_smryvalues(self, props_wildcard=None):
        """Returns summary values for certain vectors.

        Taken from stored dataframe.
        """
        raise NotImplementedError

    def __len__(self):
        raise NotImplementedError
