class TTSError(Exception):
    pass

class TTSProvider:
    has_quotas = False
    ssml_capable = False

    def __init__(self, provider):
        self.provider = provider

    def setup(self):
        pass

    def check_quota(self, voice_id, text_length):
        return True

    def quotas_text(self):
        return None
