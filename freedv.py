from ctypes import *
from threading import Lock
import numpy as np
import math
import platform

MODE_FSK_LDPC = 9
MODE_DATAC1 = 10
MODE_DATAC3 = 12
MODE_DATAC0 = 14
MODE_DATAC4 = 18
MODE_DATAC13 = 19
MODE_700D = 7


def generate_silence(duration):
    num_delay_samples = (duration / 1000) * 8000  # sample rate is 8000
    return bytearray([0] * int(num_delay_samples))


class DataTooLarge(Exception):
    pass


def get_payload_bytes_from_mode(mode):
    if mode == MODE_DATAC1:
        return 510
    elif mode == MODE_DATAC3:
        return 126
    elif mode == MODE_DATAC13:
        return 14
    else:
        return None


class FreeDVData:
    """

    Python interface for the FreeDV API raw data modes. Written by Max, KO4VMI

    Credits:

    David Rowe, for developing FreeDV and the audio_buffer class

    Simon DJ2LS, for helping me make this and providing me with example code.

    """

    def __init__(self, mode):
        system = platform.system()
        libname = None

        if system == 'Windows':
            libname = 'lib/libcodec2.dll'
        elif system == 'Linux':
            libname = 'lib/libcodec2.so'

        assert libname is not None

        try:
            self.c_lib = CDLL(libname)
        except Exception:
            self.c_lib = CDLL('_internal/' + libname)

        self.c_lib.freedv_open.restype = POINTER(c_ubyte)

        self.freedv = self.c_lib.freedv_open(mode)

        self.c_lib.freedv_get_n_max_modem_samples.argtype = [c_void_p]
        self.c_lib.freedv_get_n_max_modem_samples.restype = c_int

        self.c_lib.freedv_get_n_tx_modem_samples.argtype = [self.freedv]
        self.c_lib.freedv_get_n_tx_modem_samples.restype = c_size_t

        self.c_lib.freedv_get_n_tx_preamble_modem_samples.argtype = [self.freedv]
        self.c_lib.freedv_get_n_tx_preamble_modem_samples.restype = c_size_t

        self.c_lib.freedv_get_n_tx_postamble_modem_samples.argtype = [self.freedv]
        self.c_lib.freedv_get_n_tx_postamble_modem_samples.restype = c_size_t

        self.c_lib.freedv_get_bits_per_modem_frame.argtype = [self.freedv]
        self.c_lib.freedv_get_bits_per_modem_frame.restype = c_size_t

        self.c_lib.freedv_nin.argtype = [self.freedv]
        self.c_lib.freedv_nin.restype = c_int

        self.c_lib.freedv_rawdatarx.argtype = [self.freedv, c_uint8, c_short]
        self.c_lib.freedv_rawdatarx.restype = c_size_t

        self.c_lib.freedv_rawdatapreambletx.argtype = [self.freedv, c_short]
        self.c_lib.freedv_rawdatapreambletx.restype = c_int

        self.c_lib.freedv_rawdatatx.argtype = [self.freedv, c_short, c_uint8]
        self.c_lib.freedv_rawdatatx.restype = c_void_p

        self.c_lib.freedv_rawdatapostambletx.argtype = [self.freedv, c_short]
        self.c_lib.freedv_rawdatapostambletx.restype = c_int

        self.c_lib.freedv_gen_crc16.argtype = [c_uint8, c_size_t]
        self.c_lib.freedv_gen_crc16.restype = c_uint16

        self.bytes_per_modem_frame = self.c_lib.freedv_get_bits_per_modem_frame(self.freedv) // 8
        self.payload_bytes_per_modem_frame = self.bytes_per_modem_frame - 2

        self.n_mod_out = self.c_lib.freedv_get_n_tx_modem_samples(self.freedv)

        self.c_lib.freedv_set_frames_per_burst.argtype = [self.freedv, c_int]
        self.c_lib.freedv_set_frames_per_burst.restype = c_void_p

        self.c_lib.freedv_set_verbose.argtype = [self.freedv, c_int]
        self.c_lib.freedv_set_verbose.restype = c_void_p

        self.c_lib.freedv_rawdatarx.argtype = [self.freedv, c_uint8, c_short]
        self.c_lib.freedv_rawdatarx.restype = c_size_t

        self.c_lib.freedv_close.argtype = [c_void_p]
        self.c_lib.freedv_close.restype = c_void_p

        self.c_lib.freedv_get_sync.argtype = [self.freedv]
        self.c_lib.freedv_get_sync.restype = c_int

        self.c_lib.freedv_set_sync.argtype = [self.freedv, c_int]
        self.c_lib.freedv_set_sync.restype = c_void_p

        self.c_lib.freedv_get_rx_status.argtype = [self.freedv]
        self.c_lib.freedv_get_rx_status.restype = c_int

        self.c_lib.freedv_get_total_bits.argtype = [self.freedv]
        self.c_lib.freedv_get_total_bits.restype = c_int

        self.c_lib.freedv_get_total_bit_errors.argtype = [self.freedv]
        self.c_lib.freedv_get_total_bit_errors.restype = c_int

        self.c_lib.freedv_set_frames_per_burst.argtype = [self.freedv, c_int]
        self.c_lib.freedv_set_frames_per_burst.restype = c_void_p

        self.c_lib.freedv_set_tx_amp.argtype = [self.freedv, c_float]
        self.c_lib.freedv_set_tx_amp.restype = c_void_p

        self.c_lib.freedv_set_frames_per_burst(self.freedv, 1)
        self.c_lib.freedv_set_verbose(self.freedv, 1)

        self.nin = self.get_freedv_rx_nin()
        self.frames_per_burst = 1

        self.n_tx_modem_samples = self.c_lib.freedv_get_n_tx_modem_samples(self.freedv)
        self.n_tx_preamble_modem_samples = self.c_lib.freedv_get_n_tx_preamble_modem_samples(self.freedv)
        self.n_tx_postamble_modem_samples = self.c_lib.freedv_get_n_tx_postamble_modem_samples(self.freedv)

    def set_frames_per_burst(self, num_frames):
        self.frames_per_burst = num_frames
        self.c_lib.freedv_set_frames_per_burst(self.freedv, num_frames)

    def tx_burst(self, data_in):
        # init buffers
        mod_out = create_string_buffer(self.n_tx_modem_samples * 2)
        mod_out_preamble = create_string_buffer(self.n_tx_preamble_modem_samples * 2)
        mod_out_postamble = create_string_buffer(self.n_tx_postamble_modem_samples * 2)

        # preamble
        self.c_lib.freedv_rawdatapreambletx(self.freedv, mod_out_preamble)
        txbuffer = bytes(mod_out_preamble)

        # find number of frames needed to tx all data
        num_frames = math.ceil(len(data_in) / self.payload_bytes_per_modem_frame)

        if num_frames > self.frames_per_burst:
            raise DataTooLarge

        print(f'MODEM: Transmitting burst with {num_frames} frames')

        # create data frames
        for i in range(num_frames):
            # main data buffer
            buffer = bytearray(self.payload_bytes_per_modem_frame)
            data_chunk = data_in[i * self.payload_bytes_per_modem_frame:(i + 1) * self.payload_bytes_per_modem_frame]
            buffer[:len(data_chunk)] = data_chunk

            # add crc16
            crc16 = c_ushort(self.c_lib.freedv_gen_crc16(bytes(buffer), self.payload_bytes_per_modem_frame))
            crc16 = crc16.value.to_bytes(2, byteorder='big')
            buffer += crc16

            data = (c_ubyte * self.bytes_per_modem_frame).from_buffer_copy(buffer)
            self.c_lib.freedv_rawdatatx(self.freedv, mod_out, data)
            txbuffer += bytes(mod_out)

        # postamble
        self.c_lib.freedv_rawdatapostambletx(self.freedv, mod_out_postamble)
        txbuffer += mod_out_postamble

        # add silence between bursts
        txbuffer += generate_silence(50)

        return txbuffer

    def tx_data(self, data_in):
        # this function will split up incoming data if data is larger than can be transmitted in one burst
        bytes_per_burst = self.frames_per_burst * self.payload_bytes_per_modem_frame
        tx_buffer = b''

        # calculate how many bursts are requird to tx all data
        num_bursts = math.ceil(len(data_in) / bytes_per_burst)
        for i in range(num_bursts):
            tx_buffer += self.tx_burst(data_in[i * bytes_per_burst:(i + 1) * bytes_per_burst])

        return tx_buffer

    def get_freedv_rx_nin(self):
        return self.c_lib.freedv_nin(self.freedv)

    def get_n_max_modem_samples(self):
        return self.c_lib.freedv_get_n_max_modem_samples(self.freedv)

    def get_sync(self):
        return self.c_lib.freedv_get_sync(self.freedv)

    def set_sync(self, sync_cmd):
        self.c_lib.freedv_set_sync(self.freedv, sync_cmd)

    def get_total_bits(self):
        return self.c_lib.freedv_get_total_bits(self.freedv)

    def get_total_bit_errors(self):
        return self.c_lib.freedv_get_total_bit_errors(self.freedv)

    def get_rx_status(self):
        return self.c_lib.freedv_get_rx_status(self.freedv)

    def rx(self, demod_in):
        bytes_out = create_string_buffer(self.bytes_per_modem_frame)
        nbytes_out = self.c_lib.freedv_rawdatarx(self.freedv, bytes_out, demod_in)

        self.nin = self.get_freedv_rx_nin()
        status = self.get_rx_status()

        return status, bytes_out[:nbytes_out]

    def close(self):
        self.c_lib.freedv_close(self.freedv)


class audio_buffer:
    """
    Thread-safe audio buffer, which fits the needs of codec2

    made by David Rowe, VK5DGR
    """

    # A buffer of int16 samples, using a fixed length numpy array self.buffer for storage
    # self.nbuffer is the current number of samples in the buffer
    def __init__(self, size):
        # log.debug("[C2 ] Creating audio buffer", size=size)
        self.size = size
        self.buffer = np.zeros(size, dtype=np.int16)
        self.nbuffer = 0
        self.mutex = Lock()

    def push(self, samples):
        """
        Push new data to buffer

        Args:
            samples:

        Returns:
            Nothing
        """
        self.mutex.acquire()
        # Add samples at the end of the buffer
        assert self.nbuffer + len(samples) <= self.size
        self.buffer[self.nbuffer: self.nbuffer + len(samples)] = samples
        self.nbuffer += len(samples)
        self.mutex.release()

    def pop(self, size):
        """
        get data from buffer in size of NIN
        Args:
          size:

        Returns:
            Nothing
        """
        self.mutex.acquire()
        # Remove samples from the start of the buffer
        self.nbuffer -= size
        self.buffer[: self.nbuffer] = self.buffer[size: size + self.nbuffer]
        assert self.nbuffer >= 0
        self.mutex.release()
