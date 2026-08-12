import ctypes


class AudioPlayer:
    def __init__(self):
        self.winmm = ctypes.windll.winmm
        self.alias = "iseeu_audio"
        self.current_file = None

    def play(self, filepath):
        self.stop()
        ret = self.winmm.mciSendStringW(f'open "{filepath}" alias {self.alias}', None, 0, None)
        if ret == 0:
            self.current_file = filepath
            self.winmm.mciSendStringW(f"play {self.alias}", None, 0, None)
            return True
        return False

    def stop(self):
        self.winmm.mciSendStringW(f"close {self.alias}", None, 0, None)
        self.current_file = None
