import os
import json
import asyncio
import edge_tts
import tempfile
import subprocess
from database import db
from providers import TTSError, TTSProvider
from collections import defaultdict

class Edge(TTSProvider):
    def save_voices(self):
        result = asyncio.run(edge_tts.list_voices())
        voices = defaultdict(list)
        for voice in result:
            name = ' '.join(voice['FriendlyName'].replace('Microsoft', '').replace('Online', '').replace('(Natural)', '').split('-')[0].strip().split())
            attributes = ', '.join([voice['Gender']] + voice['VoiceTag'].get('ContentCategories', []) + voice['VoiceTag'].get('VoicePersonalities', []))
            if attributes:
                name += f' ({attributes})'
            voices[voice['Locale']].append({
                'id': voice['ShortName'],
                'name': name,
                'gender': voice['Gender'],
                'language_code': voice['Locale'],
                'language_name': voice['Locale'],
                'label': name,
            })
        for lang in list(voices.keys()):
            voices[lang] = sorted(voices[lang], key=lambda x: (
                not x['language_name'].startswith('GB'),
                not x['language_name'].startswith('US'),
                x['name'],
            ))
        voices = dict(sorted(voices.items(), key=lambda x: (
            not x[0].startswith('en-'),
            not x[0].startswith('he-'),
            x[0]
        )))
        voices = {'default': voices}
        self.provider.voices = json.dumps(voices)
        db.session.commit()

    def setup(self):
        try:
            self.save_voices()
        except Exception as e:
            raise Exception(f'Failed to save voices - {e}')

    def get_voices(self):
        try:
            return json.loads(self.provider.voices)
        except TypeError:
            return {}

    @classmethod
    def tts(cls, text, voice, audio_dst, subtitles_dst='/dev/null'):
        # Create a temporary file to store the text
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w') as temp_text_file:
            temp_text_file.write(text)
            temp_text_path = temp_text_file.name
        command = [
            'edge-tts',
            '-f', temp_text_path,
            '--write-media', audio_dst,
            '--write-subtitles', subtitles_dst,
            '--voice', voice
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Optionally print the result or return status
        if result.returncode != 0:
            raise TTSError(f'Error running TTS: {result.stderr}')
        # Clean up the temporary file (delete after the command is done)
        os.remove(temp_text_path)

    @classmethod
    def sample_voice(cls, voice, sample_text):
        temp_dir = tempfile.TemporaryDirectory(delete=False)
        audio_dst = os.path.join(temp_dir.name, 'sample.mp3')
        subtitles_dst = os.path.join(temp_dir.name, 'subs')
        tts(sample_text, voice, audio_dst, subtitles_dst)
        return audio_dst
