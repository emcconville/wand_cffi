import csv
import platform
import re
import os
import sys
from subprocess import Popen, PIPE

from cffi import FFI


ffi = FFI()
library_wand = None
library_core = None
HEADER_FILE = os.path.join(os.path.dirname(__file__), 'wand-py.h')
PLATFORM = platform.system()


CPP_INPUT = """
#define __attribute__(x)
#define va_list void *
#define time_t long
#include <wand/MagickWand.h>
"""
WIN_CPP_INPUT = """
#define va_list char *
#define time_t unsigned int
#include <wand/MagickWand.h>
"""


class Preprocessor(object):

    @staticmethod
    def by_system(system):
        if system == 'Darwin':
            return DarwinPreprocessor()
        if system == 'Linux':
            return Preprocessor()
        if system == 'Windows':
            return WindowsPreprocessor()
        raise IOError('Unsupported system: ' + repr(system))

    def __init__(self):
        csv.register_dialect('preprocessor_line', delimiter=' ', quotechar='"')

    def call_system(self, commands, stdin=None):
        pid = Popen(commands,
                    stdin=PIPE,
                    stdout=PIPE)
        stdout, stderr = pid.communicate(stdin)
        return pid.returncode, stdout, stderr

    def get_preprocessor_commands(self):
        return ['gcc', '-xc', '-E', '-std=c89']

    def get_magick_config_commands(self):
        return ['MagickWand-config', '--cflags']

    @staticmethod
    def get_wand_library_name():
        return 'MagickWand'

    @staticmethod
    def get_core_library_name():
        return 'MagickCore'

    def is_system(self, line):
        for marking in csv.reader([line], 'preprocessor_line'):
            # ['#', line_number, 'file_path', 1?, 2?, 3?, 4?]
            return '3' in marking[3:]

    def lexical_scan(self, buffer):
        """Iterate over buffer, and reduce to bare-minimal
           header file"""
        c_definitions = open(HEADER_FILE,'w')
        # Need to do a primitive lexer to determine to sort out
        # system declarations.
        ignore = False
        for line in buffer.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                ignore = self.is_system(line)
                continue
            if not line:
                continue
            # Preprocessor doesn't expand DefaultChannels
            # Hard-code default channels
            if 'DefaultChannels =' in line:
                line = '  DefaultChannels = 0x7ffffff7'
            if ignore:
                continue
            if line.endswith(';') or line.startswith('}'):
                line_end = '\n'
            else:
                line_end = ' '
            c_definitions.write(line + line_end)

        c_definitions.close()

    def remove_expanded_inline(self, buffer):
        # This sucks.
        # We need to remove expanded static inline,
        # and convert them to static function signatures.
        pattern = r"""
            ^static\s_*inline\s               # Key line identifier
            (?P<return>\w+|unsigned\schar)\s  # Return type
            (?P<method>\w+)                   # Method name
            \((?P<args>.*?)\)\s*              # Arguments
            \{(?P<block>.*?)^\}               # Code block
        """
        # Keep `static', but remove `inline' + code  block
        replacement = 'static \g<return> \g<method>(\g<args>);\n'
        static_inline_re = re.compile(pattern,
                                      re.MULTILINE | re.DOTALL | re.VERBOSE)
        return static_inline_re.sub(replacement, buffer)

    def run(self):
        ok, c_flags, _ = self.call_system(self.get_magick_config_commands())
        preprocessor_commands = self.get_preprocessor_commands()
        preprocessor_commands += c_flags.decode().strip().split(' ')

        ok, stdout, stderr = self.write_and_compile(CPP_INPUT.encode(),
                                                    preprocessor_commands)
        if ok != 0:
            raise IOError(stderr)
        stdout = self.remove_expanded_inline(stdout.decode())
        self.lexical_scan(stdout)

    def write_and_compile(self, c_input, commands):
        temp_filename = '_temp.c'
        with open(temp_filename, 'w') as temp_c:
            temp_c.write(c_input.decode('utf-8'))
        response = self.call_system(commands + [temp_c.name])
        os.unlink(temp_filename)
        return response


class DarwinPreprocessor(Preprocessor):
    def get_preprocessor_commands(self):
        return ['clang', '-arch', 'x86_64', '-xc', '-E', '-std=c89']

    def get_magick_config_commands(self):
        return ['MagickWand-config', '--cflags']

    @staticmethod
    def get_wand_library_name():
        return 'libMagickWand-6.Q16'

    @staticmethod
    def get_core_library_name():
        return 'libMagickCore-6.Q16'


class WindowsPreprocessor(Preprocessor):
    def __init__(self):
        self.magick_home = os.getenv('MAGICK_HOME', 'C:\\Program Files\\ImageMagick-6.9.0-Q16')
        super(WindowsPreprocessor, self).__init__()

    def get_preprocessor_commands(self):
        return ['cl', '/E']

    def get_magick_config_commands(self):
        return None

    @staticmethod
    def get_wand_library_name():
        return 'CORE_RL_wand_'

    @staticmethod
    def get_core_library_name():
        return 'CORE_RL_magick_'

    def is_system(self, line):
        if 'magick' in line:
            return False
        elif 'wand' in line:
            return False
        return True

    def run(self):
        if not self.magick_home:
            raise IOError('Unable to locate $MAGICK_HOME')
        commands = self.get_preprocessor_commands()
        commands += ['/I"{0}\include"'.format(self.magick_home)]

        ok, stdout, stderr = self.write_and_compile(WIN_CPP_INPUT, commands)

        if ok != 0:
            raise IOError(stderr)

        stdout = self.remove_expanded_inline(stdout.decode())
        self.lexical_scan(stdout)


def get_library():
    global ffi
    global library_wand
    global library_core
    if library_wand:
        return ffi, library_wand, library_core
    cpp = Preprocessor.by_system(PLATFORM)
    if not os.path.isfile(HEADER_FILE):
        cpp.run()
    ffi.cdef(open(HEADER_FILE, 'r').read(), override=True)
    library_wand = ffi.dlopen(cpp.get_wand_library_name())
    library_core = ffi.dlopen(cpp.get_core_library_name())
    return ffi, library_wand, library_core


if __name__ == '__main__':
    import time
    start = time.time()
    if '--cpp' in sys.argv:
        print('--cpp')
        cpp = Preprocessor.by_system(PLATFORM)
        cpp.run()
    C, wand, core = get_library()
    release_date = core.GetMagickReleaseDate()
    size_t = C.new('size_t *')
    version = core.GetMagickVersion(size_t)
    print(C.string(version))
    print(hex(size_t[0]))
    end = time.time()
    print(str(end - start) + 's')
