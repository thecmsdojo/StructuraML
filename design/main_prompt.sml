@include "included_header.sml"

@set my_sorted_list = "[1, 2, 3, 4, 5]"
@set reverse_sorted_list = "[5, 4, 3, 2, 1]"
@set my_number = 10

@if my_number > 5
    @log "My number is greater than 5!"
@else
    @log "My number is not greater than 5."
@endif

@set phpunit_tests = @prompt file="prompts/phpunit_sorting_test.txt" max_token=2000 temperature=0.1 json_decode=true
@log "Generated PHPUnit Tests:"
@log {phpunit_tests}

@set carmakes_map = @prompt file="prompts/car_make_json.sml" max_token=1000
json_decode=true

@log {carmakes_map}

@set vocabulary_list = ["casa", "perro", "sol"]
@foreach item in vocabulary_list
    @log "Processing word: {item}"
    @set word_to_translate = "{item}"
    @set result = @prompt file="prompts/translate_word.sml"
    @log "Translation for '{item}': {result}"
@endforeach

@set another_prompt_example = @prompt "What is the capital of France?" max_token=50
@log "Another LLM query result: {another_prompt_example}"

Final prompt output:
{phpunit_tests}
{another_prompt_example}
