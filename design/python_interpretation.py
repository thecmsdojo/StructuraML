import re
import os
import uuid # For unique temp file names
import toml
import requests # For making HTTP requests to the LLM API
import json # Import the json library

class StructuralMLInterpreter:
    def __init__(self, config_file="config.toml"):
        self.variables = {}
        self.output_buffer = []
        self.llm_config = self._load_config(config_file)
        # Choose the LLM API based on loaded config
        # For this example, we'll assume chatgpt section exists if llm_config is not empty
        if self.llm_config and 'chatgpt' in self.llm_config:
            self.llm_api_key = self.llm_config['chatgpt'].get('api_key')
            self.llm_api_url = self.llm_config['chatgpt'].get('api_url')
            if not self.llm_api_key or not self.llm_api_url:
                print("Warning: ChatGPT API key or URL not found in config. Using default mock LLM.")
                self.llm_api = self._default_llm_api
            else:
                self.llm_api = self._actual_llm_api_call
        else:
            print("Warning: 'chatgpt' section not found in config. Using default mock LLM.")
            self.llm_api = self._default_llm_api

    def _load_config(self, config_file):
        """Loads configuration from a TOML file."""
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = toml.load(f)
                return config
            except Exception as e:
                print(f"Error loading config file '{config_file}': {e}")
                return {}
        else:
            print(f"Warning: Config file '{config_file}' not found. LLM API will be mocked.")
            return {}

    def _default_llm_api(self, prompt_text, max_tokens=None, temperature=None):
        """
        Placeholder for LLM API call (mock version).
        """
        print(f"\n--- MOCK LLM API Call ---")
        print(f"Prompt: '{prompt_text}'")
        print(f"Max Tokens: {max_tokens}, Temperature: {temperature}")
        print(f"-------------------------\n")
        # Simulate a quick response
        return f"Mock LLM responded to: '{prompt_text[:50]}...'"

    def _actual_llm_api_call(self, prompt_text, max_tokens=None, temperature=None):
        """
        Performs an actual API call to an OpenAI-compatible LLM endpoint.
        """
        if not self.llm_api_key or not self.llm_api_url:
            print("Error: LLM API key or URL not configured. Falling back to mock LLM.")
            return self._default_llm_api(prompt_text, max_tokens, temperature)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.llm_api_key}"
        }

        # OpenAI-compatible API expects messages in a list of dicts
        payload = {
            "model": "gpt-4o", # You might want to make this configurable in TOML
            "messages": [{"role": "user", "content": prompt_text}]
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        else:
            payload["temperature"] = 0.7 # Default temperature if not specified

        try:
            print(f"\n--- Making ACTUAL LLM API Call to {self.llm_api_url} ---")
            print(f"Prompt (first 100 chars): '{prompt_text[:100]}...'")
            response = requests.post(self.llm_api_url, headers=headers, json=payload)
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

            response_data = response.json()
            # Assuming a standard OpenAI-like response structure
            if 'choices' in response_data and len(response_data['choices']) > 0:
                llm_response = response_data['choices'][0]['message']['content']
                print(f"--- LLM Response Received (first 100 chars): '{llm_response[:100]}...' ---")
                return llm_response
            else:
                print(f"Warning: No valid choices in LLM response: {response_data}")
                return f"Error: No valid LLM response. Raw: {response_data}"

        except requests.exceptions.RequestException as e:
            print(f"Error during LLM API call: {e}")
            return f"Error connecting to LLM: {e}"
        except KeyError as e:
            print(f"Error parsing LLM response (missing key: {e}): {response_data}")
            return f"Error parsing LLM response. Missing key: {e}"
        except Exception as e:
            print(f"An unexpected error occurred during LLM call: {e}")
            return f"Unexpected LLM error: {e}"

    def _interpolate_variables(self, text):
        """Replaces {variable_name} with their current values."""
        def replace_match(match):
            var_name = match.group(1)
            return str(self.variables.get(var_name, f"{{UNDEFINED_VAR:{var_name}}}"))
        return re.sub(r'\{(\w+)\}', replace_match, text)

    def _evaluate_condition(self, condition):
        """Basic condition evaluation (e.g., for @if)."""
        try:
            for var, value in self.variables.items():
                condition = re.sub(r'\b' + re.escape(var) + r'\b', str(value), condition)
            return eval(condition)
        except Exception as e:
            print(f"Error evaluating condition '{condition}': {e}")
            return False

    def execute(self, file_path):
        self.output_buffer = [] # Clear buffer for new execution
        self._parse_and_execute_block(file_path)
        return "\n".join(self.output_buffer)

    def _parse_and_execute_block(self, file_path, current_indent=0):
        with open(file_path, 'r') as f:
            lines = f.readlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            interpolated_line = self._interpolate_variables(line)

            if not interpolated_line:
                i += 1
                continue

            if interpolated_line.startswith('@set'):
                match = re.match(r'@set (\w+)\s*=\s*(.*)', interpolated_line)
                if match:
                    var_name = match.group(1)
                    value_expression = match.group(2).strip()

                    if value_expression.startswith('"') and value_expression.endswith('"'):
                        self.variables[var_name] = value_expression[1:-1]
                    elif value_expression.startswith('@prompt'):
                        # Updated regex to capture json_decode parameter
                        prompt_match = re.search(r'@prompt\s*(?:file="([^"]+)")?\s*(?:"((?:[^"\\]|\\.)*)")?\s*(.*?)(?:\s*json_decode=(true|false))?\s*$', value_expression)
                        if prompt_match:
                            prompt_file = prompt_match.group(1)
                            inline_prompt_content = prompt_match.group(2)
                            other_params_string = prompt_match.group(3).strip()
                            json_decode_param = prompt_match.group(4) # Capture the json_decode parameter

                            max_tokens = None
                            temperature = None
                            do_json_decode = False # Default to false

                            if json_decode_param and json_decode_param.lower() == 'true':
                                do_json_decode = True

                            max_token_match = re.search(r'max_token=(\d+)', other_params_string)
                            if max_token_match:
                                max_tokens = int(max_token_match.group(1))

                            temperature_match = re.search(r'temperature=([\d.]+)', other_params_string)
                            if temperature_match:
                                temperature = float(temperature_match.group(1))

                            final_prompt = ""
                            if prompt_file:
                                prompt_file_path = os.path.join(os.path.dirname(file_path), prompt_file)
                                try:
                                    with open(prompt_file_path, 'r') as pf:
                                        final_prompt = self._interpolate_variables(pf.read())
                                except FileNotFoundError:
                                    print(f"Error: Prompt file '{prompt_file_path}' not found.")
                                    final_prompt = f"Error: Prompt file '{prompt_file_path}' not found."
                            elif inline_prompt_content is not None:
                                final_prompt = self._interpolate_variables(inline_prompt_content)
                            else:
                                print("Warning: @prompt without content or file.")
                                final_prompt = ""

                            llm_response = self.llm_api(final_prompt, max_tokens, temperature)

                            if do_json_decode:
                                try:
                                    self.variables[var_name] = json.loads(llm_response)
                                    print(f"JSON decoded response for '{var_name}'.")
                                except json.JSONDecodeError as e:
                                    print(f"Error decoding JSON for '{var_name}': {e}. Storing as raw string.")
                                    self.variables[var_name] = llm_response # Store raw if decode fails
                            else:
                                self.variables[var_name] = llm_response
                        else:
                            print(f"Error: Malformed @prompt statement: {interpolated_line}")
                    elif value_expression.startswith('[') and value_expression.endswith(']'):
                        try:
                            self.variables[var_name] = [item.strip().strip('"') for item in value_expression[1:-1].split(',')]
                        except Exception as e:
                            print(f"Error parsing list for {var_name}: {e}")
                            self.variables[var_name] = []
                    else:
                        try:
                            self.variables[var_name] = eval(value_expression)
                        except (NameError, SyntaxError):
                            self.variables[var_name] = value_expression
                else:
                    print(f"Error: Malformed @set statement: {interpolated_line}")

            elif interpolated_line.startswith('@log'):
                match = re.match(r'@log\s*(.*)', interpolated_line)
                if match:
                    log_content = match.group(1)
                    var_match = re.match(r'\{(\w+)\}', log_content)
                    if var_match:
                        self.output_buffer.append(str(self.variables.get(var_match.group(1), f"{{UNDEFINED_VAR:{var_match.group(1)}}}")))
                    else:
                        self.output_buffer.append(log_content)
                else:
                    print(f"Error: Malformed @log statement: {interpolated_line}")

            elif interpolated_line.startswith('@include'):
                # Modified regex to look for double quotes
                match = re.match(r'@include\s*"([^"]+)"', interpolated_line)
                if match:
                    include_path = os.path.join(os.path.dirname(file_path), match.group(1))
                    if os.path.exists(include_path):
                        self._parse_and_execute_block(include_path, current_indent + 1)
                    else:
                        print(f"Error: Included file '{include_path}' not found.")
                else:
                    print(f"Error: Malformed @include statement: {interpolated_line}")

            elif interpolated_line.startswith('@if'):
                condition = interpolated_line[len('@if'):].strip()
                if self._evaluate_condition(condition):
                    block_lines, next_i = self._get_block_lines(lines, i + 1, '@else', '@elseif', '@endif')
                    temp_file = self._write_temp_block(block_lines)
                    self._parse_and_execute_block(temp_file, current_indent + 1)
                    os.remove(temp_file)
                    i = next_i -1
                else:
                    block_start_index = i + 1
                    while block_start_index < len(lines):
                        block_line = lines[block_start_index].strip()
                        if block_line.startswith('@else') or block_line.startswith('@elseif') or block_line.startswith('@endif'):
                            i = block_start_index -1
                            break
                        block_start_index += 1
                    else:
                        i = len(lines)

            elif interpolated_line.startswith('@elseif'):
                i += 1
                continue

            elif interpolated_line.startswith('@else'):
                block_lines, next_i = self._get_block_lines(lines, i + 1, '@endif')
                temp_file = self._write_temp_block(block_lines)
                self._parse_and_execute_block(temp_file, current_indent + 1)
                os.remove(temp_file)
                i = next_i -1

            elif interpolated_line.startswith('@endif'):
                i += 1
                continue

            elif interpolated_line.startswith('@foreach'):
                match = re.match(r'@foreach (\w+) in (\w+)', interpolated_line)
                if match:
                    loop_var = match.group(1)
                    collection_var = match.group(2)
                    collection = self.variables.get(collection_var)

                    if isinstance(collection, list):
                        block_lines, next_i = self._get_block_lines(lines, i + 1, '@endforeach')
                        temp_file = self._write_temp_block(block_lines)
                        for item in collection:
                            self.variables[loop_var] = item
                            self._parse_and_execute_block(temp_file, current_indent + 1)
                        os.remove(temp_file)
                        i = next_i -1
                    else:
                        print(f"Error: Variable '{collection_var}' is not a list for @foreach.")
                        _, next_i = self._get_block_lines(lines, i + 1, '@endforeach')
                        i = next_i - 1
                else:
                    print(f"Error: Malformed @foreach statement: {interpolated_line}")

            elif interpolated_line.startswith('@endforeach'):
                i += 1
                continue

            elif interpolated_line.startswith('{') and interpolated_line.endswith('}'):
                var_name = interpolated_line[1:-1]
                self.output_buffer.append(str(self.variables.get(var_name, f"{{UNDEFINED_VAR:{var_name}}}")))
            else:
                if not interpolated_line.startswith('@'):
                    self.output_buffer.append(interpolated_line)

            i += 1

    def _get_block_lines(self, all_lines, start_index, *end_directives):
        """Helper to extract lines within a control flow block."""
        block_lines = []
        current_index = start_index
        while current_index < len(all_lines):
            line = all_lines[current_index].strip()
            if any(line.startswith(directive) for directive in end_directives):
                return block_lines, current_index + 1
            block_lines.append(all_lines[current_index])
            current_index += 1
        return block_lines, current_index

    def _write_temp_block(self, lines):
        """Writes a block of lines to a temporary file for recursive execution."""
        temp_file_name = f"temp_structuralml_block_{uuid.uuid4().hex}.sml"
        with open(temp_file_name, 'w') as f:
            f.writelines(lines)
        return temp_file_name


# --- Main Execution Logic ---
if __name__ == "__main__":
    # Before running this script:
    # 1. Create a 'config.toml' file in the same directory, e.g.:
    #    [chatgpt]
    #    api_key = "YOUR_OPENAI_API_KEY"
    #    api_url = "https://api.openai.com/v1/chat/completions"
    #
    # 2. Create a 'main_prompt.sml' file in the same directory, e.g.:
    #    @set my_name = "Alice"
    #    @log Hello, {my_name}!

    #    @set current_year = 2025
    #    @if current_year > 2024
    #    @log It's a new year!
    #    @endif

    #    @set colors = ["red", "green", "blue"]
    #    @foreach color in colors
    #    @log My favorite color is {color}.
    #    @endforeach

    #    # Example for @prompt with json_decode
    #    # Create a 'prompts' directory and a file inside it: 'prompts/my_json_prompt.txt'
    #    # with content like: {"item": "apple", "quantity": 10, "price": 1.25}
    #    @set product_info = @prompt file="prompts/my_json_prompt.txt" json_decode=true
    #    @log Product: {product_info["item"]}, Quantity: {product_info["quantity"]}

    # Initialize interpreter with the config file
    interpreter = StructuralMLInterpreter(config_file="config.toml")
    final_output = interpreter.execute('main_prompt.sml')
    print("\n\n--- Final Interpreter Output ---")
    print(final_output)
