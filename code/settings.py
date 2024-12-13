import os
import shutil

with open('/data/.secret_key') as f:
    SECRET_KEY = f.read()

REDIS_HOSTNAME = os.environ.get('REDIS_HOSTNAME', 'redis')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
DATA_DIR = os.environ.get('DATA_DIR', '/data')
FILES_DIR = os.path.join(DATA_DIR, 'files')
SAMPLES_DIR = os.path.join(FILES_DIR, 'samples')
LOGS_DIR = os.path.join(DATA_DIR, 'logs')
URL = os.environ.get('URL', 'http://localhost:6468')
MEDIA_URL = '/media/'
DB_URI = 'sqlite:////data/app.db'

# celery settings
broker_url = f'redis://{REDIS_HOSTNAME}:{REDIS_PORT}/{REDIS_DB}'
result_backend = f'redis://{REDIS_HOSTNAME}:{REDIS_PORT}/{REDIS_DB}'

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(SAMPLES_DIR, exist_ok=True)
