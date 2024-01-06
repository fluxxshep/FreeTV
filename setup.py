from cx_Freeze import setup, Executable

# Dependencies are automatically detected, but it might need
# fine tuning.
build_options = {'packages': [], 'excludes': [], 'include_files': ['lib']}

import sys
base = 'Win32GUI' if sys.platform=='win32' else None

executables = [
    Executable('freetv.py', base=base, target_name = 'FreeTV')
]

setup(name='FreeTV',
      version = '0.1.0',
      description = 'Amateur radio digital image transmission',
      options = {'build_exe': build_options},
      executables = executables)
