import json


def merge_json_arrays(input_string: str) -> list:
    """
    Parses a string containing multiple JSON arrays and merges them into a single list.
    """
    all_objects = []
    # Use a simple state machine to find and parse all JSON arrays in the string
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(input_string):
        # Skip whitespace and non-array characters
        while pos < len(input_string) and input_string[pos] != "[":
            pos += 1

        if pos >= len(input_string):
            break

        try:
            # Decode the array starting at the current position
            obj, end_pos = decoder.raw_decode(input_string[pos:])

            # The result should be a list, extend our main list with it
            if isinstance(obj, list):
                all_objects.extend(obj)

            # Move the main position past the object we just decoded
            pos += end_pos

        except json.JSONDecodeError:
            # If decoding fails, move to the next character to avoid infinite loops
            pos += 1

    return all_objects


# --- Main Execution ---
if __name__ == "__main__":
    # 1. Read the malformed JSON data from the file
    #    (I've named your input file 'malformed_data.json')
    input_filename = "./employee_profiles.json"
    output_filename = "fixed_data.json"

    try:
        with open(input_filename, "r", encoding="utf-8") as f:
            raw_data = f.read()

        # 2. Process the data to merge all arrays
        merged_list = merge_json_arrays(raw_data)

        # 3. Write the correctly formatted single list to a new file
        with open(output_filename, "w", encoding="utf-8") as f:
            # Use indent=4 for pretty printing
            json.dump(merged_list, f, indent=4)

        print(f"Successfully merged {len(merged_list)} objects.")
        print(f"Fixed data has been saved to '{output_filename}'")

    except FileNotFoundError:
        print(f"Error: The input file '{input_filename}' was not found.")
        print("Please create this file and paste your JSON data into it.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
