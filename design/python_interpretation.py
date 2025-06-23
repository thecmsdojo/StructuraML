import re
import os

class StructuralMLInterpreter:
    def __init__(self, llm_api_placeholder=None):
        self.variables = {}
        self.llm_api = llm_api_placeholder if llm_api_placeholder else self._default_llm_api
        self.output_buffer = []

    def _default_llm_api(self, prompt_text, max_tokens=None, temperature=None):
        """
        Placeholder for LLM API call.
        In a real application, replace this with actual API calls (e.g., OpenAI, Gemini).
        """
        print(f"\n--- LLM API Call ---")
        print(f"Prompt: '{prompt_text}'")
        print(f"Max Tokens: {max_tokens}, Temperature: {temperature}")
        print(f"--------------------\n")
        # Simulate an LLM response
        return f"LLM responded to: '{prompt_text[:50]}...'"

    def _interpolate_variables(self, text):
        """Replaces {variable_name} with their current values."""
        def replace_match(match):
            var_name = match.group(1)
            return str(self.variables.get(var_name, f"{{UNDEFINED_VAR:{var_name}}}"))
        return re.sub(r'\{(\w+)\}', replace_match, text)

    def _evaluate_condition(self, condition):
        """Basic condition evaluation (e.g., for @if)."""
        # This is very basic. For complex conditions, you'd use eval() cautiously
        # or a dedicated expression parser.
        try:
            # Replace variable names with their values before evaluation
            # Example: 'my_var == 10' -> '5 == 10'
            for var, value in self.variables.items():
                # Ensure we don't accidentally replace parts of other variable names
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
                        prompt_match = re.match(r'@prompt\s*(?:file="([^"]+)")?\s*"([^"]*)?"?\s*(?:max_token=(\d+))?\s*(?:temperature=([\d.]+))?', value_expression)
                        if prompt_match:
                            prompt_file = prompt_match.group(1)
                            inline_prompt_content = prompt_match.group(2)
                            max_tokens = prompt_match.group(3)
                            temperature = prompt_match.group(4)

                            if max_tokens: max_tokens = int(max_tokens)
                            if temperature: temperature = float(temperature)

                            final_prompt = ""
                            if prompt_file:
                                prompt_file_path = os.path.join(os.path.dirname(file_path), prompt_file)
                                try:
                                    with open(prompt_file_path, 'r') as pf:
                                        final_prompt = self._interpolate_variables(pf.read())
                                except FileNotFoundError:
                                    print(f"Error: Prompt file '{prompt_file_path}' not found.")
                                    final_prompt = f"Error: Prompt file '{prompt_file_path}' not found."
                            elif inline_prompt_content:
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

            elif interpolated_line.startswith('@log'):
                match = re.match(r'@log\s*(.*)', interpolated_line)
                if match:
                    log_content = match.group(1)
                    # If it's just a variable name, log its value
                    var_match = re.match(r'\{(\w+)\}', log_content)
                    if var_match:
                        self.output_buffer.append(str(self.variables.get(var_match.group(1), f"{{UNDEFINED_VAR:{var_match.group(1)}}}")))
                    else:
                        self.output_buffer.append(log_content)
                else:
                    print(f"Error: Malformed @log statement: {interpolated_line}")

            elif interpolated_line.startswith('@include'):
                match = re.match(r'@include\s*<([^>]+)>', interpolated_line)
                if match:
                    include_path = os.path.join(os.path.dirname(file_path), match.group(1))
                    if os.path.exists(include_path):
                        self._parse_and_execute_block(include_path, current_indent + 1) # Recursive include
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
                    i = next_i -1 # Adjust i to continue after the block
                else:
                    # Skip to @else, @elseif, or @endif
                    block_start_index = i + 1
                    while block_start_index < len(lines):
                        block_line = lines[block_start_index].strip()
                        if block_line.startswith('@else') or block_line.startswith('@elseif') or block_line.startswith('@endif'):
                            i = block_start_index -1 # Adjust i to process the next control flow
                            break
                        block_start_index += 1
                    else: # If no matching end found, advance to the end of file
                        i = len(lines)

            elif interpolated_line.startswith('@elseif'):
                # Already handled by @if's else branch. Skip this.
                i += 1
                continue

            elif interpolated_line.startswith('@else'):
                # If we reached @else, the @if condition was false. Execute this block.
                block_lines, next_i = self._get_block_lines(lines, i + 1, '@endif')
                temp_file = self._write_temp_block(block_lines)
                self._parse_and_execute_block(temp_file, current_indent + 1)
                os.remove(temp_file)
                i = next_i -1 # Adjust i to continue after the block

            elif interpolated_line.startswith('@endif'):
                # End of if block, just move to the next line
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
                            self.variables[loop_var] = item # Set loop variable for current iteration
                            self._parse_and_execute_block(temp_file, current_indent + 1)
                        os.remove(temp_file)
                        i = next_i -1 # Adjust i to continue after the block
                    else:
                        print(f"Error: Variable '{collection_var}' is not a list for @foreach.")
                        # Skip the block if not a list
                        _, next_i = self._get_block_lines(lines, i + 1, '@endforeach')
                        i = next_i - 1
                else:
                    print(f"Error: Malformed @foreach statement: {interpolated_line}")

            elif interpolated_line.startswith('@endforeach'):
                # End of foreach block, just move to the next line
                i += 1
                continue

            # Handle direct variable output or plain text lines
            elif interpolated_line.startswith('{') and interpolated_line.endswith('}'):
                var_name = interpolated_line[1:-1]
                self.output_buffer.append(str(self.variables.get(var_name, f"{{UNDEFINED_VAR:{var_name}}}")))
            else:
                # Treat as plain text to be included in the final prompt, after interpolation
                if not interpolated_line.startswith('@'): # Avoid printing unhandled directives
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
            block_lines.append(all_lines[current_index]) # Keep original line for writing to temp file
            current_index += 1
        return block_lines, current_index # Reached end of file without finding end directive

    def _write_temp_block(self, lines):
        """Writes a block of lines to a temporary file for recursive execution."""
        import uuid
        temp_file_name = f"temp_structuralml_block_{uuid.uuid4().hex}.sml"
        with open(temp_file_name, 'w') as f:
            f.writelines(lines)
        return temp_file_name


# --- Example Usage ---
if __name__ == "__main__":
    # Create some dummy prompt files for demonstration
    os.makedirs('prompts', exist_ok=True)

    with open('prompts/phpunit_sorting_test.txt', 'w') as f:
        f.write("""
Generate PHPUnit test cases for a sorting algorithm with the following conditions:
- Empty array: []
- Single element array: [5]
- Already sorted array: {my_sorted_list}
- Reverse-sorted array: {reverse_sorted_list}
- Array with duplicates: [1, 2, 2, 3, 1]
- The algorithm should handle numbers.
""")

    with open('prompts/translate_word.sml', 'w') as f:
        f.write("""
Please translate the word '{word_to_translate}' to English.
""")

    with open('included_header.sml', 'w') as f:
        f.write("""
@log "--- Starting Prompt Generation ---"
@set initial_message = "This is a prompt generated by StructuralML."
@log {initial_message}
""")

    with open('main_prompt.sml', 'w') as f:
        f.write("""
@include <included_header.sml>

@set my_sorted_list = "[1, 2, 3, 4, 5]"
@set reverse_sorted_list = "[5, 4, 3, 2, 1]"
@set my_number = 10

@if my_number > 5
    @log "My number is greater than 5!"
@else
    @log "My number is not greater than 5."
@endif

@set phpunit_tests = @prompt file="prompts/phpunit_sorting_test.txt" max_token=500 temperature=0.7
@log "Generated PHPUnit Tests:"
@log {phpunit_tests}

@set vocabulary_list = ["casa", "perro", "sol"]
@foreach item in vocabulary_list
    @log "Processing word: {item}"
    @set word_to_translate = {item} // Assign to a variable for the included prompt
    @set result = @prompt file="prompts/translate_word.sml"
    @log "Translation for '{item}': {result}"
@endforeach

@set another_prompt_example = @prompt "What is the capital of France?" max_token=50
@log "Another LLM query result: {another_prompt_example}"

Final prompt output:
{phpunit_tests}
{another_prompt_example}
""")

    interpreter = StructuralMLInterpreter()
    final_output = interpreter.execute('main_prompt.sml')
    print("\n\n--- Final Interpreter Output ---")
    print(final_output)

    # Clean up dummy files
    os.remove('prompts/phpunit_sorting_test.txt')
    os.remove('prompts/translate_word.sml')
    os.remove('included_header.sml')
    os.remove('main_prompt.sml')
    os.rmdir('prompts')
