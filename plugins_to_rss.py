import argparse
import logging
from string import Template
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
import requests
from requests.exceptions import HTTPError
from feedgen.feed import FeedGenerator


BASE_PLUGIN_URL = Template('https://grafana.com/api/plugins/$slug')
BASE_VERSION_URL = Template('https://grafana.com/api/plugins/$slug/versions')
BASE_CATALOG_URL = Template('https://grafana.com/grafana/plugins/$slug/')

SESS_USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15'

def retrieve_json(session, url: str) -> Any:

    response = session.get(url)
    try:
        response.raise_for_status()
    except HTTPError as e:
        logging.error(f'URL returned {e.response.status_code} - {e.response.content}')
        raise
    return response.json()


def generate_feed(plugin: str, feed_dir: str) -> None:

    plugin_catalog_url = BASE_CATALOG_URL.substitute(slug=plugin)

    session = requests.Session()
    session.headers.update({'User-Agent': SESS_USER_AGENT,
                            'Accept' : 'application/json',
                            'Referer' : plugin_catalog_url})

    # Get the plugin information for the channel
    logging.info('Retrieving plugin information...')
    data = retrieve_json(session, BASE_PLUGIN_URL.substitute(slug=plugin))

    fg = FeedGenerator()
    fg.title(data['name'])
    # Make sure to always have a link, otherwise the RSS file is invalid
    if (link := data.get('url')) is None:
        link = plugin_catalog_url
    fg.link(href=link, rel='alternate')
    fg.description(data.get('description'))
    fg.lastBuildDate(datetime.now(timezone.utc))
    fg.updated(data.get('updatedAt'))

    for keyword in data.get('keywords', []):
        fg.category(term=keyword)

    # Get the tag details for the individual items
    logging.info('Retrieving version details...')
    version_data = retrieve_json(session, BASE_VERSION_URL.substitute(slug=plugin))

    logging.debug(f'Found {len(version_data)} tags.')
    for version in version_data['items']:
        fe = fg.add_entry()
        fe.title(f'{data['name']} {version['version']}')
        fe.link(href=plugin_catalog_url)
        fe.published(version.get('createdAt'))
        fe.updated(version.get('updatedAt'))
        
        fe.description(data.get('changelog'))
        fe.guid(f'{version['pluginId']}-{version['id']}', permalink=False)


    output_file = Path(feed_dir,f'{plugin.replace('/', '_')}.xml')
    logging.info(f'Writing to {output_file}...')
    fg.rss_file(output_file)
    logging.info(f'RSS feed saved.')


def process_repo_list(filename:str, feed_dir:str) -> None:
    # Open plugins list file, each line is a separate entry
    with open (filename) as f:
        plugins: List[str] = f.read().strip().splitlines()
    # Make sure there are no tailing spaces
    plugins = [strip(plugin) for plugin in plugins]
    logging.info(f'Found {len(plugins)} plugins to process.')
    
    # Ensure folder exists
    Path(feed_dir).mkdir(exist_ok=True)

    for plugin in plugins:
        try:
            logging.info(f'Generating feed for {plugin}...')
            generate_feed(plugin, feed_dir)
        except Exception as e:
            logging.error(f'Failed to generate feed for {plugin}: {e!r}')
    logging.info('Finished generating feeds.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate RSS feeds for Grafana plugins.')
    parser.add_argument('filename', help='Filename containing list of repositories')
    parser.add_argument('--feed-dir', help='Folder to output the resulting XML files', default='feeds')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()

    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
    # Avoid logging from requests
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    # Verify if file exists
    if not Path(args.filename).is_file():
        logging.error(f'File not found: {args.filename}')
        exit(1)

    process_repo_list(args.filename, args.feed_dir)
