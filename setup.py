from cx_Freeze import setup, Executable

# Dependencies are automatically detected, but it might need
# fine tuning.
build_options = {'packages': [], 'excludes': []}

import sys
base = 'Win32GUI' if sys.platform=='win32' else None

executables = [
    Executable('freetv.py', base=base)
]

setup(name='FreeTV',
      version = '0.1.0',
      description = 'FreeDV image transmission',
      options = {'build_exe': build_options},
      executables = executables)
