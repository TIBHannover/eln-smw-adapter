from adapter import Adapter

class Plugin:
    def __init__(self, config, adapter):
        self.name = '<plugin->'
        self.config = config
        self.adapter = adapter

    # Use this function to read experiment data from eln, transform into expected data structure and create smw pages
    def run(self, id):

        self.adapter.logger.log_message('info', 'Running plugin {} with identifier {}'.format(self.name, id)) # add message to logfile

        identifier_within_eln = id
        source_api_token = self.config[self.name]['api_key']

        protocol = {}
        protocol['ProtocolType'] = 'INFHTr' # Experiment: e.g. heat treatment
        protocol['Date'] = "yyyy-MM-dd"
        protocol['Person'] = None
        self.adapter.add_message('warning', 'Parameter person missing in experiment. Protocols created without Experimentator.') # Add message to http response
        protocol['SpecimenList'] = 'S001,S002' # Create specimen pages beforehand and use names returned by adapter.create_smw_page()
        protocol['Origin'] = self.name # name of the eln to track origin
        protocol['OriginInternalIdentifier'] = id # id within origin
        protocol['Name'] = self.adapter.create_smw_page('Protocol', protocol) # returns name of the created page

        self.adapter.logger.log_runtime()
        self.adapter.logger.log_message('info', 'Done')

        return None
