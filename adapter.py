#!/usr/bin/env python
import os
import importlib
import configparser
import re
import datetime
import platform

from smw_api_handler import SemanticMediaWikiApiHandler
from logger import Logger

import warnings  # dismiss the Unverified HTTPS request warning
# warnings.filterwarnings('ignore', message='Unverified HTTPS request')

class Adapter:
    def __init__(self):
        self.logger = Logger()
        self.config = configparser.ConfigParser(interpolation=None)
        # Preserve case for option names
        self.config.optionxform = str
        self.config.read(os.path.join(os.path.dirname(__file__), 'config/config.ini'))
        self.debug_mode = self.config.get('Main', 'debug_mode', fallback='off').lower() == 'on'
        self.smw_api = SemanticMediaWikiApiHandler(self.config)
        self.smw_pages = {} # Dictionary of created wiki pages with name and content for response
        self.messages = [] # List with info, warnings and errors for response
        self.source = None
        self.user = None # Current user from MediaWiki
        self.page_index_cache = {} # Cache for page indices to avoid race conditions

    def adapt(self, eln, id, user=None):
        self.user = user
        self.logger.log_message('info', 'Call for Plugin {} with page id {} by user {}'.format(eln, id, user if user else 'unknown'))

        try:
            # import and run plugin dynamically by determined by eln parameter
            # Convert plugin name to lowercase for file import
            plugin_module_name = eln.lower().replace('-', '-')  # Keep hyphens for file name
            module_path = 'plugins.' + plugin_module_name

            # Use importlib with __import__ for hyphenated modules
            plugin_module = __import__(module_path, fromlist=['Plugin'])
            self.source = plugin_module.Plugin(self.config, self)
            self.source.run(id)

            self.logger.log_runtime()

            # Response object contains adapter version, created smw pages and messages with info, warnings and errors
            response = {}
            response['version'] = self.config['Main']['version']
            response['smw_pages'] = self.smw_pages
            response['messages'] = self.messages
            return response
        except Exception as e:
            import traceback
            error_msg = 'Plugin {} failed: {}\n{}'.format(eln, str(e), traceback.format_exc())
            self.logger.log_message('error', error_msg)

            # Return error response
            response = {}
            response['version'] = self.config['Main']['version']
            response['smw_pages'] = {}
            response['messages'] = [{'type': 'error', 'text': str(e)}]
            return response

    # Creates a new SMW page with content in wiki syntax
    def create_smw_page(self, category, data):
        new_title = None
        text = None
        if category == 'Specimen':
            # Check if specimen already exists
            existing_specimen = self.specimen_exists(data['Description'], data['Person'])
            if existing_specimen:
                self.logger.log_message('info', 'Reusing existing specimen: {}'.format(existing_specimen))
                return existing_specimen

            # Create new specimen
            next_number = self.get_next_smw_page_index('[[Category:Specimen]]')
            new_title = "S{:05}".format(next_number)
            text = '{{{{Specimen|Description={0}|Person={1}|Material={2}}}}}'.format(data['Description'], data['Person'], data['Material']) # format replaces {{ with {
        elif category == 'Protocol':
            next_number = self.get_next_smw_page_index('[[Category:Protocol]][[ProtocolType::{}]]'.format(data['ProtocolType']))
            new_title = "P{}{:04}".format(data['ProtocolType'], next_number)
            text = '{{{{Protocol|ProtocolType={0}|Date={1}|Person={2}|SpecimenList={3}|Origin={4}|OriginInternalIdentifier={5}}}}}'.format(data['ProtocolType'], data['Date'], data['Person'], data['SpecimenList'], data['Origin'], data['OriginInternalIdentifier']) # format replaces {{ with {
        elif category == 'Record':
            new_title = "R_{}_{}".format(data['Protocol'], data['Specimen'])
            record_text = '{{{{Record|Protocol={0}|Specimen={1}}}}}'.format(data['Protocol'], data['Specimen']) # format replaces {{ with {
            data_pairs = []
            for key, value in data['Data'].items():
                data_pairs.append(f"{key}={value}")
            subobject_text = '{{{{#subobject:Data|{}}}}}'.format('|'.join(data_pairs))
            text = record_text+subobject_text

        self.logger.log_message('info', 'Create SMW page of category {} with title {}'.format(category, new_title))

        if self.debug_mode:
            self.logger.log_message('info', '[DEBUG MODE] Page {} would be created with content: {}'.format(new_title, text[:100]))
            self.smw_pages[new_title] = text
        else:
            if self.smw_api.edit(new_title, text):
                self.logger.log_message('info', 'Page {} was created'.format(new_title))
                self.smw_pages[new_title] = text
            else:
                self.logger.log_message('error', 'Page {} was not created'.format(new_title))
        return new_title

    # Calculates index for the next page with a specific condition. E.g. Specimen, Protocols
    def get_next_smw_page_index(self, ask_condition):
        # Check cache first
        if ask_condition in self.page_index_cache:
            # Increment cached value and return
            self.page_index_cache[ask_condition] += 1
            return self.page_index_cache[ask_condition]

        # Query wiki for current highest index
        data = self.smw_api.ask('{}|limit=1|order=desc'.format(ask_condition))
        if data["query"]["results"]:
            page_name = next(iter(data["query"]["results"].values()))['fulltext']
            page_name_number =  re.search(r'(\d+)$', page_name).group(0)
            next_index = int(page_name_number) + 1
        else:
            next_index = 1

        # Cache the value
        self.page_index_cache[ask_condition] = next_index
        return next_index

    def specimen_exists(self, description, person):
        """Check if specimen exists (case-insensitive). Returns specimen name if exists"""
        try:
            ask_condition = '[[Category:Specimen]][[Description::{}]][[Person::{}]]'.format(
                description, person
            )
            data = self.smw_api.ask('{}|limit=1'.format(ask_condition))
            if data and "query" in data and "results" in data["query"]:
                results = data["query"]["results"]
                if len(results) > 0:
                    return next(iter(results.values()))['fulltext']
            return None
        except Exception as e:
            self.logger.log_message('warning', 'Could not check for existing specimen: {}'.format(str(e)))
            return None

    # add message to the response
    def add_message(self, type, text):
        self.messages.append({'type': type, 'text': text })

    # get service status information
    def get_status(self):
        status = {
            'status': 'running',
            'timestamp': datetime.datetime.now().isoformat(),
            'version': self.config.get('Main', 'version'),
            'platform': platform.system(),
            'python_version': platform.python_version(),
        }
        
        # Test SMW API connection
        try:
            smw_status = self.smw_api.test_connection()
            status['smw_connection'] = 'connected' if smw_status else 'disconnected'
        except Exception as e:
            status['smw_connection'] = 'error'
            status['smw_error'] = str(e)
        
        # Check available plugins
        plugins_dir = os.path.join(os.path.dirname(__file__), 'plugins')
        available_plugins = []
        for file in os.listdir(plugins_dir):
            if file.endswith('.py') and file != 'template.py' and not file.startswith('__'):
                plugin_name = file[:-3]  # remove .py extension
                available_plugins.append(plugin_name)
        status['available_plugins'] = available_plugins
        
        # Check enabled plugins from config with their types
        enabled_plugins = []
        plugins_with_types = {}
        if self.config.has_section('Plugins'):
            # Use config.options() to get original case-sensitive option names
            for plugin_key in self.config.options('Plugins'):
                if self.config.get('Plugins', plugin_key).lower() == 'on':
                    enabled_plugins.append(plugin_key)
                    # Get plugin type from its config section (default: url)
                    plugin_type = 'url'  # default
                    
                    if self.config.has_section(plugin_key):
                        plugin_type = self.config.get(plugin_key, 'type', fallback='url')
                        
                    plugins_with_types[plugin_key] = {
                        'type': plugin_type,
                        'name': plugin_key
                    }
        status['enabled_plugins'] = enabled_plugins
        status['plugins'] = plugins_with_types
        
        # Get upload path and convert to absolute path
        upload_path = self.config.get('Main', 'upload_path', fallback='./uploads')
        if not os.path.isabs(upload_path):
            # Convert relative path to absolute path based on script directory
            upload_path = os.path.join(os.path.dirname(__file__), upload_path)
        status['upload_path'] = os.path.abspath(upload_path)
        
        return status

    @staticmethod
    def test(specimen, protocols, records):
        print('Specimen', specimen['Name'], ':\n', specimen, '\n')

        for i, protocol in enumerate(protocols):
            print('Protocol', protocol['Name'], ':\n', protocol, '\n')

        for i, record in enumerate(records):
            print('Record', record['Name'], ':\n', record, '\n')


