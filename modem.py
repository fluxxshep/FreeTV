import freedv
import pyaudio
import math
import time


def list_audio_devices():
    p = pyaudio.PyAudio()
    input_devices = {}
    output_devices = {}

    for i in range(p.get_device_count()):
        device = p.get_device_info_by_index(i)

        if device['maxInputChannels'] == 0 and device['hostApi'] == 0:
            output_devices[str(i)] = device['name']

        elif device['maxOutputChannels'] == 0 and device['hostApi'] == 0:
            input_devices[str(i)] = device['name']

    return input_devices, output_devices


class Modem:
    """

    Modem utilizing the FreeDV raw data modes.

    Written by Max, KO4VMI

    """

    forward_mode = freedv.MODE_DATAC1
    arq_mode = freedv.MODE_DATAC13

    def __init__(self, in_device, out_device):
        self.audio_frames_per_buffer = 1024

        self.p = pyaudio.PyAudio()
        self.pastream = self.p.open(rate=8000, channels=1, format=pyaudio.paInt16,
                                    frames_per_buffer=self.audio_frames_per_buffer,
                                    input=True, output=True,
                                    input_device_index=in_device, output_device_index=out_device)

        self.forward_freedv = freedv.FreeDVData(self.forward_mode)
        self.arq_freedv = freedv.FreeDVData(self.arq_mode)

        self.rx_state = 0
        self.is_transmitting = False
        self.freedv_mode = self.forward_mode

        self.forward_bytes_per_frame = freedv.get_payload_bytes_from_mode(self.forward_mode)
        self.arq_bytes_per_frame = freedv.get_payload_bytes_from_mode(self.arq_mode)

    def set_mode(self, mode):
        self.freedv_mode = mode

    def tx(self, data):
        tx_freedv = None
        if self.freedv_mode == self.forward_mode:
            tx_freedv = self.forward_freedv
        elif self.freedv_mode == self.arq_mode:
            tx_freedv = self.arq_freedv

        assert tx_freedv is not None

        samples = tx_freedv.tx_burst(data)
        self.pastream.write(samples)

    def rx(self):
        rx_freedv = None
        if self.freedv_mode == self.forward_mode:
            rx_freedv = self.forward_freedv
        elif self.freedv_mode == self.arq_mode:
            rx_freedv = self.arq_freedv

        assert rx_freedv is not None

        nin = rx_freedv.nin
        self.rx_state, rx_bytes = rx_freedv.rx(self.pastream.read(nin, exception_on_overflow=False))

        if rx_bytes:
            return rx_bytes[:-2]

    def close(self):
        self.forward_freedv.close()
        self.arq_freedv.close()
        self.pastream.close()
        self.p.terminate()


class ArqModem(Modem):
    callsign_bytes = 10
    tx_id_bytes = 1
    frame_id_bytes = 1
    frame_num_bytes = 1

    callsign_offset = 0
    tx_id_offset = callsign_offset + callsign_bytes
    frame_id_offset = tx_id_offset + tx_id_bytes
    frame_num_offset = frame_id_offset + frame_id_bytes
    payload_offset = frame_num_offset + frame_num_bytes

    total_header_bytes = callsign_bytes + tx_id_bytes + frame_id_bytes + frame_num_bytes

    retransmit_id_bytes = 1
    retransmit_id_offset = callsign_offset + callsign_bytes

    arq_wait_time = 15
    missed_frames_wait_time = 5
    retransmit_wait_time = 7

    retransmit_request_retries = 2

    def __init__(self, in_device, out_device, callsign):
        super().__init__(in_device, out_device)
        self.callsign = callsign

        self.frames = []
        self.tx_id = 0
        self.arq_callsign = None

        self.rx_callsign = None
        self.rx_num_frames = None
        self.rx_id = None
        self.rx_frames = {}
        self.last_rx_sync = None

    def arq_tx(self, data):
        self.frames = []

        data_size = len(data)
        payload_available_for_data = self.forward_bytes_per_frame - self.total_header_bytes

        frame_id = 0

        callsign = self.callsign.encode()

        if len(callsign) < self.callsign_bytes:
            callsign += (b'\x00' * (self.callsign_bytes - len(callsign)))

        num_frames = math.ceil(data_size / payload_available_for_data)

        for i in range(0, data_size + 1, payload_available_for_data):
            frame_data = bytearray(data[i:i + payload_available_for_data])

            if len(frame_data) != payload_available_for_data:
                frame_data.extend(b'\x00' * (payload_available_for_data - len(frame_data)))

            frame = bytearray(callsign + self.tx_id.to_bytes(1) + frame_id.to_bytes(1) + num_frames.to_bytes(1))
            frame_id += 1

            frame.extend(frame_data)
            self.frames.append(frame)

        self.set_mode(self.forward_mode)

        for frame in self.frames:
            assert len(frame) == self.forward_bytes_per_frame
            self.tx(frame)

        self.arq_callsign = self.wait_for_arq()

        self.tx_id += 1

        if self.tx_id > 255:
            self.tx_id = 0

    def arq_retransmit_frame(self, frame_id):
        self.set_mode(self.forward_mode)
        self.tx(self.frames[frame_id])

    def wait_for_arq(self):
        print('Waiting for ARQ retransmit request...')
        self.set_mode(self.arq_mode)
        start_time = time.time()

        while True:
            new_time = time.time()

            if new_time - start_time > self.arq_wait_time:
                print('ARQ wait timed out')
                return False

            rx_bytes = self.rx()

            if rx_bytes is not None:
                callsign = rx_bytes[self.callsign_offset:self.retransmit_id_offset]
                retransmit_id = rx_bytes[self.retransmit_id_offset]
                print(f'ARQ retransmit request received by {callsign.decode()} for frame {retransmit_id}')

                self.arq_retransmit_frame(retransmit_id)
                self.wait_for_arq()
                return callsign

    def arq_rx(self):
        self.set_mode(self.forward_mode)
        rx_bytes = self.rx()

        if self.rx_state != 0:
            self.last_rx_sync = time.time()

        if rx_bytes is not None:
            callsign = rx_bytes[self.callsign_offset:self.tx_id_offset]
            tx_id = rx_bytes[self.tx_id_offset:self.frame_id_offset]
            frame_id = rx_bytes[self.frame_id_offset:self.frame_num_offset]
            num_frames = rx_bytes[self.frame_num_offset:self.payload_offset]
            payload = rx_bytes[self.payload_offset:]

            tx_id = int.from_bytes(tx_id)

            if callsign != self.rx_callsign or tx_id != self.rx_id:
                self.rx_frames = {}

            self.rx_frames[str(int.from_bytes(frame_id))] = payload

            self.rx_callsign = callsign
            self.rx_id = tx_id
            self.rx_num_frames = int.from_bytes(num_frames)

    def check_missed_frames(self):
        if self.last_rx_sync is not None:
            if time.time() - self.last_rx_sync > self.missed_frames_wait_time:
                missed_frames = []

                for i in range(self.rx_num_frames):
                    if str(i) not in self.rx_frames.keys():
                        missed_frames.append(i)

                return missed_frames

            return False

    def wait_for_retransmit(self):
        print('Waiting for station to retransmit frame...')
        self.set_mode(self.forward_mode)
        start_time = time.time()

        while True:
            new_time = time.time()

            if new_time - start_time > self.retransmit_wait_time:
                return False

            rx_bytes = self.rx()

            if rx_bytes is not None:
                callsign = rx_bytes[self.callsign_offset:self.tx_id_offset]
                tx_id = rx_bytes[self.tx_id_offset:self.frame_id_offset]
                frame_id = rx_bytes[self.frame_id_offset:self.frame_num_offset]
                num_frames = rx_bytes[self.frame_num_offset:self.payload_offset]
                payload = rx_bytes[self.payload_offset:]

                tx_id = int.from_bytes(tx_id)

                if callsign != self.rx_callsign or tx_id != self.rx_id:
                    self.rx_frames = {}

                self.rx_frames[str(int.from_bytes(frame_id))] = payload
                print(self.rx_frames)

                self.rx_callsign = callsign
                self.rx_id = tx_id
                self.rx_num_frames = int.from_bytes(num_frames)

                return True

    def tx_retransmit_request(self):
        missed_frames = self.check_missed_frames()

        if isinstance(missed_frames, list):
            callsign = self.callsign.encode()

            if len(callsign) < self.callsign_bytes:
                callsign += (b'\x00' * (self.callsign_bytes - len(callsign)))

            for frame_id in missed_frames:
                retransmit_success = False

                for attempt_num in range(self.retransmit_request_retries):
                    print(f'Sending retransmit request for frame {frame_id} (attempt {attempt_num + 1})')
                    self.set_mode(self.arq_mode)

                    arq_frame = callsign + frame_id.to_bytes(1)
                    self.tx(arq_frame)

                    retransmit_success = self.wait_for_retransmit()
                    if retransmit_success:
                        break

                if not retransmit_success:
                    return False

            missed_frames = self.check_missed_frames()

            if missed_frames:
                self.tx_retransmit_request()

            return True

    def get_rx_data(self):
        data = bytearray()

        if self.rx_num_frames is not None:
            for i in range(self.rx_num_frames):
                try:
                    data.extend(self.rx_frames[str(i)])
                except KeyError:
                    return None

            self.rx_num_frames = None
            self.rx_frames = {}
            return data

        else:
            return None

    def get_rx_callsign(self):
        if self.rx_callsign is not None:
            return self.rx_callsign.decode()
