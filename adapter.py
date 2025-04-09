#!/usr/bin/env python
import os
import importlib
import configparser
import re

from smw_api_handler import SemanticMediaWikiApiHandler
from logger import Logger

import warnings  # dismiss the Unverified HTTPS request warning
# warnings.filterwarnings('ignore', message='Unverified HTTPS request')

class Adapter:
    def __init__(self):
        self.logger = Logger()
        self.config = configparser.ConfigParser()
        self.config.read(os.path.join(os.path.dirname(__file__), 'config/config.ini'))
        self.smw_api = SemanticMediaWikiApiHandler(self.config)
        self.smw_pages = {} # Dictionary of created wiki pages with name and content for response
        self.messages = [] # List with info, warnings and errors for response
        self.source = None

    def adapt(self, eln, id):
        self.logger.log_message('info', 'Call for Plugin {} with page id {}'.format(eln, id))

        # import and run plugin dynamically by determined by eln parameter
        self.source = importlib.import_module('plugins.' + eln.lower(), '.').Plugin(self.config, self)
        self.source.run(id)

        self.logger.log_runtime()

        # Response object contains adapter version, created smw pages and messages with info, warnings and errors
        response = {}
        response['version'] = self.config['Main']['version']
        response['smw_pages'] = self.smw_pages
        response['messages'] = self.messages
        return response

    # Creates a new SMW page with content in wiki syntax
    def create_smw_page(self, category, data):
        new_title = None
        text = None
        if category == 'Specimen':
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
        if self.smw_api.edit(new_title, text):
            self.logger.log_message('info', 'Page {} was created'.format(new_title))
            self.smw_pages[new_title] = text
        else:
            self.logger.log_message('error', 'Page {} was not created'.format(new_title))
        return new_title

    # Calculates index for the next page with a specific condition. E.g. Specimen, Protocols
    def get_next_smw_page_index(self, ask_condition):
        data = self.smw_api.ask('{}|limit=1|order=desc'.format(ask_condition))
        if data["query"]["results"]:
            page_name = next(iter(data["query"]["results"].values()))['fulltext']
            page_name_number =  re.search(r'(\d+)$', page_name).group(0)
            return int(page_name_number)+1
        else:
            return 1

    # add message to the response
    def add_message(self, type, text):
        self.messages.append({'type': type, 'text': text })

    @staticmethod
    def test(specimen, protocols, records):
        print('Specimen', specimen['Name'], ':\n', specimen, '\n')

        for i, protocol in enumerate(protocols):
            print('Protocol', protocol['Name'], ':\n', protocol, '\n')

        for i, record in enumerate(records):
            print('Record', record['Name'], ':\n', record, '\n')


