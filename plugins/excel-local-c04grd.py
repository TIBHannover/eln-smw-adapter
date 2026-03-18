import os
import pandas as pd
import datetime
import re

class Plugin:
    def __init__(self, config, adapter):
        self.name = 'Excel-local-c04grd'
        self.config = config
        self.adapter = adapter

    def run(self, filename):
        self.adapter.logger.log_message('info', 'Running plugin {} with filename {}'.format(self.name, filename))

        # Get the uploads directory path
        uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
        file_path = os.path.join(uploads_dir, filename)

        # Check if file exists
        if not os.path.exists(file_path):
            self.adapter.add_message('error', 'File {} not found in uploads directory'.format(filename))
            self.adapter.logger.log_message('error', 'File {} not found in {}'.format(filename, uploads_dir))
            return None

        # Check if it's actually a file (not a directory)
        if not os.path.isfile(file_path):
            self.adapter.add_message('error', '{} is not a file'.format(filename))
            self.adapter.logger.log_message('error', '{} is not a file'.format(filename))
            return None

        # Check if it's a CSV file
        if not filename.lower().endswith('.csv'):
            self.adapter.add_message('error', 'File {} is not a CSV file'.format(filename))
            self.adapter.logger.log_message('error', 'File {} is not a CSV file'.format(filename))
            return None

        self.adapter.logger.log_message('info', 'File {} found in uploads directory'.format(filename))
        self.adapter.add_message('info', 'File {} successfully located'.format(filename))

        try:
            # Read CSV file with semicolon separator, no header row
            df = pd.read_csv(file_path, sep=';', header=None)
            self.adapter.logger.log_message('info', 'CSV file loaded successfully with {} rows'.format(len(df)))

            if df.empty:
                self.adapter.add_message('error', 'CSV file is empty or has no data')
                self.adapter.logger.log_message('error', 'CSV file {} is empty'.format(filename))
                return None

        except Exception as e:
            self.adapter.add_message('error', 'Failed to read CSV file: {}'.format(str(e)))
            self.adapter.logger.log_message('error', 'Failed to read CSV file {}: {}'.format(filename, str(e)))
            return None

        try:
            # Extract metadata from B1 and B2 (pandas uses 0-based indexing)
            date_raw = df.iloc[0, 1]  # B1
            material = df.iloc[1, 1]  # B2

            # Format date from dd.mm.yyyy to yyyy-mm-dd
            try:
                date_formatted = self.format_experiment_date(date_raw)
            except Exception as e:
                date_formatted = datetime.datetime.now().strftime('%Y-%m-%d')
                self.adapter.add_message('warning', 'Could not parse date from B1, using current date: {}'.format(str(e)))

            # Create origin internal identifier
            origin_internal_id = "{}_{}".format(date_formatted, material)

            # Check if protocol already exists
            if self.protocol_exists(origin_internal_id):
                self.adapter.logger.log_message('warning', 'Protocol with OriginInternalIdentifier {} already exists, skipping'.format(origin_internal_id))
                self.adapter.add_message('warning', 'Protocol {} already exists, skipping'.format(origin_internal_id))
                return None

            # Create the single protocol
            protocol = {}
            protocol['ProtocolType'] = 'INFGRD'
            protocol['Date'] = date_formatted
            protocol['Person'] = self.adapter.data.get('user', '')
            protocol['Origin'] = self.name
            protocol['OriginInternalIdentifier'] = origin_internal_id

            # Get parameter names from row 8 (index 7)
            parameter_names = df.iloc[7, :].tolist()

            # Process data starting from row 9 (index 8)
            data_rows = df.iloc[8:, :]

            specimen_list = []
            record_list = []

            for index, row in data_rows.iterrows():
                # Skip empty rows
                if pd.isna(row.iloc[0]) or row.iloc[0] == '':
                    continue

                # Create specimen
                specimen = {}
                specimen['Person'] = self.adapter.data.get('user', '')
                specimen['Description'] = str(row.iloc[0])  # Column A
                specimen['Material'] = material
                specimen['Name'] = self.adapter.create_smw_page('Specimen', specimen)
                specimen_list.append(specimen)

                # Create record
                record = {}
                record['Specimen'] = specimen['Name']
                record['Data'] = {}

                # Process parameters from columns B onwards
                for col_idx, param_name in enumerate(parameter_names[1:], start=1):
                    if pd.notna(param_name) and param_name != '':
                        value = row.iloc[col_idx]
                        if pd.notna(value) and value != '':
                            # Handle units in parameter names
                            param_name, formatted_value = self.process_parameter_with_unit(param_name, value)
                            record['Data'][param_name] = formatted_value

                record_list.append(record)

            # Set specimen list for protocol (comma-separated names)
            protocol['SpecimenList'] = ','.join([s['Name'] for s in specimen_list])
            protocol['Name'] = self.adapter.create_smw_page('Protocol', protocol)

            # Create records with protocol name
            for record in record_list:
                record['Protocol'] = protocol['Name']
                record['Name'] = self.adapter.create_smw_page('Record', record)

            self.adapter.logger.log_message('info', 'Successfully processed CSV file with {} specimens'.format(len(specimen_list)))
            self.adapter.add_message('info', 'Successfully processed {} specimens and {} records'.format(len(specimen_list), len(record_list)))

        except Exception as e:
            self.adapter.add_message('error', 'Failed to process CSV data: {}'.format(str(e)))
            self.adapter.logger.log_message('error', 'Failed to process CSV data from {}: {}'.format(filename, str(e)))
            return None

        self.adapter.logger.log_runtime()
        self.adapter.logger.log_message('info', 'Done processing {}'.format(filename))

        return None

    def protocol_exists(self, origin_internal_id):
        """
        Check if a protocol with the given OriginInternalIdentifier already exists in the wiki
        """
        try:
            # Use SMW ask query to check for existing protocol
            ask_condition = '[[Category:Protocol]][[Origin::{}]][[OriginInternalIdentifier::{}]]'.format(
                self.name, origin_internal_id)

            data = self.adapter.smw_api.ask('{}|limit=1'.format(ask_condition))

            if data and "query" in data and "results" in data["query"]:
                # If results exist, protocol already exists
                return len(data["query"]["results"]) > 0

            return False

        except Exception as e:
            self.adapter.logger.log_message('warning', 'Could not check for existing protocol: {}'.format(str(e)))
            # If we can't check, assume it doesn't exist to avoid blocking new protocols
            return False

    def process_parameter_with_unit(self, param_name, value):
        """
        Process parameter name and value, extracting units from parameter name
        and adding them to the value
        """
        # Check if parameter name contains unit in brackets
        unit_match = re.search(r'\[([^\]]+)\]', param_name)
        if unit_match:
            unit = unit_match.group(1)
            # Remove unit from parameter name
            clean_param_name = re.sub(r'\s*\[[^\]]+\]', '', param_name).strip()
            # Add unit to value
            formatted_value = "{} {}".format(str(value), unit)
            return clean_param_name, formatted_value
        else:
            return param_name, str(value)

    @staticmethod
    def format_experiment_date(date_string):
        """
        Convert date from dd.mm.yyyy format to yyyy-mm-dd format
        """
        try:
            # Try to parse as dd.mm.yyyy format
            date_obj = datetime.datetime.strptime(str(date_string), '%d.%m.%Y')
            return date_obj.strftime('%Y-%m-%d')
        except ValueError:
            try:
                # Try dd.mm.yyyy format without leading zeros
                date_obj = datetime.datetime.strptime(str(date_string), '%d.%m.%Y')
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                # If that fails, try other common formats
                try:
                    # Try pandas to_datetime for flexible parsing
                    date_obj = pd.to_datetime(date_string)
                    return date_obj.strftime('%Y-%m-%d')
                except:
                    raise ValueError(f"Could not parse date: {date_string}")