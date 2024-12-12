import json
import boto3
import utils
from time import sleep
from database import db
from datetime import datetime
from providers import TTSError, TTSProvider
from collections import defaultdict
from botocore.exceptions import ClientError

class Polly(TTSProvider):
    has_quotas = True
    ssml_capable = True

    def __init__(self, provider):
        self.provider = provider
        self.settings = provider.parsed_settings()
        self.bucket_name = self.settings.get('s3_bucket_name')
        self.session = boto3.Session(
            aws_access_key_id=self.settings.get('aws_access_key'),
            aws_secret_access_key=self.settings.get('aws_secret_key'),
            region_name=self.settings.get('region_name')
        )

    def create_bucket(self):
        s3_client = self.session.client('s3')
        try:
            s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            try:
                s3_client.create_bucket(Bucket=self.bucket_name)
            except ClientError as e:
                s3_client.create_bucket(Bucket=self.bucket_name, CreateBucketConfiguration={'LocationConstraint': region_name})

    def create_access_policy(self):
        iam_client = self.session.client('iam')
        policy_name = 'PollyS3AccessPolicy'
        try:
            existing_policy = iam_client.get_policy(PolicyArn=f'arn:aws:iam::aws:policy/{policy_name}')
        except iam_client.exceptions.NoSuchEntityException:
            iam_client.create_policy(PolicyName=policy_name, PolicyDocument=json.dumps({
                'Version': '2012-10-17',
                'Statement': [
                    {
                        'Effect': 'Allow',
                        'Action': [
                            'polly:StartSpeechSynthesisTask',
                            'polly:GetSpeechSynthesisTask',
                            'polly:ListSpeechSynthesisTasks'
                        ],
                        'Resource': '*'
                    },
                    {
                        'Effect': 'Allow',
                        'Action': 's3:PutObject',
                        'Resource': f'arn:aws:s3:::{self.bucket_name}/*'
                    }
                ]
            }))

    def save_voices(self):
        polly_client = self.session.client('polly')
        response = polly_client.describe_voices()
        voices = response['Voices']
        while response.get('NextToken'):
            response = polly_client.describe_voices(NextToken=response.get('NextToken'))
            voices += response['Voices']
        self.provider.voices = json.dumps(voices)
        db.session.commit()

    def setup(self):
        try:
            self.create_bucket()
        except Exception as e:
            raise Exception(f'Failed to create s3 bucket: {e}')
        try:
            self.create_access_policy()
        except Exception as e:
            if 'EntityAlreadyExists' not in str(e):
                raise Exception(f'Failed to create access policy: {e}')
        try:
            self.save_voices()
        except Exception as e:
            raise Exception(f'Failed to save voices: {e}')
        try:
            self.get_quotas()
        except Exception as e:
            raise Exception(f'Failed to save quotas: {e}')

    def get_voices(self):
        if not self.provider.voices:
            return []
        raw_voices = json.loads(self.provider.voices)
        voices = {
            'neural': defaultdict(list),
            'standard': defaultdict(list),
            'long-form': defaultdict(list),
            'generative': defaultdict(list),
        }
        for voice in raw_voices:
            for engine in voice.get('SupportedEngines', []):
                data = {
                    'id': f"{engine}.{voice['Id']}",
                    'name': voice['Name'],
                    'gender': voice['Gender'],
                    'language_code': voice['LanguageCode'],
                    'language_name': voice['LanguageName'],
                    'label': f"{voice['Name']} - {voice['Gender']}"
                }
                voices[engine][voice['LanguageCode']].append(data)
        return voices

    @classmethod
    def parse_voice_id(cls, voice_id):
        engine, voice_id = voice_id.split('.', 1)
        return engine, voice_id

    def tts_short(self, text, voice, audio_dst):
        # for up to 3000 characters
        engine, voice_id = self.parse_voice_id(voice)
        polly_client = self.session.client('polly')
        response = polly_client.synthesize_speech(
            VoiceId=voice_id,
            OutputFormat='mp3', 
            Text=text,
            Engine=engine,
            TextType='ssml' if text.startswith('<speak>') else 'text',
        )
        with open(audio_dst, 'wb') as f:
            f.write(response['AudioStream'].read())

    def tts_long(self, text, voice, audio_dst):
        # for over 3000 characters
        engine, voice_id = self.parse_voice_id(voice)
        polly_client = self.session.client('polly')
        s3_client = self.session.client('s3')
        response = polly_client.start_speech_synthesis_task(
            VoiceId=voice_id,
            OutputS3BucketName=self.bucket_name,
            OutputFormat='mp3', 
            Text=text,
            TextType='ssml' if text.startswith('<speak>') else 'text',
            Engine=engine
        )
        taskId = response['SynthesisTask']['TaskId']
        task_status = None
        while not task_status or task_status['SynthesisTask']['TaskStatus'] in (None, 'scheduled', 'inProgress'):
            if task_status:
                sleep(2)
            task_status = polly_client.get_speech_synthesis_task(TaskId=taskId)
        if task_status['SynthesisTask']['TaskStatus'] != 'completed':
            raise TTSError(f"Failed to generate audio: {task_status}")
        key = task_status['SynthesisTask']['OutputUri'].split('/')[-1]
        s3_client.download_file(self.bucket_name, key, audio_dst)
        s3_client.delete_object(Bucket=self.bucket_name, Key=key)

    def tts(self, text, voice, audio_dst):
        if len(text) <= 3000:
            return self.tts_short(text, voice, audio_dst)
        else:
            return self.tts_long(text, voice, audio_dst)

    def get_quotas(self):
        engines = {
            'SynthesizeSpeech-Chars': 'standard',
            'SynthesizeSpeechGenerative-Characters': 'generative',
            'SynthesizeSpeechLongForm-Characters': 'long-form',
            'SynthesizeSpeechNeural-Characters': 'neural',
        }
        start_limits = {
            'standard': 5_000_000,
            'generative': 100_000,
            'long-form': 500_000,
            'neural': 1_000_000,
        }
        freetier_client = self.session.client('freetier')
        response = freetier_client.get_free_tier_usage(filter={
            'Dimensions': {
                'Key': 'SERVICE',
                'Values': ['Amazon Polly'],
                'MatchOptions': ['EQUALS']
            }
        })
        month = datetime.now().strftime('%Y-%m')
        quotas = self.provider.cached_quotas()
        if not quotas or quotas.get('month') != month:
            quotas = {
                'month': month,
                'engines': {x: {'used': 0, 'limit': y} for x, y in start_limits.items()}
            }
        if response['freeTierUsages']:
            for usage in response['freeTierUsages']:
                quotas['engines'][engines.get(usage['usageType'])] = {'used': usage['actualUsageAmount'], 'limit': usage['limit']}
        self.provider.quotas = json.dumps(quotas)
        db.session.commit()
        return quotas

    def check_quota(self, voice_id, text, update=True):
        if self.provider.exceed_quotas:
            return True
        text_length = len(text)
        quotas = self.get_quotas()
        engine, _ = self.parse_voice_id(voice_id)
        if engine in quotas.get('engines', {}):
            remaining = quotas['engines'][engine]['limit'] - quotas['engines'][engine]['used']
            if remaining >= text_length:
                if update:
                    quotas['engines'][engine]['used'] += text_length
                    self.provider.quotas = json.dumps(quotas)
                    db.session.commit()
                return True
        return False

    def quotas_text(self):
        quotas = self.provider.cached_quotas()
        lines = []
        for engine, data in quotas.get('engines', {}).items():
            remaining = data['limit'] - data['used']
            used_str = utils.summarize_number(data['used'])
            limit_str = utils.summarize_number(data['limit'])
            used_percentage = ((data['used'] / data['limit']) * 100) if data['limit'] else 100
            lines.append(f'{engine.title()} - {used_str} / {limit_str} ({used_percentage:.1f}% used)')
        return lines
