import elabapi_python
import pandas as pd
from bs4 import BeautifulSoup
from elabapi_python.rest import ApiException
import json

from adapter import Adapter
import datetime
from io import StringIO

class Plugin:
    def __init__(self, config, adapter):
        self.name = 'eLabFTW'
        self.config = config
        self.adapter = adapter

    def run(self, id):
        elab_experiment = self.get_elab_experiment(id)
        if elab_experiment:
            elab_protocols = self.get_elab_protocols(elab_experiment)
            if len(elab_protocols) == 0:
                print(json.dumps(elab_protocols, indent=4))
                print('test')
                return None
        else:
            return None

        # extract specimen creator from first experiment table
        specimen_person = self.get_experiment_value_with_mapping(elab_protocols[0], 'person', '')

        # only one specimen per eLabFTW page
        specimen = {}
        specimen['Description'] = self.get_experiment_value_with_mapping(elab_protocols[0], 'specimen_description', '')
        specimen['Person'] = specimen_person
        specimen['Material'] = '?' #todo: extend elab template by material
        specimen['Name'] = self.adapter.create_smw_page('Specimen', specimen)

        protocols = []
        records = []
        for i, elab_protocol in enumerate(elab_protocols):
            # extract date from experiment
            date_string = self.get_experiment_value_with_mapping(elab_protocols[i], 'date', '')
            formatted_date = Plugin.format_experiment_date(date_string)
            if not formatted_date:
                formatted_date = Plugin.format_experiment_date(elab_experiment.created_at)
                self.adapter.logger.log_message('warning', 'unable to format date: {}'.format(date_string))

            protocol = {}
            protocol['ProtocolType'] = self.get_experiment_value_with_mapping(elab_protocols[i], 'experiment', 'INFELN')
            protocol['Date'] = formatted_date
            protocol['Person'] = self.get_experiment_value_with_mapping(elab_protocols[i], 'person', '')
            protocol['SpecimenList'] = specimen['Name']
            protocol['Origin'] = self.name
            protocol['OriginInternalIdentifier'] = id
            protocols.append(protocol)
            protocol['Name'] = self.adapter.create_smw_page('Protocol', protocol)

            record = {}
            record['Specimen'] = specimen['Name']
            record['Protocol'] = protocol['Name']
            record['Data'] = {}
            for parameter, value in elab_protocol.items():
                parameter, value = Plugin.correct_unit(parameter, value)
                record['Data'][parameter] = value

            records.append(record)
            record['Name'] = self.adapter.create_smw_page('Record', record)

        Adapter.test(specimen, protocols, records)

    def get_elab_experiment(self, experiment_id):

        # Configure the api client
        configuration = elabapi_python.Configuration()
        configuration.api_key['api_key'] = self.config[self.name]['api_key']
        configuration.api_key_prefix['api_key'] = 'Authorization'
        configuration.host = self.config['eLabFTW']['api_url']
        configuration.debug = False
        configuration.verify_ssl = False

        # create an instance of the API class
        api_client = elabapi_python.ApiClient(configuration)
        # fix issue with Authorization header not being properly set by the generated lib
        api_client.set_default_header(header_name='Authorization', header_value=self.config[self.name]['api_key'])

        # create an instance of Experiments
        experiments_api = elabapi_python.ExperimentsApi(api_client)

        # get experiment with ID
        try:
            exp = experiments_api.get_experiment(experiment_id)
            self.adapter.logger.log_message('info', 'eLabApi call for experiment with id {} successfull'.format(experiment_id))
            self.adapter.logger.log_runtime()
            return exp
        except ApiException as e:

            error_json = json.loads(e.body.decode('utf-8'))  # Decode and load as JSON
            self.adapter.logger.log_message('error', 'eLabApi returned http status {} - {}'.format(error_json.get('code'), error_json.get('message')))
            self.adapter.add_message('error', 'eLabApi returned http status {} - {}'.format(error_json.get('code'), error_json.get('message')))

            return None

    def get_elab_protocols(self, elab_experiment):
        soup = BeautifulSoup(elab_experiment.body, 'html.parser')

        # Extract all tables
        tables = soup.find_all('table')
        if len(tables) == 0:
            self.adapter.add_message('error', 'No table found on page. Protocols must be provided in a table format, with one column for parameters and another for their corresponding values.')

        # Process tables with exactly two columns and create dictionaries
        all_table_dicts = []
        for table in tables:
            # Wrap the HTML string in StringIO
            table_html = str(table)
            table_io = StringIO(table_html)

            # Read the table into a DataFrame
            dataframe = pd.read_html(table_io)[0]

            # Check if the table has exactly two columns or third column is comment
            if dataframe.shape[1] == 2 or dataframe.shape[1] > 2 and dataframe.iloc[0, 2] == 'Comments'  or dataframe.shape[1] > 2 and dataframe.iloc[0, 2] == 'Measurement':
                if dataframe.shape[1] > 2:
                    dataframe = dataframe.iloc[1:]

                # Filter out rows where key or value is empty
                dataframe = dataframe.dropna(subset=[dataframe.columns[0], dataframe.columns[1]])
                dataframe = dataframe[(dataframe.iloc[:, 0] != "") & (dataframe.iloc[:, 1] != "")]
                table_dict = dict(zip(dataframe.iloc[:, 0], dataframe.iloc[:, 1]))
                if not all_table_dicts or len(all_table_dicts[-1]) >= 4:
                    # Create a dictionary with left column as keys and right column as values

                    all_table_dicts.append(table_dict)
                else:
                    # if previous dict has less than 4 items expect the experiment to be split in two tables and add parameters to previous dict
                    all_table_dicts[-1].update(table_dict)

        # Remove items that are excluded in config
        for dictionary in all_table_dicts:
            keys_to_remove = self.config.get(self.name, 'exclude').split(',')
            for key in keys_to_remove:
                dictionary.pop(key, None)

        # Remove all with less than 4 items
        all_table_dicts = [dictionary for dictionary in all_table_dicts if len(dictionary) >= 4]
        return all_table_dicts

    def get_experiment_value_with_mapping(self, elab_protocol, mapping_key, default_value, remove_parameter=True):
        keys = self.config.get(self.name, 'mapping_{}'.format(mapping_key))
        key_list = keys.split(',')
        for key in key_list:
            key = key.strip()
            if key in elab_protocol:
                value = elab_protocol[key]
                if remove_parameter:
                    elab_protocol.pop(key)
                return value

        self.adapter.add_message('warning', 'No entry for {}. Each table must contain one of the following parameters: {}'.format(mapping_key, keys))
        print('no {}'.format(mapping_key))
        print(elab_protocol)
        return default_value

    @staticmethod
    def format_experiment_date(date_string):
        formats_to_try = [
            '%a., %d. %b. %Y, %H:%M',  # Example: Mon., 11. Dec. 2023, 14:45
            '%a, %d %b %Y, %H:%M',  # Example: Mon., 11. Dec. 2023, 14:45
            '%Y-%m-%d %H:%M:%S', # Example: 2024-06-13 15:04:03
            '%d.%m.%Y %H:%M' # Example: 24.09.2020 10:30
        ]

        output_format = '%Y-%m-%d'

        for input_format in formats_to_try:
            try:
                date_object = datetime.datetime.strptime(date_string, input_format)
                return date_object.strftime(output_format)
            except ValueError:
                continue
        return None

    @staticmethod
    def correct_unit(parameter, value):
        unit = ''
        if ',' in parameter:
            parameter, unit = parameter.rsplit(',', 1)
        if ' ' in value:
            value, unit = value.rsplit(' ', 1)
        value = '{} {}'.format(value.strip(), unit.strip())
        return parameter, value