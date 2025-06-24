import re
import os
import toml
import requests
import json

class StructuralMLInterpreter:
    def __init__(self, config_file="config.toml"):
        self.variables = {}
        self.output_buffer = []
        self.llm_config = self._load_config(config_file)
        # Choose the LLM API based on loaded config
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
            print(f"Prompt: '{prompt_text}...'")
            response = requests.post(self.llm_api_url, headers=headers, json=payload)
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

            response_data = response.json()
            # Assuming a standard OpenAI-like response structure
            if 'choices' in response_data and len(response_data['choices']) > 0:
                llm_response = response_data['choices'][0]['message']['content']
                print(f"--- LLM Response Received: '{llm_response}...' ---")
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
        """Replaces {variable_name} with their current values, supporting nested access."""
        def replace_match(match):
            var_expression = match.group(1) # This can be "my_var", "my_list[0]", "my_dict['key']"
            try:
                # Safely evaluate the full variable expression using the current variables context
                # This allows for {my_list[0]} or {my_dict['key']}
                return str(eval(var_expression, {"__builtins__": None}, self.variables))
            except Exception as e:
                # print(f"DEBUG: Error during interpolation eval for '{var_expression}': {e}") # Uncomment for debugging
                return f"{{UNDEFINED_OR_INVALID_VAR:{var_expression}}}"
        # The regex now captures anything that is not a curly brace, allowing for more complex expressions
        return re.sub(r'\{([^{}]+)\}', replace_match, text)

    def _evaluate_condition(self, condition):
        """Basic condition evaluation (e.g., for @if)."""
        try:
            # Create a safe environment for eval, limiting globals and builtins
            # Only self.variables are accessible
            return eval(condition, {"__builtins__": None}, self.variables)
        except Exception as e:
            print(f"Error evaluating condition '{condition}': {e}")
            return False

    def execute(self, file_path):
        self.output_buffer = [] # Clear buffer for new execution
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
            # Pass the directory of the SML file for resolving relative paths in @include and @prompt file
            self._parse_and_execute_block(lines, os.path.dirname(os.path.abspath(file_path)))
            return "\n".join(self.output_buffer)
        except FileNotFoundError:
            return f"Error: File '{file_path}' not found."
        except Exception as e:
            return f"Error during execution: {e}"

    def _parse_and_execute_block(self, lines, base_dir, current_indent=0):
        """
        Parses and executes a block of lines.
        Args:
            lines (list): A list of strings, where each string is a line of the SML code.
            base_dir (str): The base directory for resolving relative file paths (e.g., for @include, @prompt file).
            current_indent (int): Current indentation level for debugging/logging (optional).
        """
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped_line = line.strip()

            if not stripped_line:
                i += 1
                continue

            # Interpolate the entire line for directives, as variables might be part of the command itself
            # e.g., @log {my_variable}, @include "{file_path_var}"
            interpolated_line = self._interpolate_variables(stripped_line)


            if interpolated_line.startswith('@set'):
                match = re.match(r'@set (\w+)\s*=\s*(.*)', interpolated_line)
                if match:
                    var_name = match.group(1)
                    value_expression = match.group(2).strip()

                    if value_expression.startswith('"') and value_expression.endswith('"'):
                        # Explicit string literal
                        self.variables[var_name] = value_expression[1:-1]
                    elif value_expression.startswith('@prompt'):
                        # Handle @prompt specific logic
                        prompt_match = re.search(r'@prompt\s*(?:file="([^"]+)")?\s*(?:"((?:[^"\\]|\\.)*)")?\s*(.*?)(?:\s*json_decode=(true|false))?\s*$', value_expression)
                        if prompt_match:
                            prompt_file = prompt_match.group(1)
                            inline_prompt_content = prompt_match.group(2)
                            other_params_string = prompt_match.group(3).strip()
                            json_decode_param = prompt_match.group(4)

                            max_tokens = None
                            temperature = None
                            do_json_decode = False

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
                                prompt_file_path = os.path.join(base_dir, prompt_file)
                                try:
                                    with open(prompt_file_path, 'r') as pf:
                                        # Interpolate variables in prompt file content as well
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
                                cleaned_llm_response = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", llm_response, flags=re.DOTALL).strip()
                                try:
                                    self.variables[var_name] = json.loads(cleaned_llm_response)
                                    # print(f"DEBUG: JSON decoded response for '{var_name}'. Value: {self.variables[var_name]}, Type: {type(self.variables[var_name])}") # Debug print
                                except json.JSONDecodeError as e:
                                    print(f"Error decoding JSON for '{var_name}': {e}. Storing as raw string.")
                                    self.variables[var_name] = llm_response
                            else:
                                self.variables[var_name] = llm_response
                        else:
                            print(f"Error: Malformed @prompt statement: {interpolated_line}")
                    else:
                        # Attempt to evaluate as a general Python literal (list, dict, int, float, bool)
                        # or a simple expression involving existing variables.
                        try:
                            # Use the original (non-interpolated by top-level line interpolation)
                            # value_expression here for eval, as it expects Python literal syntax.
                            self.variables[var_name] = eval(value_expression, {"__builtins__": None}, self.variables)
                            # print(f"DEBUG: @set {var_name} = evaluated to {self.variables[var_name]}, Type: {type(self.variables[var_name])}") # Debug print
                        except (NameError, SyntaxError, TypeError, IndexError) as e:
                            # If evaluation fails, treat as a literal string
                            print(f"Warning: Could not evaluate '{value_expression}' for variable '{var_name}'. Storing as string. Error: {e}")
                            self.variables[var_name] = value_expression
                else:
                    print(f"Error: Malformed @set statement: {interpolated_line}")

            elif interpolated_line.startswith('@log'):
                match = re.match(r'@log\s*(.*)', interpolated_line)
                if match:
                    log_content = match.group(1)
                    # log_content is already interpolated because it came from interpolated_line
                    self.output_buffer.append(log_content)
                else:
                    print(f"Error: Malformed @log statement: {interpolated_line}")

            elif interpolated_line.startswith('@include'):
                match = re.match(r'@include\s*"([^"]+)"', interpolated_line)
                if match:
                    include_path = os.path.join(base_dir, match.group(1))
                    if os.path.exists(include_path):
                        try:
                            with open(include_path, 'r') as f_inc:
                                include_lines = f_inc.readlines()
                            # Recursive call, passing the new base_dir for the included file
                            self._parse_and_execute_block(include_lines, os.path.dirname(os.path.abspath(include_path)), current_indent + 1)
                        except FileNotFoundError:
                            print(f"Error: Included file '{include_path}' not found.")
                        except Exception as e:
                            print(f"Error processing included file '{include_path}': {e}")
                    else:
                        print(f"Error: Included file '{include_path}' not found.")
                else:
                    print(f"Error: Malformed @include statement: {interpolated_line}")

            elif interpolated_line.startswith('@if'):
                condition = interpolated_line[len('@if'):].strip()
                if self._evaluate_condition(condition):
                    block_lines, next_i = self._get_block_lines(lines, i + 1, '@else', '@elseif', '@endif')
                    self._parse_and_execute_block(block_lines, base_dir, current_indent + 1) # Execute directly
                    i = next_i - 1 # Adjust index to skip the executed block
                else:
                    # Skip the block until @else, @elseif, or @endif
                    block_start_index = i + 1
                    while block_start_index < len(lines):
                        block_line = lines[block_start_index].strip()
                        if block_line.startswith('@else') or block_line.startswith('@elseif') or block_line.startswith('@endif'):
                            i = block_start_index - 1 # Set i to the line *before* the directive found
                            break
                        block_start_index += 1
                    else:
                        i = len(lines) # Reached end of file without a closing directive

            elif interpolated_line.startswith('@elseif'):
                # If we arrived here, the previous @if or @elseif was false.
                condition = interpolated_line[len('@elseif'):].strip()
                if self._evaluate_condition(condition):
                    block_lines, next_i = self._get_block_lines(lines, i + 1, '@else', '@endif')
                    self._parse_and_execute_block(block_lines, base_dir, current_indent + 1) # Execute directly
                    i = next_i - 1 # Adjust index to skip the executed block
                else:
                    # Skip the block until @else or @endif
                    block_start_index = i + 1
                    while block_start_index < len(lines):
                        block_line = lines[block_start_index].strip()
                        if block_line.startswith('@else') or block_line.startswith('@endif'):
                            i = block_start_index - 1 # Set i to the line *before* the directive found
                            break
                        block_start_index += 1
                    else:
                        i = len(lines) # Reached end of file without a closing directive

            elif interpolated_line.startswith('@else'):
                # This block is executed only if previous @if/@elseif was false
                block_lines, next_i = self._get_block_lines(lines, i + 1, '@endif')
                self._parse_and_execute_block(block_lines, base_dir, current_indent + 1) # Execute directly
                i = next_i - 1 # Adjust index to skip the executed block

            elif interpolated_line.startswith('@endif'):
                i += 1
                continue

            elif interpolated_line.startswith('@foreach'):
                match = re.match(r'@foreach (\w+) in (.*)', interpolated_line)
                if match:
                    loop_var = match.group(1)
                    collection_expression = match.group(2).strip()

                    try:
                        # Evaluate the collection expression in the current variables context
                        collection = eval(collection_expression, {"__builtins__": None}, self.variables)

                        if isinstance(collection, (list, dict, str)): # Allow iteration over lists, dicts (keys), and strings
                            block_lines, next_i = self._get_block_lines(lines, i + 1, '@endforeach')
                            for item in collection:
                                # Set the loop variable in the interpreter's variables for the block's execution
                                self.variables[loop_var] = item
                                self._parse_and_execute_block(block_lines, base_dir, current_indent + 1) # Execute directly
                            i = next_i - 1 # Adjust index to skip the entire foreach block
                        else:
                            print(f"Error: Expression '{collection_expression}' does not resolve to an iterable (list, dict, or string) for @foreach. Type: {type(collection)}")
                            # Skip the block if the collection is not iterable
                            _, next_i = self._get_block_lines(lines, i + 1, '@endforeach')
                            i = next_i - 1
                    except Exception as e:
                        print(f"Error evaluating collection expression '{collection_expression}': {e}")
                        # Skip the block if there's an error evaluating the collection
                        _, next_i = self._get_block_lines(lines, i + 1, '@endforeach')
                        i = next_i - 1
                else:
                    print(f"Error: Malformed @foreach statement: {interpolated_line}")

            elif interpolated_line.startswith('@endforeach'):
                i += 1
                continue

            else:
                # If it's not a directive, and not just whitespace, append its interpolated content.
                if not stripped_line.startswith('@'): # Ensure we don't accidentally print directives that didn't match.
                    self.output_buffer.append(interpolated_line)

            i += 1

    def _get_block_lines(self, all_lines, start_index, *end_directives):
        """Helper to extract lines within a control flow block."""
        block_lines = []
        current_index = start_index
        while current_index < len(all_lines):
            line = all_lines[current_index].strip() # Strip for directive matching
            if any(line.startswith(directive) for directive in end_directives):
                return block_lines, current_index + 1
            block_lines.append(all_lines[current_index]) # Keep original line with newline for block execution
            current_index += 1
        return block_lines, current_index


# --- Main Execution Logic ---
if __name__ == "__main__":
    interpreter = StructuralMLInterpreter(config_file="config.toml")
    main_prompt_file = "main_prompt.sml"
    main_prompt_content = interpreter.execute(main_prompt_file)
    # now send the prompt to llm
    interpreter._actual_llm_api_call(main_prompt_content, 1000, 0.1)
