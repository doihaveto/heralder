import settings
import xml.etree.ElementTree as ET
from xml.dom import minidom
from urllib.parse import quote

def generate_rss_feed(items):
    rss = ET.Element('rss')
    rss.set('xmlns:podcast', 'https://github.com/Podcastindex-org/podcast-namespace/blob/main/docs/1.0.md')
    rss.set('xmlns:itunes', 'http://www.itunes.com/dtds/podcast-1.0.dtd')
    rss.set('version', '2.0')
    channel = ET.SubElement(rss, 'channel')
    podcast_locked = ET.SubElement(channel, 'podcast:locked')
    podcast_locked.set('owner', 'podcastowner@example.com')
    podcast_locked.text = 'yes'
    image = ET.SubElement(channel, f'itunes:image')
    image.set('href', f'{settings.URL}/static/rss.jpg')
    title = ET.SubElement(channel, 'title')
    title.text = 'Heralder'
    titles = []
    for item, added_date in items:
        item_el = ET.SubElement(channel, 'item')
        item_title = ET.SubElement(item_el, 'title')
        item_title.text = item.title
        if item.author:
            item_title.text = f'{item.title} - {item.author}'
        if item_title.text in titles:
            item_title.text += ' (older)'
        titles.append(item_title.text)
        item_description = ET.SubElement(item_el, 'description')
        description = [item.title]
        if item.subheadline:
            description.append(item.subheadline)
        if item.author:
            description.append(f'By {item.author}')
        if item.published_date:
            description.append(f'Published on {item.published_date.strftime("%Y-%m-%d")}')
        if item.url:
            description.append(f'Source: {item.url}')
        item_description.text = '\n\n'.join(description)
        item_guid = ET.SubElement(item_el, 'guid')
        item_guid.text = str(item.id)
        if item.duration_seconds:
            itunes_duration = ET.SubElement(item_el, 'itunes:duration')
            itunes_duration.text = str(int(item.duration_seconds))
        item_pub_date = ET.SubElement(item_el, 'pubDate')
        item_pub_date.text = added_date.strftime('%a, %d %b %Y %H:%M:%S GMT')
        audio_data = item.audio_data()
        audio_url = f'{settings.URL}' + audio_data['url']
        enclosure = ET.SubElement(item_el, 'enclosure')
        enclosure.set('url', audio_url)
        enclosure.set('type', 'audio/mpeg')
        enclosure.set('length', str(audio_data['size_bytes']))
    rss_string = ET.tostring(rss, encoding='utf-8')
    dom = minidom.parseString(rss_string)
    return dom.toprettyxml(indent='  ')
