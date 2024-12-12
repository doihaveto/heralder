import json
import utils
from pydub import AudioSegment
from database import db
from datetime import datetime
from providers import TTSError, TTSProvider
from collections import defaultdict
from google.cloud import texttospeech, storage
from google.oauth2 import service_account

class GoogleTTS(TTSProvider):
    has_quotas = True
    ssml_capable = True

    def __init__(self, provider):
        self.provider = provider
        self.settings = provider.parsed_settings()
        self.bucket_name = self.settings.get('bucket_name')
        self.credentials_dict = json.loads(self.settings['credentials'])
        self.project_id = self.credentials_dict['project_id']
        self.credentials = service_account.Credentials.from_service_account_info(self.credentials_dict)

    def setup(self):
        try:
            self.create_bucket()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(e)
            raise Exception(f'Failed to create bucket: {e}')
        try:
            self.save_voices()
        except Exception as e:
            raise Exception(f'Failed to save voices: {e}')
        try:
            self.get_quotas()
        except Exception as e:
            raise Exception(f'Failed to save quotas: {e}')

    def create_bucket(self):
        region = self.settings.get('bucket_region') or 'europe-west4'
        storage_client = storage.Client(credentials=self.credentials)
        try:
            bucket = storage_client.get_bucket(self.bucket_name)
        except Exception:
            # Create the bucket
            bucket = storage.Bucket(storage_client, name=self.bucket_name)
            bucket.storage_class = 'STANDARD'
            new_bucket = storage_client.create_bucket(bucket, location=region)
            # Ensure the bucket is private by removing public access
            new_bucket.iam_configuration.uniform_bucket_level_access_enabled = True
            new_bucket.versioning_enabled = False
            new_bucket.retention_policy = None
            new_bucket.patch()

    def save_voices(self):
        client = texttospeech.TextToSpeechClient(credentials=self.credentials)
        response = client.list_voices()
        voices = defaultdict(lambda: defaultdict(list))
        for voice in response.voices:
            engine = voice.name.split('-')[2]
            gender = texttospeech.SsmlVoiceGender(voice.ssml_gender).name
            for language_code in voice.language_codes:
                name_formatted = voice.name.replace(language_code, '').replace('-', ' ').strip()
                voices[engine][language_code].append({
                    'id': f'{voice.name}-{gender}',
                    'label': f'{name_formatted} - {gender.title()}',
                    'gender': gender,
                    'natural_sample_rate_hertz': voice.natural_sample_rate_hertz,
                    'language_name': language_code,
                })
        self.provider.voices = json.dumps(voices)
        db.session.commit()

    def get_voices(self):
        if not self.provider.voices:
            return []
        return json.loads(self.provider.voices)

    @classmethod
    def parse_voice_id(cls, voice_id):
        parts = voice_id.split('-')
        engine = parts[2]
        language_code = '-'.join(parts[:2])
        gender = parts[-1]
        voice_name = '-'.join(parts[:-1])
        return engine, language_code, gender, voice_name

    def tts_short(self, text, voice, audio_dst):
        client = texttospeech.TextToSpeechClient(credentials=self.credentials)
        engine, language_code, gender, voice_name = self.parse_voice_id(voice)
        if text.startswith('<speak>'):
            input_text = texttospeech.SynthesisInput(ssml=text)
        else:
            input_text = texttospeech.SynthesisInput(text=text)
        voice_params = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE if gender == 'FEMALE' else texttospeech.SsmlVoiceGender.MALE,
        )
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        response = client.synthesize_speech(input=input_text, voice=voice_params, audio_config=audio_config)
        with open(audio_dst, 'wb') as f:
            f.write(response.audio_content)

    def tts_long(self, text, voice, audio_dst):
        client = texttospeech.TextToSpeechLongAudioSynthesizeClient(credentials=self.credentials)
        engine, language_code, gender, voice_name = self.parse_voice_id(voice)
        if text.startswith('<speak>'):
            input_text = texttospeech.SynthesisInput(ssml=text)
        else:
            input_text = texttospeech.SynthesisInput(text=text)
        voice_params = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE if gender == 'FEMALE' else texttospeech.SsmlVoiceGender.MALE,
        )
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16)
        fname = utils.generate_random_string(10)
        fname = f'{fname}.wav'
        request = texttospeech.SynthesizeLongAudioRequest(
            parent=f'projects/{self.project_id}/locations/us-central1',
            input=input_text,
            audio_config=audio_config,
            voice=voice_params,
            output_gcs_uri=f'gs://{self.bucket_name}/{fname}',
        )
        operation = client.synthesize_long_audio(request=request)
        result = operation.result(timeout=60*30)
        storage_client = storage.Client(credentials=self.credentials)
        temp_wav_path = f'/tmp/{fname}'
        bucket = storage_client.bucket(self.bucket_name)
        blob = bucket.blob(fname)
        blob.download_to_filename(temp_wav_path)
        audio = AudioSegment.from_wav(temp_wav_path)
        audio.export(audio_dst, format='mp3')
        blob.delete()

    def tts(self, text, voice, audio_dst):
        if len(text) <= 3000:
            return self.tts_short(text, voice, audio_dst)
        else:
            return self.tts_long(text, voice, audio_dst)

    def get_quotas(self):
        # Free-tier quotas: https://cloud.google.com/text-to-speech/pricing
        quotas = self.provider.cached_quotas()
        month = datetime.now().strftime('%Y-%m')
        if not quotas or quotas['month'] != month:
            quotas = {
                'month': month,
                'engines': {
                    'Casual': {'limit': 0, 'used': 0},
                    'Journey': {'limit': 1_000_000, 'used': 0},
                    'Neural2': {'limit': 1_000_000, 'used': 0},
                    'News': {'limit': 0, 'used': 0},
                    'Polyglot': {'limit': 100_000, 'used': 0},
                    'Standard': {'limit': 4_000_000, 'used': 0},
                    'Studio': {'limit': 100_000, 'used': 0},
                    'Wavenet': {'limit': 1_000_000, 'used': 0},
                }
            }
        self.provider.quotas = json.dumps(quotas)
        db.session.commit()
        return quotas

    def check_quota(self, voice_id, text, update=True):
        if self.provider.exceed_quotas:
            return True
        text_length = len(text.encode('utf-8'))
        quotas = self.get_quotas()
        engine, _, _, _ = self.parse_voice_id(voice_id)
        if engine in quotas['engines']:
            remaining = quotas['engines'][engine]['limit'] - quotas['engines'][engine]['used']
            if remaining >= text_length:
                if update:
                    quotas['engines'][engine]['used'] += text_length
                    self.provider.quotas = json.dumps(quotas)
                    db.session.commit()
                return True
        return False

    def quotas_text(self):
        quotas = self.get_quotas()
        lines = []
        if quotas:
            for engine, data in quotas['engines'].items():
                remaining = data['limit'] - data['used']
                used_str = utils.summarize_number(data['used'])
                limit_str = utils.summarize_number(data['limit'])
                used_percentage = ((data['used'] / data['limit']) * 100) if data['limit'] else 100
                lines.append(f'{engine.title()} - {used_str} / {limit_str} ({used_percentage:.1f}% used)')
        return lines

