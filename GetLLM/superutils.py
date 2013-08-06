'''
Collection of functions of more general use that 
were originally in getsuper.py

Feel free to move these around to more suitable places.

'''


def get_twissfile(options):
    '''
    Returns the full path to
    the twiss file
    '''

    import os

    _twpaths=[options.twissfile,
              os.path.join(options.twissfile,'twiss.dat'),
              os.path.join(options.twissfile,'twiss.dat.gz')]
    for _twpath in _twpaths:
        if os.path.isfile(_twpath):
            return _twpath
    # did not find any file..
    raise ValueError("Could not find twissfile! "+options.twissfile)

def get_filelist(options, args):
    '''
    Returns list of files to be analysed

    Files can either be given with the optional argument
     --files=f1,f2,...
     or as arguments
     f1 f2 ...
    '''
    if options.files:
        files = [f.strip() for f in options.files.split(',')]
        files.extend(args)
        return files
    return args