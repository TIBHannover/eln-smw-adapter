import os
import re
import configparser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Environment variables for the core settings: variable -> (section, option)
ENV_MAPPING = {
    'SMW_API_URL': ('SMW', 'api_url'),
    'SMW_USERNAME': ('SMW', 'username'),
    'SMW_PASSWORD': ('SMW', 'password'),
    'DEBUG_MODE': ('Main', 'debug_mode'),
    'UPLOAD_PATH': ('Main', 'upload_path'),
}


def get_version():
    """Adapter version, single source of truth is the VERSION file"""
    with open(os.path.join(BASE_DIR, 'VERSION')) as f:
        return f.read().strip()


def plugin_env_prefix(plugin_name):
    """Env prefix of a plugin, e.g. Excel-local -> EXCEL_LOCAL_"""
    return re.sub(r'[^A-Za-z0-9]', '_', plugin_name).upper() + '_'


def load_config():
    """
    Load configuration from config/config.ini (optional) and override it with environment variables.

    - SMW_API_URL, SMW_USERNAME, SMW_PASSWORD, DEBUG_MODE (on/off), UPLOAD_PATH
    - ENABLED_PLUGINS: comma separated plugin names (e.g. "eLabFTW,Excel-local"), replaces the [Plugins] section
    - <PLUGIN>_<OPTION> for every enabled plugin, e.g. ELABFTW_API_URL, ELABFTW_API_KEY, EXCEL_LOCAL_TYPE
    """
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str  # Preserve case for option names
    config.read(os.path.join(BASE_DIR, 'config/config.ini'))

    for var, (section, option) in ENV_MAPPING.items():
        value = os.environ.get(var)
        if value is not None:
            if not config.has_section(section):
                config.add_section(section)
            config.set(section, option, value)

    enabled = os.environ.get('ENABLED_PLUGINS')
    if enabled is not None:
        config.remove_section('Plugins')
        config.add_section('Plugins')
        for name in enabled.split(','):
            if name.strip():
                config.set('Plugins', name.strip(), 'on')

    plugin_names = set(config.sections()) - {'Main', 'SMW', 'Plugins'}
    if config.has_section('Plugins'):
        plugin_names.update(config.options('Plugins'))
    for plugin in plugin_names:
        prefix = plugin_env_prefix(plugin)
        for var, value in os.environ.items():
            if var.startswith(prefix):
                if not config.has_section(plugin):
                    config.add_section(plugin)
                config.set(plugin, var[len(prefix):].lower(), value)

    return config
