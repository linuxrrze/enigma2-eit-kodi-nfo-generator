# Description
Script to convert from enigma2 eit files to nfo files used by kodi

Ported to Python 3 from the Python 2 version sourced from [here](https://gist.github.com/marcohald/5a58698c71d36ae62a2ac897917eecac) which was originally based on [this](https://github.com/betonme/e2openplugin-EnhancedMovieCenter/blob/master/src/EitSupport.py).

More information about the basic format can be found in [ETSI EN 300 468 (latest version: v1.16.1 (2019-08))](https://www.etsi.org/deliver/etsi_en/300400_300499/300468/01.16.01_60/en_300468v011601p.pdf)

# Using the script

`python3 enigma2-eit-kodi-nfo-generator.py <dir-name1> <dir-name2> ...`

The script will covert each `*.eit` file it finds in the specified directories.
