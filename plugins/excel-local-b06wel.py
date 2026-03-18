import os
import pandas as pd
import datetime

class Plugin:
    def __init__(self, config, adapter):
        self.name = 'Excel-local-b06wel'
        self.config = config
        self.adapter = adapter

    # Use this function to read experiment data from Excel file, transform into expected data structure and create SMW pages
    def run(self, filename):
        self.adapter.logger.log_message('info', 'Running plugin {} with filename {}'.format(self.name, filename))

        # Get the uploads directory path using current file handling logic
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

        # Check if it's an Excel file
        if not filename.lower().endswith(('.xlsx', '.xls')):
            self.adapter.add_message('error', 'File {} is not an Excel file'.format(filename))
            self.adapter.logger.log_message('error', 'File {} is not an Excel file'.format(filename))
            return None

        self.adapter.logger.log_message('info', 'File {} found in uploads directory'.format(filename))
        self.adapter.add_message('info', 'File {} successfully located'.format(filename))

        try:
            # Read Excel file
            df = pd.read_excel(file_path, sheet_name=0, usecols="A:AB", skiprows=2)
            self.adapter.logger.log_message('info', 'Excel file loaded successfully with {} rows'.format(len(df)))
            
            if df.empty:
                self.adapter.add_message('error', 'Excel file is empty or has no data')
                self.adapter.logger.log_message('error', 'Excel file {} is empty'.format(filename))
                return None

        except Exception as e:
            self.adapter.add_message('error', 'Failed to read Excel file: {}'.format(str(e)))
            self.adapter.logger.log_message('error', 'Failed to read Excel file {}: {}'.format(filename, str(e)))
            return None

        try:
            # Process Excel data
            translated_df = self.translate_columns(df)
            df_unit = self.move_units_to_values(translated_df)
            experiment_list = df_unit.iloc[0:].to_dict(orient="records")

            self.adapter.logger.log_message('info', 'Processing {} experiments from Excel file'.format(len(experiment_list)))

            specimen_list = []
            protocol_list = []
            record_list = []

            # Process experiments
            for experiment in experiment_list:
                try:
                    person = experiment.pop('Operator', 'Unknown')
                    experiment_number = experiment.pop('Experiment number', 'Unknown')
                    origin_internal_id = "{}-{}".format(filename, experiment_number)

                    # Check if protocol already exists
                    if self.protocol_exists(origin_internal_id):
                        self.adapter.logger.log_message('warning', 'Protocol with OriginInternalIdentifier {} already exists, skipping'.format(origin_internal_id))
                        self.adapter.add_message('warning', 'Protocol {} already exists, skipping'.format(origin_internal_id))
                        continue

                    # Create specimen
                    specimen = {}
                    specimen['Person'] = person
                    specimen['Description'] = experiment.pop('Workpiece dimensions', '?')
                    specimen['Material'] = experiment.pop('Base material', '?')
                    specimen['Name'] = self.adapter.create_smw_page('Specimen', specimen)
                    specimen_list.append(specimen)

                    # Create protocol
                    protocol = {}
                    protocol['ProtocolType'] = experiment.pop('Protocol type', 'B06Wel')

                    # Format date with error handling
                    raw_date = experiment.pop('Date', '')
                    try:
                        protocol['Date'] = self.format_experiment_date(raw_date)
                    except Exception as e:
                        protocol['Date'] = datetime.datetime.now().strftime('%Y-%m-%d')
                        self.adapter.add_message('warning', 'Could not parse date, using current date: {}'.format(str(e)))

                    protocol['Person'] = person
                    protocol['SpecimenList'] = specimen['Name']
                    protocol['Origin'] = self.name
                    protocol['OriginInternalIdentifier'] = origin_internal_id
                    protocol_list.append(protocol)
                    protocol['Name'] = self.adapter.create_smw_page('Protocol', protocol)

                    # Create record
                    record = {}
                    record['Specimen'] = specimen['Name']
                    record['Protocol'] = protocol['Name']
                    record['Data'] = {}
                    for parameter, value in experiment.items():
                        if pd.notna(value):  # Only add non-null values
                            record['Data'][parameter] = value

                    record_list.append(record)
                    record['Name'] = self.adapter.create_smw_page('Record', record)

                    self.adapter.logger.log_message('info', 'Successfully processed experiment: {}'.format(protocol['OriginInternalIdentifier']))

                except Exception as e:
                    self.adapter.add_message('error', 'Failed to process experiment: {}'.format(str(e)))
                    self.adapter.logger.log_message('error', 'Failed to process experiment: {}'.format(str(e)))

                # break  # Intentional for testing purposes - break after first row regardless of outcome

        except Exception as e:
            self.adapter.add_message('error', 'Failed to process Excel data: {}'.format(str(e)))
            self.adapter.logger.log_message('error', 'Failed to process Excel data from {}: {}'.format(filename, str(e)))
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

    def translate_columns(self, df):
        translation = {
            'Versuchsnummer': 'Experiment number',
            'Datum': 'Date',
            'Bearbeiter': 'Operator',
            'Schweißverfahren': 'Welding process',
            'Schweißquelle': 'Welding source',
            'Material': 'Base material',
            'Abmaße in mm': 'Workpiece dimensions [mm]',
            'Material2': 'Filler material',
            'Drahtdicke in mm': 'Wire thickness [mm]',
            'Schweißart': 'Welding type',
            'Abmaße in mm3': 'Weld volume [mm^3]',
            'Umgebungsatmosphäre': 'Atmosphere',
            'Stromstärke in A': 'Current [A]',
            'Sollspannung in V': 'Target voltage [V]',
            'Holdspannung in V': 'Hold voltage [V]',
            'Schweißgeschwindigkeit in mm/s': 'Welding speed [mm/s]',
            'Vorschubgeschwindigkeit Draht in m/min': 'Wire feed speed [m/min]',
            'Gasvorströmzeit in s': 'Gas prepurge time [s]',
            'Gasflussrate in l/min': 'Gas flow rate [l/min]',
            'Schweißgas': 'Welding gas',
            'Trigerzeitpunkt für Ende vor Ende in s': 'Trigger time stop before end [s]',
            'Pulsart': 'Pulse type',
            'Balance': 'Balance',
            'Frequenz in Hz': 'Frequency [Hz]',
            'Wartezeit zw. Den Lagen': 'Wait between layers [s]',
            'Abstand zw. Lagen': 'Gap between layers [mm]',
            'Bemerkungen': 'Notes',
            'Ursache': 'Cause'
        }

        return df.rename(columns=translation)

    def move_units_to_values(self, df):
        new_df = df.copy()
        for col in df.columns:
            if "[" in col and "]" in col:
                # Extract name and unit
                name, unit = col.split("[", 1)
                unit = unit.rstrip("]").strip()
                name = name.strip()

                # Rename column
                new_df.rename(columns={col: name}, inplace=True)

                # Append unit to each value (if not NaN)
                new_df[name] = new_df[name].apply(
                    lambda x: f"{x} {unit}" if pd.notna(x) else x
                )
        return new_df

    @staticmethod
    def format_experiment_date(date):
        output_format = '%Y-%m-%d'
        if isinstance(date, str):
            # Handle string dates - you may need to adjust the input format
            try:
                parsed_date = pd.to_datetime(date)
                return parsed_date.strftime(output_format)
            except:
                raise ValueError(f"Could not parse date string: {date}")
        elif hasattr(date, 'strftime'):
            # Handle datetime objects
            return date.strftime(output_format)
        else:
            raise ValueError(f"Unsupported date type: {type(date)}")