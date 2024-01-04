# FreeTV
HF radio image transmission using the FreeDV modem

This program is in very, very early stages of development. Expect bugs, and use on the air at your own risk!

# Installation
Releases will be available at https://github.com/fluxxshep/FreeTV/releases.
Alternatively, you can "manually" run it with python.
Install python 3 on your system. Then, run `pip install -r requirements.txt`.
*You might want to do this in a python virtual environment!*
Then, after building codec2 (see next section), run `python freetv.py`

# libcodec2 (if you are installing manually)
Finally, you will need to compile codec2 from https://github.com/drowe67/codec2.
Once built, place the libcodec2.so / .dll files inside a `lib` directory in the same directory as the .py files.
If you used cx_freeze to build the files, a `lib` directory already exists in the build directory.
Put the libcodec2 files there!
