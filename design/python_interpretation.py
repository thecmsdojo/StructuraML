import re
import os
import uuid # For unique temp file names

class StructuralMLInterpreter:
    # ... (rest of your class code remains the same)

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
                        # --- MODIFIED REGEX HERE ---
                        # This regex tries to capture the main prompt content OR file,
                        # and then any number of keyword arguments like max_token, temperature.
                        # It uses a non-greedy match for the prompt content to not consume keywords.
                        prompt_match = re.search(r'@prompt\s*(?:file="([^"]+)")?\s*(?:"((?:[^"\\]|\\.)*)")?\s*(.*)', value_expression)
                        if prompt_match:
                            prompt_file = prompt_match.group(1)
                            inline_prompt_content = prompt_match.group(2)
                            other_params_string = prompt_match.group(3).strip()

                            max_tokens = None
                            temperature = None

                            # Parse additional parameters from other_params_string
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
                            elif inline_prompt_content is not None: # Use 'is not None' because an empty string is valid
                                final_prompt = self._interpolate_variables(inline_prompt_content)
                            else:
                                print("Warning: @prompt without content or file.")
                                final_prompt = ""

                            llm_response = self.llm_api(final_prompt, max_tokens, temperature)
                            self.variables[var_name] = llm_response
                        else:
                            print(f"Error: Malformed @prompt statement: {interpolated_line}")
                    elif value_expression.startswith('[') and value_expression.endswith(']'):
                        # Basic list parsing
                        try:
                            self.variables[var_name] = [item.strip().strip('"') for item in value_expression[1:-1].split(',')]
                        except Exception as e:
                            print(f"Error parsing list for {var_name}: {e}")
                            self.variables[var_name] = []
                    else:
                        # Attempt to evaluate as a number or boolean
                        try:
                            self.variables[var_name] = eval(value_expression)
                        except (NameError, SyntaxError):
                            # Treat as a string if it's not a number/boolean
                            self.variables[var_name] = value_expression
                else:
                    print(f"Error: Malformed @set statement: {interpolated_line}")

            # ... (rest of the _parse_and_execute_block method)
