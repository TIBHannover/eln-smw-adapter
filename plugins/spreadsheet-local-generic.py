import os
import pandas as pd
import datetime
import re

class Plugin:
    def __init__(self, config, adapter):
        self.name = 'Spreadsheet-local-generic'
        self.config = config
        self.adapter = adapter

    def run(self, filename):
        self.adapter.logger.log_message('info', 'Running plugin {} with filename {}'.format(self.name, filename))

        # Extract protocol type from filename
        protocol_type = self.extract_protocol_type(filename)
        if not protocol_type:
            self.adapter.add_message('error', 'Could not extract protocol type from filename: {}'.format(filename))
            self.adapter.logger.log_message('error', 'Failed to extract protocol type from filename: {}'.format(filename))
            return None

        self.adapter.logger.log_message('info', 'Extracted protocol type: {}'.format(protocol_type))

        # Check if protocol type exists in wiki
        if not self.check_protocol_type_exists(protocol_type):
            self.adapter.add_message('error', 'Protocol type {} does not exist in wiki. Please create it first or check filename.'.format(protocol_type))
            self.adapter.logger.log_message('error', 'Protocol type {} not found in wiki'.format(protocol_type))
            return None

        # Get configuration from wiki
        cfg = self.get_config_from_wiki(protocol_type)
        if not cfg:
            return None  # Error messages already added in get_config_from_wiki

        # Get the uploads directory path
        uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
        file_path = os.path.join(uploads_dir, filename)

        # Check if file exists
        if not os.path.exists(file_path):
            self.adapter.add_message('error', 'File {} not found in uploads directory'.format(filename))
            self.adapter.logger.log_message('error', 'File {} not found in {}'.format(filename, uploads_dir))
            return None

        if not os.path.isfile(file_path):
            self.adapter.add_message('error', '{} is not a file'.format(filename))
            self.adapter.logger.log_message('error', '{} is not a file'.format(filename))
            return None

        # Auto-detect file format from extension
        file_ext = filename.lower().split('.')[-1]
        if file_ext not in ['csv', 'xlsx', 'xls']:
            self.adapter.add_message('error', 'Unsupported file format: {}'.format(file_ext))
            return None

        self.adapter.logger.log_message('info', 'File {} found in uploads directory'.format(filename))
        self.adapter.add_message('info', 'File {} successfully located'.format(filename))

        # Read file (auto-detect format and delimiter)
        try:
            df = self.read_file(file_path, file_ext, cfg)
            self.adapter.logger.log_message('info', 'File loaded successfully with {} rows'.format(len(df)))

            if df.empty:
                self.adapter.add_message('error', 'File is empty or has no data')
                self.adapter.logger.log_message('error', 'File {} is empty'.format(filename))
                return None

        except Exception as e:
            self.adapter.add_message('error', 'Failed to read file: {}'.format(str(e)))
            self.adapter.logger.log_message('error', 'Failed to read file {}: {}'.format(filename, str(e)))
            return None

        # Process based on mode
        try:
            if cfg['mode'] == 'single':
                self.process_single_protocol(df, filename, cfg)
            else:  # multiple
                self.process_multiple_protocols(df, filename, cfg)

            self.adapter.logger.log_runtime()
            self.adapter.logger.log_message('info', 'Done processing {}'.format(filename))

        except Exception as e:
            self.adapter.add_message('error', 'Failed to process file data: {}'.format(str(e)))
            self.adapter.logger.log_message('error', 'Failed to process file data from {}: {}'.format(filename, str(e)))
            return None

        return None

    def extract_protocol_type(self, filename):
        """
        Extract protocol type from filename
        Example: c04grd_file.csv -> C04GRD
        Returns uppercase protocol type or None if not found
        """
        # Remove extension
        name_without_ext = filename.rsplit('.', 1)[0]

        # Extract letters and numbers until first special character
        protocol_type = ''
        for char in name_without_ext:
            if char.isalnum():  # letters and numbers
                protocol_type += char
            else:
                break

        if protocol_type:
            return protocol_type.upper()
        return None

    def check_protocol_type_exists(self, protocol_type):
        """
        Check if protocol type exists in wiki
        Returns True if exists, False otherwise
        """
        try:
            # Query SMW for protocol type page
            ask_query = '[[{}]][[Category:ProtocolType]]|limit=1'.format(protocol_type)
            result = self.adapter.smw_api.ask(ask_query)

            if result and result.get('query') and result['query'].get('results'):
                self.adapter.logger.log_message('info', 'Protocol type {} found in wiki'.format(protocol_type))
                return True

            self.adapter.logger.log_message('error', 'Protocol type {} not found in wiki'.format(protocol_type))
            return False
        except Exception as e:
            self.adapter.logger.log_message('error', 'Failed to check protocol type {}: {}'.format(protocol_type, str(e)))
            return False

    def get_config_from_wiki(self, protocol_type):
        """
        Fetch configuration from wiki page and parse it
        Returns config dict or None on error
        """
        config_page_name = 'SMWAdapterConfig:SpreadsheetLocalGeneric_{}'.format(protocol_type)

        try:
            # Fetch page content from wiki
            page_content = self.adapter.smw_api.get_page_content(config_page_name)

            if not page_content or not page_content.strip():
                self.adapter.add_message('error', 'Configuration page {} not found or empty in wiki'.format(config_page_name))
                self.adapter.logger.log_message('error', 'Config page {} is empty or does not exist'.format(config_page_name))
                return None

            self.adapter.logger.log_message('info', 'Fetched config from wiki page {}'.format(config_page_name))

            # Parse INI-style content
            cfg = self.parse_config_content(page_content, protocol_type)

            return cfg

        except Exception as e:
            self.adapter.add_message('error', 'Failed to fetch configuration from {}: {}'.format(config_page_name, str(e)))
            self.adapter.logger.log_message('error', 'Failed to fetch config from {}: {}'.format(config_page_name, str(e)))
            return None

    def parse_config_content(self, content, protocol_type):
        """
        Parse INI-style configuration content from wiki page
        Returns config dict with all necessary fields
        """
        cfg = {
            # File structure
            'parameter_name_row': 0,  # Will be converted to 0-based
            'protocol_type': protocol_type,  # Use extracted protocol type
            'sheet_name': None,  # Sheet name for Excel files (default: first sheet)

            # Protocol metadata
            'date': None,
            'date_format': '',
            'person': None,

            # Specimen metadata
            'specimen_material': None,
            'specimen_description': None,

            # Custom metadata for identifier
            'metadata_experiment_number': None,

            # Origin identifier template
            'origin_internal_identifier': '{date}_{specimen_material}',

            # Parameter processing
            'parameter_name_unit_pattern': '',
            'parameter_name_replace': '',
            'parameter_exclude': '',
        }

        # Parse line by line
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                # Remove inline comments (everything after #)
                if '#' in value:
                    value = value.split('#')[0].strip()

                if key == 'parameter_name_row':
                    cfg['parameter_name_row'] = int(value) - 1  # Convert to 0-based
                elif key in cfg:
                    cfg[key] = value

        # Auto-detect mode based on metadata format
        cfg['mode'] = self.detect_mode(cfg)

        return cfg

    def get_config(self):
        """
        DEPRECATED: This method is no longer used.
        Configuration is now fetched from wiki pages via get_config_from_wiki()
        """
        # This method is kept for backwards compatibility but should not be called
        raise NotImplementedError("Configuration must be loaded from wiki via get_config_from_wiki()")

    def detect_mode(self, cfg):
        """Auto-detect mode based on whether metadata are cells or columns"""
        # If date is a cell reference (e.g., B1), it's single mode
        # If it's a column reference (e.g., B or column name), it's multiple mode
        if cfg['date']:
            if self.is_cell_reference(cfg['date']):
                return 'single'
            else:
                return 'multiple'
        # Default to single if no date specified
        return 'single'

    def is_cell_reference(self, ref):
        """Check if reference is a cell (e.g., B1) or column (e.g., B or column name)"""
        if not ref:
            return False
        # Cell reference has letters followed by digits (e.g., B1, AB10)
        import re
        return bool(re.match(r'^[A-Z]+\d+$', ref.upper()))

    def read_file(self, file_path, file_ext, cfg):
        """Read CSV or Excel file with auto-detection"""
        if file_ext == 'csv':
            # Auto-detect delimiter by trying both ; and ,
            delimiter = self.detect_csv_delimiter(file_path)
            # Always read without treating first row as header
            df = pd.read_csv(file_path, sep=delimiter, header=None)
            self.adapter.logger.log_message('info', 'CSV file loaded with delimiter: "{}"'.format(delimiter))
        else:  # excel (xlsx, xls)
            # Determine sheet to read
            sheet = cfg.get('sheet_name') if cfg.get('sheet_name') else 0

            try:
                df = pd.read_excel(file_path, sheet_name=sheet, header=None)
                if isinstance(sheet, str):
                    self.adapter.logger.log_message('info', 'Excel file loaded from sheet: "{}"'.format(sheet))
                else:
                    self.adapter.logger.log_message('info', 'Excel file loaded from first sheet')
            except ValueError as e:
                # Sheet name not found
                try:
                    # Get available sheet names for error message
                    xl_file = pd.ExcelFile(file_path)
                    available_sheets = xl_file.sheet_names
                    error_msg = 'Sheet "{}" not found. Available sheets: {}'.format(sheet, ', '.join(available_sheets))
                    self.adapter.add_message('error', error_msg)
                    self.adapter.logger.log_message('error', error_msg)
                except:
                    self.adapter.add_message('error', 'Failed to read Excel file: {}'.format(str(e)))
                    self.adapter.logger.log_message('error', 'Failed to read Excel file: {}'.format(str(e)))
                raise

        # Auto-trim columns at first empty header (if parameter_name_row is configured)
        if 'parameter_name_row' in cfg and cfg['parameter_name_row'] is not None:
            df = self.trim_empty_columns(df, cfg['parameter_name_row'])

        return df

    def trim_empty_columns(self, df, header_row):
        """Remove columns after the first empty header cell"""
        header_values = df.iloc[header_row, :]
        # Find first empty/NaN column
        for idx, val in enumerate(header_values):
            if pd.isna(val) or val == '':
                # Trim dataframe to only include columns before this one
                return df.iloc[:, :idx]
        return df  # No empty headers found, return as is

    def detect_csv_delimiter(self, file_path):
        """Auto-detect CSV delimiter (try ; and ,)"""
        with open(file_path, 'r') as f:
            first_line = f.readline()
            if ';' in first_line:
                return ';'
            else:
                return ','

    def process_single_protocol(self, df, filename, cfg):
        """Process file with single protocol and multiple specimens"""

        # Get parameter names first (needed for column-based metadata)
        parameter_names = df.iloc[cfg['parameter_name_row'], :].tolist()

        # Apply parameter name replacements with validation
        if cfg['parameter_name_replace']:
            parameter_names = self.apply_parameter_name_replacements(
                parameter_names, cfg['parameter_name_replace'], cfg['parameter_name_unit_pattern']
            )

        # Extract metadata (single mode uses cell references, not rows)
        metadata = {}

        # Date
        date_raw = self.get_metadata_value(df, cfg['date'])
        try:
            metadata['date'] = self.format_date(date_raw, cfg['date_format']) if date_raw else datetime.datetime.now().strftime('%Y-%m-%d')
        except Exception as e:
            metadata['date'] = datetime.datetime.now().strftime('%Y-%m-%d')
            self.adapter.add_message('warning', 'Could not parse date, using current date: {}'.format(str(e)))

        # Material
        metadata['specimen_material'] = self.get_metadata_value(df, cfg['specimen_material']) or '?'

        # Person (use adapter.user if not specified)
        metadata['person'] = self.get_metadata_value(df, cfg['person']) or (self.adapter.user if self.adapter.user else '')

        # Build origin internal identifier from pattern
        metadata['filename'] = filename
        origin_internal_id = self.build_origin_internal_identifier(cfg['origin_internal_identifier'], metadata, filename)

        # Check if protocol already exists
        origin = '{}-{}'.format(self.name, cfg['protocol_type'])
        existing_protocol = self.protocol_exists(origin_internal_id, origin, cfg)
        if existing_protocol:
            self.adapter.logger.log_message('warning', 'Protocol {} with Origin {} and OriginInternalIdentifier {} already exists, skipping'.format(existing_protocol, origin, origin_internal_id))
            self.adapter.add_message('warning', 'Protocol {} already exists, skipping'.format(existing_protocol))
            return None

        # Process data rows (start one row after parameter names)
        data_rows = df.iloc[cfg['parameter_name_row'] + 1:, :]

        # Get description column reference - can be column index or column name
        desc_col_ref = cfg['specimen_description']

        specimen_list = []
        record_list = []

        self.adapter.logger.log_message('info', 'Total data_rows to process: {}'.format(len(data_rows)))

        # Build list of columns to exclude (metadata columns that appear in parameters)
        metadata_columns_to_exclude = []
        for meta_key in ['date', 'specimen_material', 'person', 'specimen_description',
                         'metadata_experiment_number']:
            if cfg.get(meta_key) and not self.is_cell_reference(cfg.get(meta_key)):
                # It's a column reference, convert to parameter name and exclude
                col_ref = cfg.get(meta_key)
                col_idx = self.column_letter_to_index(col_ref)
                if col_idx < len(parameter_names):
                    param_name = parameter_names[col_idx]
                    if param_name and not pd.isna(param_name):
                        metadata_columns_to_exclude.append(param_name)

        exclude_params = [p.strip() for p in cfg['parameter_exclude'].split(',') if p.strip()]
        exclude_params.extend(metadata_columns_to_exclude)

        for index, row in data_rows.iterrows():
            # Get specimen description
            specimen_description = self.get_metadata_value(df, desc_col_ref, row, parameter_names) if desc_col_ref else row.iloc[0]

            # Skip empty rows
            if not specimen_description or pd.isna(specimen_description) or specimen_description == '':
                continue

            # Create specimen
            specimen = {}
            specimen['Person'] = metadata['person']
            specimen['Description'] = str(specimen_description)
            specimen['Material'] = metadata['specimen_material']
            specimen['Name'] = self.adapter.create_smw_page('Specimen', specimen)
            specimen_list.append(specimen)

            self.adapter.logger.log_message('info', 'Iteration {}: Created specimen {} (Description: {}) - Total in list: {}'.format(index, specimen['Name'], specimen_description, len(specimen_list)))

            # Create record
            record = {}
            record['Specimen'] = specimen['Name']
            record['Data'] = {}

            # Process parameters
            for col_idx, param_name in enumerate(parameter_names):
                if pd.isna(param_name) or param_name == '':
                    continue
                if param_name in exclude_params:
                    continue

                value = row.iloc[col_idx]
                if pd.notna(value) and value != '':
                    # Handle units
                    if cfg['parameter_name_unit_pattern']:
                        param_name, value = self.extract_unit_from_header(param_name, value, cfg['parameter_name_unit_pattern'])
                    record['Data'][param_name] = value

            record_list.append(record)

        # Create protocol
        protocol_name = self.create_protocol(
            cfg, metadata, origin_internal_id, ','.join([s['Name'] for s in specimen_list])
        )

        # Create records with protocol name
        for record in record_list:
            record['Protocol'] = protocol_name
            record['Name'] = self.adapter.create_smw_page('Record', record)

        self.adapter.logger.log_message('info', 'Successfully processed file with {} specimens'.format(len(specimen_list)))
        self.adapter.add_message('info', 'Successfully processed {} specimens and {} records'.format(len(specimen_list), len(record_list)))

    def process_multiple_protocols(self, df, filename, cfg):
        """Process file with multiple protocols (one per row)"""

        # Get parameter names from parameter_name_row
        parameter_names = df.iloc[cfg['parameter_name_row'], :].tolist()

        # Apply parameter name replacements with validation
        if cfg['parameter_name_replace']:
            parameter_names = self.apply_parameter_name_replacements(
                parameter_names, cfg['parameter_name_replace'], cfg['parameter_name_unit_pattern']
            )

        # Get data rows (start one row after parameter names)
        data_rows = df.iloc[cfg['parameter_name_row'] + 1:, :]

        # Build list of columns to exclude (metadata columns that appear in parameters)
        metadata_columns_to_exclude = []
        for meta_key in ['date', 'specimen_material', 'person', 'specimen_description',
                         'metadata_experiment_number']:
            if cfg.get(meta_key) and not self.is_cell_reference(cfg.get(meta_key)):
                # It's a column reference, convert to parameter name and exclude
                col_ref = cfg.get(meta_key)
                col_idx = self.column_letter_to_index(col_ref)
                if col_idx < len(parameter_names):
                    param_name = parameter_names[col_idx]
                    if param_name and not pd.isna(param_name):
                        metadata_columns_to_exclude.append(param_name)

        exclude_params = [p.strip() for p in cfg['parameter_exclude'].split(',') if p.strip()]
        exclude_params.extend(metadata_columns_to_exclude)

        for index, row in data_rows.iterrows():
            # Skip empty rows
            if row.isnull().all():
                continue

            try:
                # Extract metadata from this row (multiple mode uses column references)
                metadata = {}

                # Date
                date_raw = self.get_metadata_value(df, cfg['date'], row, parameter_names)
                try:
                    metadata['date'] = self.format_date(date_raw, cfg['date_format']) if date_raw else datetime.datetime.now().strftime('%Y-%m-%d')
                except Exception as e:
                    metadata['date'] = datetime.datetime.now().strftime('%Y-%m-%d')
                    self.adapter.add_message('warning', 'Could not parse date for row {}: {}'.format(index, str(e)))

                # Material
                metadata['specimen_material'] = self.get_metadata_value(df, cfg['specimen_material'], row, parameter_names) or '?'

                # Person
                metadata['person'] = self.get_metadata_value(df, cfg['person'], row, parameter_names) or (self.adapter.user if self.adapter.user else '')

                # Description
                metadata['specimen_description'] = self.get_metadata_value(df, cfg['specimen_description'], row, parameter_names) or '?'

                # Experiment number
                metadata['metadata_experiment_number'] = self.get_metadata_value(df, cfg['metadata_experiment_number'], row, parameter_names) or str(index)

                # Build origin internal identifier from pattern
                metadata['filename'] = filename
                origin_internal_id = self.build_origin_internal_identifier(cfg['origin_internal_identifier'], metadata, filename)

                # Check if protocol already exists
                origin = '{}-{}'.format(self.name, cfg['protocol_type'])
                existing_protocol = self.protocol_exists(origin_internal_id, origin, cfg)
                if existing_protocol:
                    self.adapter.logger.log_message('warning', 'Protocol {} with Origin {} and OriginInternalIdentifier {} already exists, skipping'.format(existing_protocol, origin, origin_internal_id))
                    self.adapter.add_message('warning', 'Protocol {} already exists, skipping'.format(existing_protocol))
                    continue

                # Create specimen
                specimen = {}
                specimen['Person'] = metadata['person']
                specimen['Description'] = str(metadata['specimen_description'])
                specimen['Material'] = str(metadata['specimen_material'])
                specimen['Name'] = self.adapter.create_smw_page('Specimen', specimen)

                # Create protocol
                protocol_name = self.create_protocol(
                    cfg, metadata, origin_internal_id, specimen['Name']
                )

                # Create record with remaining columns
                record = {}
                record['Specimen'] = specimen['Name']
                record['Protocol'] = protocol_name
                record['Data'] = {}

                # Process parameters (skip metadata columns)
                for col_idx, param_name in enumerate(parameter_names):
                    # Skip empty parameter names and excluded parameters
                    if pd.isna(param_name) or param_name == '':
                        continue
                    if param_name in exclude_params:
                        continue

                    value = row.iloc[col_idx]
                    if pd.notna(value) and value != '':
                        # Handle units if needed
                        if cfg['parameter_name_unit_pattern']:
                            param_name, value = self.extract_unit_from_header(parameter_names[col_idx], value, cfg['parameter_name_unit_pattern'])
                        record['Data'][param_name] = value

                record['Name'] = self.adapter.create_smw_page('Record', record)

                self.adapter.logger.log_message('info', 'Successfully processed protocol: {}'.format(origin_internal_id))

            except Exception as e:
                self.adapter.add_message('error', 'Failed to process row {}: {}'.format(index, str(e)))
                self.adapter.logger.log_message('error', 'Failed to process row {}: {}'.format(index, str(e)))

    def get_cell_value(self, df, cell_ref):
        """Get value from cell reference like 'B1' (column B, row 1)"""
        # Parse cell reference
        col_letter = ''.join([c for c in cell_ref if c.isalpha()])
        row_num = int(''.join([c for c in cell_ref if c.isdigit()])) - 1  # Convert to 0-based

        # Convert column letter to index (A=0, B=1, etc.)
        col_idx = 0
        for i, c in enumerate(reversed(col_letter.upper())):
            col_idx += (ord(c) - ord('A') + 1) * (26 ** i)
        col_idx -= 1  # Convert to 0-based

        return df.iloc[row_num, col_idx]

    def column_letter_to_index(self, col_letter):
        """Convert column letter (A, B, AA, etc.) to 0-based index"""
        col_idx = 0
        for i, c in enumerate(reversed(col_letter.upper())):
            col_idx += (ord(c) - ord('A') + 1) * (26 ** i)
        col_idx -= 1
        return col_idx

    def get_metadata_value(self, df, metadata_ref, row=None, parameter_names=None):
        """
        Get metadata value from either cell reference (B1) or column letter (B)
        - If cell reference (B1): returns value from that specific cell
        - If column letter (B) and row provided: returns value from that column in the row
        """
        if not metadata_ref:
            return None

        if self.is_cell_reference(metadata_ref):
            # It's a cell reference like B1
            return self.get_cell_value(df, metadata_ref)
        else:
            # It's a column letter (A, B, etc.)
            if row is None:
                return None

            col_idx = self.column_letter_to_index(metadata_ref)
            return row.iloc[col_idx] if pd.notna(row.iloc[col_idx]) else None

    def build_origin_internal_identifier(self, pattern, metadata_values, filename):
        """Build origin internal identifier from pattern like {date}_{specimen_material}"""
        result = pattern
        # Replace all {placeholder} with actual values
        for key, value in metadata_values.items():
            placeholder = '{' + key + '}'
            if placeholder in result:
                result = result.replace(placeholder, str(value) if value else '')
        # Replace {filename}
        result = result.replace('{filename}', filename)
        return result

    def create_protocol(self, cfg, metadata, origin_internal_id, specimen_list):
        """
        Create a protocol page
        Returns the protocol name
        """
        protocol = {}
        protocol['ProtocolType'] = cfg['protocol_type']
        protocol['Date'] = metadata['date']
        protocol['Person'] = metadata['person']
        protocol['SpecimenList'] = specimen_list
        protocol['Origin'] = '{}-{}'.format(self.name, cfg['protocol_type'])
        protocol['OriginInternalIdentifier'] = origin_internal_id
        protocol['Name'] = self.adapter.create_smw_page('Protocol', protocol)
        return protocol['Name']

    def apply_parameter_name_replacements(self, parameter_names, replacements_str, unit_pattern):
        """
        Apply parameter name replacements with validation
        Format: Column:ExpectedName=NewName (e.g., I:Drahtdicke=Wire thickness)
        - Column: column letter (A, B, I, etc.)
        - ExpectedName: parameter name after unit extraction
        - NewName: new name to use
        Throws error if expected name doesn't match actual name
        """
        if not replacements_str:
            return parameter_names

        # Parse replacements
        replacements = []
        for entry in replacements_str.split(','):
            entry = entry.strip()
            if not entry:
                continue

            if ':' not in entry or '=' not in entry:
                raise ValueError(f"Invalid parameter_name_replace format: '{entry}'. Expected format: 'Column:ExpectedName=NewName'")

            col_part, name_part = entry.split(':', 1)
            expected_name, new_name = name_part.split('=', 1)

            col_letter = col_part.strip()
            expected_name = expected_name.strip()
            new_name = new_name.strip()

            col_idx = self.column_letter_to_index(col_letter)
            replacements.append({
                'col_idx': col_idx,
                'col_letter': col_letter,
                'expected_name': expected_name,
                'new_name': new_name
            })

        # Apply replacements with validation
        new_names = parameter_names.copy()
        for repl in replacements:
            col_idx = repl['col_idx']
            if col_idx >= len(parameter_names):
                raise ValueError(f"Column {repl['col_letter']} (index {col_idx}) does not exist in file")

            actual_name = parameter_names[col_idx]
            if pd.isna(actual_name):
                actual_name = ''

            # Extract unit from actual name if unit pattern is configured
            if unit_pattern:
                actual_name_clean, _ = self.extract_unit_from_header(actual_name, '', unit_pattern)
            else:
                actual_name_clean = actual_name

            # Validate expected name matches actual name
            if actual_name_clean.strip() != repl['expected_name']:
                raise ValueError(
                    f"Parameter name mismatch at column {repl['col_letter']}: "
                    f"expected '{repl['expected_name']}' but found '{actual_name_clean}'. "
                    f"File structure may have changed. Please update configuration."
                )

            # Replace with new name
            new_names[col_idx] = repl['new_name']

        return new_names

    def extract_unit_from_header(self, param_name, value, pattern):
        """Extract unit from parameter name using regex pattern and add to value"""
        if not pattern:
            return param_name, str(value)

        unit_match = re.search(pattern, str(param_name))
        if unit_match:
            # Get the first non-None group (the captured unit)
            unit = None
            for group in unit_match.groups():
                if group:
                    unit = group
                    break

            if unit:
                # Remove the matched portion from parameter name
                clean_param_name = re.sub(pattern, '', str(param_name)).strip()
                formatted_value = "{} {}".format(str(value), unit.strip())
                return clean_param_name, formatted_value

        return param_name, str(value)

    def format_date(self, date_value, date_format):
        """Format date from various input formats to yyyy-mm-dd"""
        # If no format specified, use pandas flexible parsing
        if not date_format:
            if isinstance(date_value, str):
                date_obj = pd.to_datetime(date_value)
                return date_obj.strftime('%Y-%m-%d')
            elif hasattr(date_value, 'strftime'):
                return date_value.strftime('%Y-%m-%d')
            else:
                raise ValueError(f"Unsupported date type: {type(date_value)}")

        # Otherwise use specified format
        if isinstance(date_value, str):
            date_obj = datetime.datetime.strptime(str(date_value), date_format)
            return date_obj.strftime('%Y-%m-%d')
        elif hasattr(date_value, 'strftime'):
            return date_value.strftime('%Y-%m-%d')
        else:
            raise ValueError(f"Unsupported date type: {type(date_value)}")

    def protocol_exists(self, origin_internal_id, origin, cfg):
        """Check if protocol already exists in wiki (case-insensitive). Returns protocol name if exists, None otherwise."""
        try:
            # Query for protocols - SMW search is case-insensitive by default
            ask_condition = '[[Category:Protocol]][[OriginInternalIdentifier::{}]][[Origin::{}]]'.format(
                origin_internal_id, origin
            )
            data = self.adapter.smw_api.ask('{}|limit=1'.format(ask_condition))
            if data and "query" in data and "results" in data["query"]:
                results = data["query"]["results"]
                if len(results) > 0:
                    # Return the protocol page name
                    return next(iter(results.values()))['fulltext']
            return None
        except Exception as e:
            self.adapter.logger.log_message('warning', 'Could not check for existing protocol: {}'.format(str(e)))
            return None