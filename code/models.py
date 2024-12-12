import json
import utils
import os.path
import settings
from users import User
from typing import List, Optional
from database import db
from datetime import datetime, date
from providers import edge, polly, googletts
from sqlalchemy.orm import relationship, Mapped, mapped_column

class Item(db.Model):
    __tablename__ = 'items'

    id: Mapped[int] = mapped_column(primary_key=True)
    created_date: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    user_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey('users.id'))
    url: Mapped[Optional[str]] = mapped_column(db.String(1000))
    title: Mapped[str] = mapped_column(db.String(500))
    author: Mapped[Optional[str]] = mapped_column(db.String(255))
    published_date: Mapped[Optional[date]] = mapped_column()
    subheadline: Mapped[Optional[str]] = mapped_column(db.Text)
    content: Mapped[str] = mapped_column(db.Text)
    voice: Mapped[str] = mapped_column(db.String(100))
    provider_type: Mapped[str] = mapped_column(db.String(20))
    provider_id: Mapped[int] = mapped_column(db.ForeignKey('providers.id'))
    duration_seconds: Mapped[Optional[int]] = mapped_column()
    audio_fname: Mapped[Optional[str]] = mapped_column(db.String(100))
    task_id: Mapped[Optional[str]] = mapped_column(db.String(36))

    user: Mapped['User'] = db.relationship('User', back_populates='items')
    provider: Mapped['Provider'] = relationship('Provider', back_populates='items')
    feed_items: Mapped[List['UserFeedItem']] = db.relationship(
        'UserFeedItem', cascade='all, delete-orphan', back_populates='item'
    )

    def audio_data(self):
        if self.audio_fname:
            fpath = os.path.join(settings.FILES_DIR, self.audio_fname)
            if os.path.exists(fpath):
                file_size = os.path.getsize(fpath)
                return {
                    'url': f'/files/{self.audio_fname}',
                    'size_bytes': file_size,
                    'size': utils.convert_size(file_size),
                    'duration_seconds': self.duration_seconds,
                    'duration_formatted': self.duration_formatted(),
                    'voice': f'{self.provider_type} - {self.voice}',
                }
        return None

    def duration_formatted(self):
        if self.duration_seconds:
            return utils.convert_seconds_to_hhmm(self.duration_seconds)
        return ''

User.items = db.relationship('Item', back_populates='user')

class UserFeedItem(db.Model):
    __tablename__ = 'user_feed_items'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey('users.id'))
    item_id: Mapped[int] = mapped_column(db.ForeignKey('items.id'))
    added_date: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    user: Mapped['User'] = db.relationship('User', back_populates='feed_items')
    item: Mapped['Item'] = db.relationship('Item', back_populates='feed_items')

User.feed_items = db.relationship('UserFeedItem', cascade='all, delete-orphan', back_populates='user')

class Provider(db.Model):
    __tablename__ = 'providers'

    id: Mapped[int] = mapped_column(primary_key=True)
    added_date: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    name: Mapped[str] = mapped_column(db.String(100))
    provider: Mapped[str] = mapped_column(db.String(100))
    settings: Mapped[Optional[str]] = mapped_column(db.Text)
    voices: Mapped[Optional[str]] = mapped_column(db.Text)
    quotas: Mapped[Optional[str]] = mapped_column(db.Text)
    exceed_quotas: Mapped[bool] = mapped_column(default=False)

    items: Mapped[List['Item']] = db.relationship('Item', back_populates='provider')

    @classmethod
    def settings_options(cls):
        return {
            'edge': {
                'name': 'Edge',
            },
            'polly': {
                'name': 'Amazon Polly',
                'fields': ['aws_secret_key', 'aws_access_key', 'region_name', 's3_bucket_name'],
            },
            'google-tts': {
                'name': 'Google TTS',
                'fields': ['credentials', 'bucket_name', 'bucket_region'],
            }
        }

    def parsed_settings(self):
        settings = {}
        if self.settings:
            settings = json.loads(self.settings) or {}
        fields = self.settings_options().get(self.provider, {}).get('fields', [])
        data = {k: settings.get(k, '') for k in fields}
        return data

    def get_provider_instance(self):
        if self.provider == 'polly':
            return polly.Polly(self)
        elif self.provider == 'edge':
            return edge.Edge(self)
        elif self.provider == 'google-tts':
            return googletts.GoogleTTS(self)

    def cached_quotas(self):
        if self.quotas:
            return json.loads(self.quotas)
        return {}

    def get_name(self):
        provider_name = self.settings_options().get(self.provider, {}).get('name')
        if self.name and provider_name != self.name:
            return f'{provider_name} - {self.name}'
        return provider_name
