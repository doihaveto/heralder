import rss
import json
import users
import tasks
import utils
import os.path
import settings
from flask import Flask, render_template, redirect, url_for, request, flash, send_file, jsonify, session, make_response
from models import Item, UserFeedItem, Provider
from database import db
from datetime import datetime
from providers import edge as ttsp
from celery_app import celery_init_app
from sqlalchemy import desc
from flask_login import LoginManager, login_required, current_user
from celery.result import AsyncResult
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

app = Flask('tts')
app.register_blueprint(users.blueprint)
app.secret_key = settings.SECRET_KEY

# Configure the SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = settings.DB_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_TIME_LIMIT'] = None

# Initialise celery
celery = celery_init_app(app)

# Initialise the database and migrations
db.init_app(app)
migrate = Migrate(app, db)

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'users.login'
login_manager.user_loader(users.load_user)

csrf = CSRFProtect()
csrf.init_app(app)

@app.route('/')
@login_required
def index():
    return render_template('base.html')

@app.route('/dashboard/')
@login_required
def dashboard():
    if not current_user.is_superuser:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))
    return render_template('dashboard.html')

@app.route('/items/add/', endpoint='item_add')
@app.route('/items/<int:item_id>/', endpoint='item_view')
@app.route('/items/<int:item_id>/edit/', endpoint='item_edit')
@login_required
def manage_item(item_id=None):
    item = None
    if item_id:
        item = Item.query.get_or_404(item_id)
    providers = []
    if request.args.get('cache') and not item:
        cache_hash = request.args.get('cache')
        cached_data = utils.cache_get(f'ext_{cache_hash}')
        if cached_data:
            cached_data = json.loads(cached_data)
            published_date = None
            if cached_data.get('published_date'):
                try:
                    published_date = datetime.strptime(cached_data.get('published_date'), '%Y-%m-%d').date()
                except:
                    pass
            item = Item(
                title=cached_data.get('title') or '',
                author=cached_data.get('author') or '',
                url=cached_data.get('url') or '',
                published_date=published_date,
                subheadline=cached_data.get('subheadline') or '',
                content=cached_data.get('content') or '',
            )
    for provider in Provider.query.all():
        ttsp = provider.get_provider_instance()
        providers.append({
            'id': provider.id,
            'name': provider.get_name(),
            'voices': ttsp.get_voices(),
            'quotas_text': ttsp.quotas_text(),
        })
    return render_template('manage_item.html', providers=providers, item=item)

@app.route('/api/items/', methods=['POST'])
@login_required
def api_item_action():
    item = None
    if request.json.get('item_id'):
        item = Item.query.get(request.json.get('item_id'))
        if not item:
            return jsonify({'message': 'This item does not exist'}), 400
        if request.json.get('action') == 'delete':
            if current_user.id == item.user_id or current_user.is_superuser:
                db.session.delete(item)
                db.session.commit()
                return jsonify({'message': 'Item deleted'})
            else:
                return jsonify({'message': 'Insufficient privileges'}), 400
    voice = request.json.get('voice')
    title = request.json.get('title')
    subheadline = request.json.get('subheadline')
    author = request.json.get('author')
    url = request.json.get('url')
    content = request.json.get('content')
    provider_id = request.json.get('provider')
    generate = request.json.get('generate')
    if generate:
        if not provider_id:
            return jsonify({'message': 'Missing provider'}), 400
        provider = Provider.query.get(provider_id)
        if not provider:
            return jsonify({'message': 'This provider does not exist'}), 400
        if not voice:
            return jsonify({'message': 'Invalid voice'}), 400
    else:
        provider = Provider.query.first()
        provider_id = provider.id
        voice = ''
    if not title:
        return jsonify({'message': 'Missing title'}), 400
    if not content:
        return jsonify({'message': 'Missing content'}), 400
    published_date = None
    if request.json.get('published_date'):
        published_date = datetime.strptime(request.json.get('published_date'), '%Y-%m-%d').date()
    if item:
        item.title = title
        item.author = author or ''
        item.url = url or ''
        item.published_date = published_date
        item.subheadline = subheadline
        item.content = content
        item.voice = voice
        item.provider_id = provider.id
        item.provider_type = provider.provider
    else:
        item = Item(
            title=title,
            user_id=current_user.id,
            author=author or '',
            url=url or '',
            published_date=published_date,
            subheadline=subheadline,
            content=content,
            voice=voice,
            provider_id=provider.id,
            provider_type=provider.provider,
        )
        db.session.add(item)
        db.session.commit()
        user_feed_item = UserFeedItem(user_id=current_user.id, item_id=item.id)
        db.session.add(user_feed_item)
    if generate:
        task = tasks.generate_audio.delay(item.id)
        item.task_id = task.id
    db.session.commit()
    return jsonify({'item_id': item.id})

@app.route('/api/items/check')
@login_required
def api_item_check_progress():
    item_id = request.args.get('item_id')
    item = Item.query.get(item_id)
    if not item or not item.task_id:
        return jsonify({
            'message': 'No active tasks for this item',
            'state': 'INVALID'
        })
    task_result = AsyncResult(item.task_id, app=celery)
    if task_result.state == 'PENDING':
        return jsonify({
            'message': 'Task is running',
            'state': task_result.state
        })
    elif task_result.state == 'SUCCESS':
        item.task_id = None
        db.session.commit()
        return jsonify({
            'result': task_result.result,
            'message': 'Task completed successfully',
            'state': task_result.state,
            'audio_data': item.audio_data(),
        })
    elif task_result.state == 'FAILURE':
        return jsonify({
            'message': f'Task failed with exception: {task_result.result}',
            'traceback': str(task_result.result.__traceback__),
            'state': task_result.state
        })
    else:
        # Other states: RETRY, REVOKED, etc.
        return jsonify({
            'message': f'Task is in {task_result.state} state',
            'state': task_result.state
        })

@app.route('/voice-sample/', methods=['POST'])
@login_required
def sample_voice():
    provider_id = request.json.get('provider')
    provider = Provider.query.get(provider_id)
    if not provider:
        return jsonify({'message': 'This provider does not exist'}), 400
    voice = request.json.get('voice')
    text = request.json.get('text')
    if not text:
        text = 'This is how this voice sounds. Not too bad, is it?'
    ttsp = provider.get_provider_instance()
    fhash = utils.short_hash(f'{text}-{voice}-{provider.provider}')
    audio_dst = os.path.join(settings.SAMPLES_DIR, f'{fhash}.mp3')
    if not os.path.exists(audio_dst):
        if not ttsp.check_quota(voice, text):
            return jsonify({'message': f'Limit exceeded for this voice'}), 500
        try:
            ttsp.tts(text, voice, audio_dst)
        except Exception as e:
            return jsonify({'message': f'Unexpected error: {e}'}), 500
    return jsonify({'url': f'/files/samples/{fhash}.mp3'})

@app.route('/refresh-quotas/', methods=['POST'])
@login_required
def refresh_quotas():
    provider_id = request.json.get('provider')
    provider = Provider.query.get(provider_id)
    if not provider:
        return jsonify({'message': 'This provider does not exist'}), 400
    ttsp = provider.get_provider_instance()
    ttsp.get_quotas()
    quotas_text = ttsp.quotas_text()
    return jsonify({'provider_id': provider.id, 'quotas_text': quotas_text})

@app.route('/items/')
@login_required
def list_items():
    total_items = Item.query.count()
    per_page = 50
    page = utils.get_page(request, total_items, per_page)
    items = Item.query.order_by(Item.id.desc()).offset(page.start_idx).limit(per_page).all()
    item_ids = [x.id for x in items]
    feed_item_ids = db.session.scalars(db.session.query(UserFeedItem.item_id).filter(UserFeedItem.user_id == current_user.id, UserFeedItem.item_id.in_(item_ids))).all()
    return render_template('list_items.html', page=page, items=items, feed_item_ids=feed_item_ids)

@app.route('/feed/')
@login_required
def list_feed_items():
    total_items = UserFeedItem.query.filter(UserFeedItem.user_id == current_user.id).count()
    per_page = 50
    page = utils.get_page(request, total_items, per_page)
    items = (
        db.session.query(Item)
        .join(UserFeedItem, UserFeedItem.item_id == Item.id)
        .filter(UserFeedItem.user_id == current_user.id)
        .order_by(UserFeedItem.id.desc())
        .offset(page.start_idx)
        .limit(per_page)
        .all()
    )
    feed_item_ids = [x.id for x in items]
    rss_key = utils.generate_key(current_user.id)
    return render_template('list_items.html', page=page, items=items, feed_item_ids=feed_item_ids, rss_key=rss_key, url=settings.URL)

@app.route('/feed/item', methods=['POST'])
@login_required
def modify_feed_item():
    item_id = request.json.get('item_id')
    action = request.json.get('action')
    if not item_id or action not in ('add', 'remove'):
        return jsonify({'error': 'Invalid input'}), 400
    if action == 'add':
        if not UserFeedItem.query.filter_by(user_id=current_user.id, item_id=item_id).first():
            new_feed_item = UserFeedItem(user_id=current_user.id, item_id=item_id)
            db.session.add(new_feed_item)
            db.session.commit()
            return jsonify({'message': 'Item added to feed'}), 200
        else:
            return jsonify({'message': 'Item already in feed'}), 200
    elif action == 'remove':
        feed_item = UserFeedItem.query.filter_by(user_id=current_user.id, item_id=item_id).first()
        if feed_item:
            db.session.delete(feed_item)
            db.session.commit()
            return jsonify({'message': 'Item removed from feed'}), 200
        else:
            return jsonify({'message': 'Item not found in feed'}), 200
    return jsonify({'error': 'Action not recognized'}), 400

@app.route('/rss/<user_id>/<key>.rss')
def user_rss(user_id, key):
    user = users.User.query.get_or_404(user_id)
    if not user or key != utils.generate_key(user.id):
        return 'Not found', 404
    items = (
        db.session.query(Item, UserFeedItem.added_date)
        .join(UserFeedItem, UserFeedItem.item_id == Item.id)
        .filter(
            UserFeedItem.user_id == user.id,
            Item.audio_fname.isnot(None)  # Exclude items with audio_fname as None
        )
        .order_by(UserFeedItem.id.desc())
        .all()
    )
    rss_content = rss.generate_rss_feed(items)
    response = make_response(rss_content)
    response.headers['Content-Type'] = 'application/xml'
    return response

@app.route('/providers/', methods=['GET', 'POST'])
@login_required
def list_providers():
    if not current_user.is_superuser:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form['name']
        provider = request.form['provider']
        new_provider = Provider(
            name=name,
            provider=provider,
        )
        db.session.add(new_provider)
        db.session.commit()
        flash('Provider added successfully', 'success')
        return redirect(url_for('manage_provider', provider_id=new_provider.id))
    settings_options = Provider.settings_options()
    providers = Provider.query.all()
    return render_template('list_providers.html', providers=providers, settings_options=settings_options)

@app.route('/providers/<int:provider_id>/', methods=['GET', 'POST'])
@login_required
def manage_provider(provider_id):
    if not current_user.is_superuser:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))
    provider = Provider.query.get_or_404(provider_id)
    settings_options = Provider.settings_options()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'edit':
            provider.name = request.form['name']
            provider.exceed_quotas = request.form.get('exceed_quotas') == 'on'
            settings = {}
            if provider.provider in settings_options and settings_options[provider.provider].get('fields'):
                for key in settings_options[provider.provider]['fields']:
                    settings[key] = request.form.get(key, '')
            if provider.provider == 'polly' and not settings.get('s3_bucket_name'):
                bucket_random = utils.generate_random_string(10)
                settings['s3_bucket_name'] = f'heralder-{bucket_random}'
            if provider.provider == 'google-tts' and not settings.get('bucket_name'):
                bucket_random = utils.generate_random_string(10)
                settings['bucket_name'] = f'heralder-{bucket_random}'
            provider.settings = json.dumps(settings)
            db.session.commit()
            tts_provider = provider.get_provider_instance()
            try:
                tts_provider.setup()
            except Exception as e:
                flash(f'Failed to setup provider: {e}', 'error')
            else:
                flash('Provider updated successfully', 'success')
            return redirect(url_for('manage_provider', provider_id=provider_id))
        elif action == 'delete':
            db.session.delete(provider)
            db.session.commit()
            flash('Provider deleted successfully', 'success')
            return redirect(url_for('list_providers'))
    return render_template('manage_provider.html', provider=provider)

@app.route('/api/ext/submit', methods=['POST'])
@csrf.exempt
def api_ext_submit_item():
    if not current_user:
        return redirect(url_for('users.login'))
    data = {
        'title': request.form.get('title'),
        'subheadline': request.form.get('subheadline'),
        'author': request.form.get('author'),
        'url': request.form.get('url'),
        'content': request.form.get('content'),
        'published_date': request.form.get('publishedDate'),
    }
    cache_hash = utils.generate_random_string(8)
    utils.cache_set(f'ext_{cache_hash}', json.dumps(data), 60*60)
    return redirect(url_for('item_add') + f'?cache={cache_hash}')

if __name__ == '__main__':
    if not Provider.query.count():
        new_provider = Provider(
            name='Edge',
            provider='edge',
        )
        db.session.add(new_provider)
        db.session.commit()
        tts_provider = provider.get_provider_instance()
        try:
            tts_provider.setup()
        except:
            pass
    app.run(debug=False)
