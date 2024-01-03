# FreeTV
HF radio image transmission using the FreeDV modem

This program is in very, very early stages of development. Expect bugs, and use on the air at your own risk!

# Installation
Install python 3 on your system. Then, run `pip install -r requirements.txt` in the root directory of this repository.
*You might want to do this in a python virtual environment!*
Then, after building codec2 (see next section), run `python freetv.py`,
or you may choose to convert to a standalone executable by running `python setup.py build`.
This will run cx_freeze (automatially installed from requirements.txt) to build the app.

# libcodec2
Finally, you will need to compile codec2 from https://github.com/drowe67/codec2.
Once built, place the libcodec2.so / .dll files inside a `lib` directory located in root directory.
