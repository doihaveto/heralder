import os
import audio
import utils
import logging
import settings
import tempfile
from celery import shared_task
from models import Item, Provider
from database import db

logger = logging.getLogger(__name__)

@shared_task
def generate_audio(item_id):
    if utils.cache_get(f'generate_{item_id}'):
        raise Exception('Already generating audio for this item')
    utils.cache_set(f'generate_{item_id}', True, 600)
    try:
        item = Item.query.get(item_id)
        ttsp = item.provider.get_provider_instance()
        if ttsp.ssml_capable:
            text = utils.item_to_ssml(item, item.provider.provider)
        else:
            segments = utils.item_to_segments(item)
            text = '\n'.join([x[0] for x in segments])
        audio_hash = utils.short_hash(f'{item.id}-{item.voice}-{item.provider_type}-{text}')
        audio_fname = f'{audio_hash}.mp3'
        audio_dst = os.path.join(settings.FILES_DIR, audio_fname)
        if os.path.exists(audio_dst):
            logger.info(f'Audio file already exists for item {item.id} - {audio_fname}')
            item.audio_fname = audio_fname
            db.session.commit()
            return
        if not ttsp.check_quota(item.voice, text):
            raise Exception('Text exceeds provider quota, aborting')
        if ttsp.ssml_capable:
            ttsp.tts(text, item.voice, audio_dst)
            if not os.path.exists(audio_dst):
                raise Exception(f'Error generating audio - unexpected error (missing file)')
        else:
            temp_dir = tempfile.TemporaryDirectory(delete=False)
            new_segments = []
            for idx, (text, pause_before, pause_after) in enumerate(segments):
                taudio_dst = os.path.join(temp_dir.name, f'{idx}.mp3')
                ttsp.tts(text, item.voice, taudio_dst)
                if not os.path.exists(taudio_dst):
                    raise Exception(f'Error generating audio - unexpected error - {text}')
                elif not os.path.getsize(taudio_dst):
                    raise Exception(f'Error generating audio - unexpected error (file is empty) - {text}')
                new_segments.append((taudio_dst, pause_before, pause_after))
            audio.merge_audio_with_pauses(new_segments, audio_dst)
        item = Item.query.get(item_id)
        item.duration_seconds = audio.get_mp3_duration(audio_dst)
        item.audio_fname = audio_fname
        db.session.commit()
    except:
        raise
    finally:
        utils.cache_delete(f'generate_{item_id}')
