import requests

class SemanticMediaWikiApiHandler:
    def __init__(self, config):
        self.api_url = config.get('SMW', 'api_url')  # Ensure 'api_url' exists in the config
        self.username = config.get('SMW', 'username')  # Ensure 'username' exists in the config
        self.password = config.get('SMW', 'password')  # Ensure 'password' exists in the config
        self.session = requests.Session()  # Using session for persistent connections
        self.login()

    def login(self):
        # Get login token
        login_token_params = {
            'action': 'query',
            'meta': 'tokens',
            'type': 'login',
            'format': 'json'
        }
        try:
            response = self.session.get(self.api_url, params=login_token_params)
            response.raise_for_status()  # Raise an error for bad HTTP response codes
            login_token = response.json()['query']['tokens']['logintoken']
        except requests.RequestException as e:
            print(f"Login token request failed: {e}")
            return False
        except KeyError:
            print("Login token not found in response.")
            return False

        # Log in with the token
        params = {
            'action': 'login',
            'lgname': self.username,
            'lgpassword': self.password,
            'lgtoken': login_token,
            'format': 'json'
        }
        try:
            response = self.session.post(self.api_url, data=params)
            response.raise_for_status()
            login_result = response.json()
            if login_result['login']['result'] == 'Success':
                return True
            else:
                print(f"Login failed: {login_result['login'].get('reason', 'Unknown error')}")
                return False
        except requests.RequestException as e:
            print(f"Login failed: {e}")
            return False
        except KeyError:
            print("Login result missing in response.")
            return False

    def ask(self, query):
        # Define the parameters for the SMW query
        params = {
            'action': 'ask',
            'query': query,
            'format': 'json'
        }

        # Send the SMW query request
        try:
            response = self.session.get(self.api_url, params=params)
            response.raise_for_status()  # Raise an error for bad HTTP response codes
            return response.json()  # Return the parsed JSON data
        except requests.RequestException as e:
            print(f"Query request failed: {e}")
            return None  # Return None in case of failure
        except ValueError:
            print("Failed to parse response as JSON.")
            return None

    def edit(self, title, text):
        # Get the CSRF token for editing the page
        csrf_token_params = {
            'action': 'query',
            'meta': 'tokens',
            'format': 'json'
        }
        try:
            response = self.session.get(self.api_url, params=csrf_token_params)
            response.raise_for_status()  # Raise an error for bad HTTP response codes
            csrf_token = response.json()['query']['tokens']['csrftoken']
        except requests.RequestException as e:
            print(f"CSRF token request failed: {e}")
            return False
        except KeyError:
            print("CSRF token missing in response.")
            return False

        # Post the edit request
        params = {
            'action': 'edit',
            'title': title,
            'text': text,
            'token': csrf_token,
            'format': 'json'
        }
        try:
            response = self.session.post(self.api_url, data=params)
            response.raise_for_status()
            create_result = response.json()

            if 'edit' in create_result and create_result['edit']['result'] == 'Success':
                print(f"Page '{title}' edited successfully.")
                return True
            else:
                print(f"Failed to edit the page. Response: {create_result}")
                return False
        except requests.RequestException as e:
            print(f"Edit request failed: {e}")
            return False
        except KeyError:
            print("Edit result missing in response.")
            return False
