@include "included_header.sml"

@set my_sorted_list = "[1, 2, 3, 4, 5]"
@set reverse_sorted_list = "[5, 4, 3, 2, 1]"
@set my_number = 10

@if my_number > 5
    @log "My number is greater than 5!"
@else
    @log "My number is not greater than 5."
@endif

@set carmakes_map = @prompt file="prompts/car_make_json.sml" max_token=1000

show all the makes in {carmakes_map}
